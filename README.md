# Rare Earths Assistant (RAG chat)

A public chat website that answers questions about rare earths using **your documents and datasets**.
The ChatGPT model decides when to call three tools (`search_documents`, `list_datasets`, `query_dataset`), then writes a cited answer.

```
Browser (static/)  ->  FastAPI (/api/chat)  ->  OpenAI (function calling)
                                |-> app/rag.py       search PDFs/MD/TXT in data/documents
                                |-> app/datasets.py  query CSVs in data/datasets
```

## Project layout
```
app/main.py       API, tool loop, rate limiting
app/rag.py        document chunking + search
app/datasets.py   CSV queries
scripts/ingest.py builds data/index.pkl
static/           chat UI (index.html, style.css, app.js)
Dockerfile, render.yaml, requirements.txt, .env.example
```
