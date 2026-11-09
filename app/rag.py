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
    """Yield (page_number_or_None, text) for a file. Raises on unreadable files (the caller skips them)."""
    ext = path.suffix.lower()
    if ext in {".txt", ".md"}:
        yield None, path.read_text(encoding="utf-8", errors="ignore")
    elif ext == ".pdf":
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")  # many "protected" PDFs just have an empty user password
            except Exception as e:
                raise ValueError(f"password-protected PDF ({e})")
        fallback = {}  # lazily opened PyMuPDF document, used only for pages pypdf cannot read
        for i, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception:
                # e.g. pypdf LimitReachedError on huge/complex pages: try a second PDF engine for this page only
                text = _fallback_page_text(path, i, fallback)
            yield i, text


def _fallback_page_text(path: Path, page_no: int, cache: dict) -> str:
    try:
        import pymupdf
        if "doc" not in cache:
            cache["doc"] = pymupdf.open(str(path))
        return cache["doc"][page_no - 1].get_text() or ""
    except Exception:
        return ""  # one unreadable page should not lose the whole document


def build_index():
    chunks, skipped = [], []
    for path in sorted(DOC_DIR.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {".txt", ".md", ".pdf"}:
            continue
        before = len(chunks)
        try:
            for page, text in _read(path):
                for j, c in enumerate(_chunk(text)):
                    if len(c.strip()) < 30:
                        continue
                    chunks.append({
                        "id": f"{path.stem}-{page or 0}-{j}",
                        "title": path.stem.replace("_", " ").replace("-", " ").title(),
                        "source": path.name,
                        "page": page,
                        "text": c,
                    })
        except Exception as e:
            chunks = chunks[:before]  # drop partial results from a file that failed midway
            skipped.append((path.name, repr(e)[:160]))
            continue
        if len(chunks) == before:
            skipped.append((path.name, "no extractable text (scanned PDF? run OCR first)"))
    empty = {"chunks": [], "vectorizer": None, "matrix": None, "skipped": skipped}
    if not chunks:
        return empty
    texts = [c["text"] for c in chunks]
    for kwargs in (dict(stop_words="english", ngram_range=(1, 2), sublinear_tf=True),
                   dict(ngram_range=(1, 1), sublinear_tf=True)):  # fallback if stop-word filtering empties the vocabulary
        try:
            vec = TfidfVectorizer(**kwargs)
            matrix = vec.fit_transform(texts)
            return {"chunks": chunks, "vectorizer": vec, "matrix": matrix, "skipped": skipped}
        except ValueError:
            continue
    return empty


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
