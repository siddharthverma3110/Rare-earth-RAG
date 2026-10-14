# Rare Earths Assistant (RAG chat)

A public chat website that answers questions about rare earths using **your documents and datasets**.
The ChatGPT model decides when to call three tools (`search_documents`, `list_datasets`, `query_dataset`), then writes a cited answer.

```
Browser (static/)  ->  FastAPI (/api/chat)  ->  OpenAI (function calling)
                                |-> app/rag.py       search PDFs/MD/TXT in data/documents
                                |-> app/datasets.py  query CSVs in data/datasets
```

## 1. Add your data
- Put documents (`.pdf`, `.md`, `.txt`) in `data/documents/`.
- Put tables (`.csv`, with a header row) in `data/datasets/`, and describe them in `data/datasets/descriptions.json`.
- The sample files are placeholders. Delete them once you add yours.

## 2. Run locally
```bash
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                 # then paste your OPENAI_API_KEY
python -m scripts.ingest                             # optional: pre-builds the search index
uvicorn app.main:app --reload
```
Open http://localhost:8000

## 3. Push to GitHub
```bash
git init && git add . && git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<you>/rare-earths-rag.git
git push -u origin main
```
`.env` is git-ignored, so your API key is never committed. If your documents are private or licensed,
use a **private repo**, or keep them out of git and load them at deploy time.

## 4. Deploy (Render, easiest)
1. Go to https://render.com, sign in with GitHub, and choose **New > Blueprint** (or **New > Web Service**).
2. Select your repo. Render reads `render.yaml` and builds the `Dockerfile`.
3. When prompted, set `OPENAI_API_KEY` (from https://platform.openai.com/api-keys).
4. Click deploy. You get a public URL like `https://rare-earths-rag.onrender.com`.
5. Check `https://<your-url>/api/health` returns `{"ok": true}`.

The free tier sleeps after inactivity, so the first request can take ~30-60 s. Use a paid instance for always-on.

### Other hosts
The app is a standard Docker container that listens on `$PORT`, so it also runs on:
- **Railway**: New Project > Deploy from GitHub; add `OPENAI_API_KEY`.
- **Fly.io**: `fly launch`, then `fly secrets set OPENAI_API_KEY=...`, then `fly deploy`.
- **Google Cloud Run**: `gcloud run deploy --source . --set-env-vars OPENAI_API_KEY=...`.

## 5. Custom domain
In your host's dashboard, add the domain, then create the CNAME record they show at your DNS provider. HTTPS is automatic.

## 6. Protect your API bill (important for a public site)
- Set a **monthly spend limit** in the OpenAI dashboard (Settings > Limits).
- `RATE_LIMIT_PER_HOUR` (per IP) and `DAILY_REQUEST_CAP` (global) are enforced in `app/main.py`.
  They are in-memory, so use Redis if you run more than one instance.
- Optional: put Cloudflare in front for bot protection, or add a login before `/api/chat`.

## Choosing the model
Set `OPENAI_MODEL` (default `gpt-4o`). Reasoning models such as `gpt-6-luna` don't allow function tools on the
Chat Completions API while reasoning is on, so set `OPENAI_REASONING_EFFORT=none`. The app also adapts automatically: if the API says
function tools need reasoning off it retries with `none`, and if the model doesn't recognise
`reasoning_effort` at all it retries without it. For models like `gpt-4o`, leave the setting blank.

## Upgrading retrieval
`app/rag.py` uses TF-IDF, which is fast and light. For semantic search, replace `build_index()` and
`search()` with embeddings + a vector DB (Chroma, pgvector, Pinecone, Qdrant). Keep the same return shape
and nothing else needs to change. Likewise `app/datasets.py` can query a SQL database or external API.

## Project layout
```
app/main.py       API, tool loop, rate limiting
app/rag.py        document chunking + search
app/datasets.py   CSV queries
scripts/ingest.py builds data/index.pkl
static/           chat UI (index.html, style.css, app.js)
Dockerfile, render.yaml, requirements.txt, .env.example
```
