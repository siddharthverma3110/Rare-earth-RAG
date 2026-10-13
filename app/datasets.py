"""Structured data lookups over CSV files in data/datasets/.

Optional: data/datasets/descriptions.json  ->  {"file_stem": "what this table contains"}
To use a database or external API instead, keep these two function signatures.
"""
import csv
import json
from pathlib import Path

DS_DIR = Path(__file__).resolve().parent.parent / "data" / "datasets"
MAX_ROWS = 60


def _load():
    desc_file = DS_DIR / "descriptions.json"
    descs = json.loads(desc_file.read_text()) if desc_file.exists() else {}
    out = {}
    for p in sorted(DS_DIR.glob("*.csv")):
        with p.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        out[p.stem] = {"description": descs.get(p.stem, ""), "rows": rows,
                       "columns": list(rows[0].keys()) if rows else []}
    return out


DATA = _load()


def list_datasets():
    return [{"name": k, "description": v["description"], "columns": v["columns"], "row_count": len(v["rows"])}
            for k, v in DATA.items()]


def query(dataset: str, filters: dict | None = None):
    ds = DATA.get(dataset)
    if ds is None:
        return {"error": f"Unknown dataset '{dataset}'. Available: {list(DATA)}"}
    filters = filters or {}
    bad = [c for c in filters if c not in ds["columns"]]
    if bad:
        return {"error": f"Unknown columns {bad}. Columns: {ds['columns']}"}
    rows = [r for r in ds["rows"]
            if all(str(r[c]).strip().lower() == str(v).strip().lower() for c, v in filters.items())]
    return {"columns": ds["columns"], "total_matches": len(rows), "rows": rows[:MAX_ROWS]}
