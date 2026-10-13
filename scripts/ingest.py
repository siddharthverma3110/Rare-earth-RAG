"""Pre-build the search index:  python -m scripts.ingest
Reads everything in data/documents (.pdf, .txt, .md) and writes data/index.pkl.
Optional - the app builds the index on startup if the file is missing."""
from app import rag

idx = rag.build_index()
rag.save_index(idx)
print(f"Indexed {len(idx['chunks'])} chunks from {len({c['source'] for c in idx['chunks']})} files.")
