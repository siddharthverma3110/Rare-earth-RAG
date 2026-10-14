"""Structured data lookups over CSV files in data/datasets/.

Optional: data/datasets/descriptions.json  ->  {"file_stem": "what this table contains"}
To use a database or external API instead, keep these two function signatures.
"""
import csv
import difflib
import json
import re
from pathlib import Path

DS_DIR = Path(__file__).resolve().parent.parent / "data" / "datasets"
MAX_ROWS = 60


def _read_text(path: Path) -> str:
    """Read a CSV as UTF-8 (with or without BOM); fall back to Windows-1252 (common for Excel/government exports)."""
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def _load():
    desc_file = DS_DIR / "descriptions.json"
    descs = json.loads(desc_file.read_text()) if desc_file.exists() else {}
    out = {}
    for p in sorted(DS_DIR.glob("*.csv")):
        rows = list(csv.DictReader(_read_text(p).splitlines()))
        out[p.stem] = {"description": descs.get(p.stem, ""), "rows": rows,
                       "columns": list(rows[0].keys()) if rows else []}
    return out


DATA = _load()


def list_datasets():
    return [{"name": k, "description": v["description"], "columns": v["columns"], "row_count": len(v["rows"])}
            for k, v in DATA.items()]


def _norm(x: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def query(dataset: str, filters: dict | None = None, contains: str | None = None):
    """Forgiving lookup.
    - dataset and column names are matched ignoring case, spaces and underscores
    - filter values must match exactly; if nothing matches, they are retried as case-insensitive substrings
    - `contains`: space-separated words that must all appear somewhere in the row (any column)
    - when nothing matches, the result lists the closest real values so the caller can correct itself
    """
    key = next((k for k in DATA if _norm(k) == _norm(dataset)), None)
    if key is None:
        return {"error": f"Unknown dataset '{dataset}'. Available: {list(DATA)}"}
    ds = DATA[key]
    colmap = {_norm(c): c for c in ds["columns"]}
    resolved = {}
    for col, val in (filters or {}).items():
        real = colmap.get(_norm(col))
        if real is None:
            return {"error": f"Unknown column '{col}'. Columns: {ds['columns']}"}
        resolved[real] = str(val).strip().lower()

    def match(row, partial):
        for col, val in resolved.items():
            cell = str(row[col]).strip().lower()
            if (val not in cell) if partial else (cell != val):
                return False
        return True

    rows, mode = ds["rows"], "exact"
    if resolved:
        found = [r for r in rows if match(r, False)]
        if not found:
            found, mode = [r for r in rows if match(r, True)], "partial"
        rows = found
    if contains:
        terms = contains.lower().split()
        rows = [r for r in rows if all(t in " ".join(map(str, r.values())).lower() for t in terms)]

    out = {"columns": ds["columns"], "match_mode": mode, "total_matches": len(rows), "rows": rows[:MAX_ROWS]}
    if not rows:
        hint = {}
        for col, val in resolved.items():
            values = sorted({r[col] for r in ds["rows"]})
            hint[col] = difflib.get_close_matches(val, values, n=8, cutoff=0.3) or values[:8]
        out["hint"] = {"note": "No rows matched. Closest real values per filtered column; retry with fewer or looser filters, or use 'contains'.", "closest_values": hint}
    return out
