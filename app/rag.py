"""Document retrieval. Default: TF-IDF (no GPU, tiny memory, free-tier friendly).

To upgrade to embeddings + a vector DB, keep the same public API:
    search(query, top_k) -> list[dict(id, title, source, page, text, score)]
and replace the body of `build_index` / `search`.
"""
import pickle
import re
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

DOC_DIR = Path(__file__).resolve().parent.parent / "data" / "documents"
INDEX_PATH = Path(__file__).resolve().parent.parent / "data" / "index.pkl"
CHUNK_CHARS, OVERLAP = 900, 150

_index = None  # {"chunks": [...], "vectorizer": ..., "matrix": ...}


def _chunk(text: str):
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    buf = ""
    for p in paras:
        if len(buf) + len(p) > CHUNK_CHARS and buf:
            yield buf
            buf = buf[-OVERLAP:] + "\n" + p
        else:
            buf = (buf + "\n\n" + p).strip()
    if buf:
        yield buf


def _read(path: Path):
    """Yield (page_number_or_None, text) for a file."""
    ext = path.suffix.lower()
    if ext in {".txt", ".md"}:
        yield None, path.read_text(encoding="utf-8", errors="ignore")
    elif ext == ".pdf":
        from pypdf import PdfReader
        for i, page in enumerate(PdfReader(str(path)).pages, start=1):
            yield i, page.extract_text() or ""


def build_index():
    chunks = []
    for path in sorted(DOC_DIR.rglob("*")):
        if not path.is_file():
            continue
        for page, text in _read(path):
            for j, c in enumerate(_chunk(text)):
                chunks.append({
                    "id": f"{path.stem}-{page or 0}-{j}",
                    "title": path.stem.replace("_", " ").replace("-", " ").title(),
                    "source": path.name,
                    "page": page,
                    "text": c,
                })
    if not chunks:
        return {"chunks": [], "vectorizer": None, "matrix": None}
    vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), sublinear_tf=True)
    matrix = vec.fit_transform([c["text"] for c in chunks])
    return {"chunks": chunks, "vectorizer": vec, "matrix": matrix}


def save_index(idx):
    INDEX_PATH.write_bytes(pickle.dumps(idx))


def load_index():
    global _index
    if INDEX_PATH.exists():
        _index = pickle.loads(INDEX_PATH.read_bytes())
    else:
        _index = build_index()
    return _index


def search(query: str, top_k: int = 4):
    idx = _index or load_index()
    if not idx["chunks"]:
        return []
    q = idx["vectorizer"].transform([query])
    scores = linear_kernel(q, idx["matrix"]).ravel()
    order = scores.argsort()[::-1][: max(1, min(top_k, 8))]
    return [{**idx["chunks"][i], "score": round(float(scores[i]), 3)} for i in order if scores[i] > 0]
