import json
import os
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
    "use several calls if needed. Cite document titles and pages for text facts, and name the dataset "
    "for numbers. If the tools return nothing relevant, say it is not in the knowledge base instead of "
    "guessing. Be concise and use short Markdown lists when helpful."
)

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


def complete(msgs):
    """Call the model; if it rejects reasoning_effort with tools, retry once with reasoning off."""
    kwargs = dict(model=MODEL, messages=msgs, tools=TOOLS, max_completion_tokens=1200)
    if REASONING_EFFORT:
        kwargs["reasoning_effort"] = REASONING_EFFORT
    try:
        return client.chat.completions.create(**kwargs)
    except BadRequestError as e:
        if "reasoning_effort" in str(e) and kwargs.get("reasoning_effort") != "none":
            kwargs["reasoning_effort"] = "none"
            return client.chat.completions.create(**kwargs)
        raise


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
    trace, sources = [], {}
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
                trace.append({"tool": call.function.name, "input": args, "output": out})
                if call.function.name == "search_documents" and isinstance(out, list):
                    for c in out:
                        sources[c["id"]] = {"title": c["title"], "source": c["source"], "page": c["page"]}
                msgs.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(out)})
    except OpenAIError as e:
        raise HTTPException(502, f"Model error: {getattr(e, 'message', str(e))}")
    answer = (msg.content or "").strip() or "I couldn't produce an answer."
    return {"answer": answer, "sources": list(sources.values()), "trace": trace}


@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
