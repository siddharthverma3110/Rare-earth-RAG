import json
import os
import re
import time
from collections import defaultdict, deque

from openai import BadRequestError, OpenAI, OpenAIError
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import datasets, rag

load_dotenv()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
RATE_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "30"))
DAILY_CAP = int(os.getenv("DAILY_REQUEST_CAP", "500"))
MAX_TOOL_ROUNDS = 5
# Reasoning models (e.g. gpt-6-luna) reject function tools on /v1/chat/completions unless reasoning is off.
# Set OPENAI_REASONING_EFFORT=none (or low/medium/high where supported). Leave blank for non-reasoning models.
REASONING_EFFORT = os.getenv("OPENAI_REASONING_EFFORT", "").strip()

client = OpenAI()  # reads OPENAI_API_KEY
app = FastAPI(title="Rare Earths RAG")

origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["POST", "GET"], allow_headers=["*"])

SYSTEM = (
    "You are a rare earths research assistant. Answer using ONLY information returned by your tools "
    "(search_documents, list_datasets, query_dataset). Call tools before answering factual questions; "
    "use several calls if needed. Every passage or dataset result returned by a tool has a 'cite' tag "
    "such as S1. Put the tag(s) in square brackets immediately after each sentence or claim they support, "
    "e.g. 'Nd and Pr are used in NdFeB magnets [S1].' Use several tags like [S1][S3] when needed. Only use "
    "tags that tools returned, and never write a separate reference list or source names in the text. "
    "If the tools return nothing relevant, say it is not in the knowledge base instead of guessing. "
    "Be concise and use short Markdown lists when helpful."
)

CITE_RE = re.compile(r"\[(S\d+(?:\s*,\s*S\d+)*)\]")


def _fn(name, description, parameters):
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


TOOLS = [
    _fn("search_documents",
        "Search the rare earths document corpus. Returns the most relevant passages with source and page.",
        {"type": "object",
         "properties": {"query": {"type": "string"}, "top_k": {"type": "integer", "default": 4}},
         "required": ["query"]}),
    _fn("list_datasets",
        "List available structured datasets with their columns and descriptions.",
        {"type": "object", "properties": {}}),
    _fn("query_dataset",
        "Fetch rows from a dataset. 'filters' maps column name -> exact value (case-insensitive).",
        {"type": "object",
         "properties": {"dataset": {"type": "string"}, "filters": {"type": "object"}},
         "required": ["dataset"]}),
]


_effort = REASONING_EFFORT or None  # learned at runtime and remembered for later requests


def complete(msgs):
    """Call the model, adapting `reasoning_effort` to what the model accepts:
    - rejects function tools while reasoning -> retry with "none"
    - doesn't recognise the parameter at all -> retry without it
    The working setting is remembered, so only the first request pays for a retry."""
    global _effort
    last = None
    for _ in range(3):
        kwargs = dict(model=MODEL, messages=msgs, tools=TOOLS, max_completion_tokens=1200)
        if _effort:
            kwargs["reasoning_effort"] = _effort
        try:
            return client.chat.completions.create(**kwargs)
        except BadRequestError as e:
            last = e
            m = str(e).lower()
            if "reasoning_effort" not in m:
                raise
            if "unrecognized" in m or "unknown" in m or "unsupported parameter" in m:
                if _effort is None:
                    raise
                _effort = None
            elif _effort != "none":
                _effort = "none"
            else:
                raise
    raise last


def run_tool(name: str, args: dict):
    if name == "search_documents":
        return rag.search(args.get("query", ""), int(args.get("top_k", 4)))
    if name == "list_datasets":
        return datasets.list_datasets()
    if name == "query_dataset":
        return datasets.query(args.get("dataset", ""), args.get("filters"))
    return {"error": f"Unknown tool {name}"}


# ---- simple in-memory rate limiting (use Redis if you run several instances) ----
_hits = defaultdict(deque)
_day = {"key": None, "n": 0}


def check_limits(request: Request):
    ip = (request.headers.get("x-forwarded-for") or request.client.host or "?").split(",")[0].strip()
    now = time.time()
    q = _hits[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= RATE_PER_HOUR:
        raise HTTPException(429, "Too many requests. Please try again later.")
    today = time.strftime("%Y-%m-%d")
    if _day["key"] != today:
        _day.update(key=today, n=0)
    if _day["n"] >= DAILY_CAP:
        raise HTTPException(429, "Daily capacity reached. Please come back tomorrow.")
    q.append(now)
    _day["n"] += 1


class Msg(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(max_length=4000)


class ChatIn(BaseModel):
    messages: list[Msg] = Field(min_length=1, max_length=20)


@app.get("/api/health")
def health():
    return {"ok": True, "model": MODEL}


@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    check_limits(request)
    if body.messages[-1].role != "user":
        raise HTTPException(400, "Last message must be from the user.")
    msgs = [{"role": "system", "content": SYSTEM}] + [m.model_dump() for m in body.messages[-12:]]
    trace, src, labels = [], {}, {}

    def label(key, info):
        if key not in labels:
            labels[key] = f"S{len(labels) + 1}"
            src[labels[key]] = info
        return labels[key]

    try:
        for _ in range(MAX_TOOL_ROUNDS + 1):
            resp = complete(msgs)
            msg = resp.choices[0].message
            if not msg.tool_calls:
                break
            msgs.append(msg.model_dump(exclude_none=True))
            for call in msg.tool_calls:
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                out = run_tool(call.function.name, args)
                if call.function.name == "search_documents" and isinstance(out, list):
                    for c in out:
                        c["cite"] = label(c["id"], {"title": c["title"], "source": c["source"], "page": c["page"],
                                                    "excerpt": c["text"][:400]})
                elif call.function.name == "query_dataset" and isinstance(out, dict) and "rows" in out:
                    ds = args.get("dataset", "")
                    preview = "; ".join(", ".join(f"{k}={v}" for k, v in r.items()) for r in out["rows"][:3])
                    out["cite"] = label("ds:" + ds + json.dumps(args.get("filters"), sort_keys=True),
                                        {"title": "Dataset: " + ds, "source": ds + ".csv", "page": None,
                                         "excerpt": (f"Filters: {args.get('filters') or 'none'}. " + preview)[:400]})
                trace.append({"tool": call.function.name, "input": args, "output": out})
                msgs.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(out)})
    except OpenAIError as e:
        raise HTTPException(502, f"Model error: {getattr(e, 'message', str(e))}")
    answer = (msg.content or "").strip() or "I couldn't produce an answer."
    used = {t.strip() for grp in CITE_RE.findall(answer) for t in grp.split(",")}
    return {"answer": answer, "sources": {k: v for k, v in src.items() if k in used}, "trace": trace}


@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
