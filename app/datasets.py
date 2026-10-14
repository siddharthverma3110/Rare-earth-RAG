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


def _vals(v):
    return [str(x).strip().lower() for x in (v if isinstance(v, (list, tuple)) else [v])]


def _find(dataset: str):
    key = next((k for k in DATA if _norm(k) == _norm(dataset)), None)
    return (key, DATA[key]) if key else (None, None)


def _select(ds, filters, contains):
    """Return (rows, mode, resolved_filters, error). Filter values may be a string or a list (any-of)."""
    colmap = {_norm(c): c for c in ds["columns"]}
    resolved = {}
    for col, val in (filters or {}).items():
        real = colmap.get(_norm(col))
        if real is None:
            return None, None, None, {"error": f"Unknown column '{col}'. Columns: {ds['columns']}"}
        resolved[real] = _vals(val)

    def match(row, partial):
        for col, vals in resolved.items():
            cell = str(row[col]).strip().lower()
            if not (any(v in cell for v in vals) if partial else cell in vals):
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
    return rows, mode, resolved, None


def _hint(ds, resolved):
    hint = {}
    for col, vals in resolved.items():
        values = sorted({r[col] for r in ds["rows"]})
        close = []
        for v in vals:
            close += difflib.get_close_matches(v, values, n=6, cutoff=0.3)
        hint[col] = close or values[:8]
    return {"note": "No rows matched. Closest real values per filtered column; retry with fewer or looser filters, or use 'contains'.",
            "closest_values": hint}


def _unmatched(rows, resolved):
    """Requested filter values that matched no selected row (e.g. a misspelt item in a list)."""
    out = {}
    for col, vals in resolved.items():
        missing = [v for v in vals if not any(v in str(r[col]).strip().lower() for r in rows)]
        if missing:
            out[col] = missing
    return out


def query(dataset: str, filters: dict | None = None, contains: str | None = None):
    """Forgiving lookup.
    - dataset and column names are matched ignoring case, spaces and underscores
    - filter values must match exactly (a list means any-of); if nothing matches they are retried as substrings
    - `contains`: space-separated words that must all appear somewhere in the row (any column)
    - when nothing matches, the result lists the closest real values so the caller can correct itself
    """
    key, ds = _find(dataset)
    if ds is None:
        return {"error": f"Unknown dataset '{dataset}'. Available: {list(DATA)}"}
    rows, mode, resolved, err = _select(ds, filters, contains)
    if err:
        return err
    out = {"columns": ds["columns"], "match_mode": mode, "total_matches": len(rows), "rows": rows[:MAX_ROWS]}
    if not rows:
        out["hint"] = _hint(ds, resolved)
    elif (um := _unmatched(rows, resolved)):
        out["unmatched_filter_values"] = um
    return out


def _num(v):
    """'1,234' -> 1234.0 ; 'W', 'NA', '>50', '-' -> None"""
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def chart_data(dataset, filters, x, series_by=None, y="Value", contains=None):
    """Pivot matching rows into chart series, straight from the data (no model-typed numbers)."""
    key, ds = _find(dataset)
    if ds is None:
        return {"error": f"Unknown dataset '{dataset}'. Available: {list(DATA)}"}
    rows, mode, resolved, err = _select(ds, filters, contains)
    if err:
        return err
    if not rows:
        return {"error": "No rows matched.", "hint": _hint(ds, resolved) if resolved else None}
    colmap = {_norm(c): c for c in ds["columns"]}
    xc, yc = colmap.get(_norm(x or "")), colmap.get(_norm(y or "Value"))
    sc = colmap.get(_norm(series_by)) if series_by else None
    if not xc or not yc or (series_by and not sc):
        return {"error": f"Unknown x / series_by / value column. Columns: {ds['columns']}"}
    uc = colmap.get("unit")
    units = sorted({r[uc].strip() for r in rows if r[uc].strip()}) if uc else []
    if len(units) > 1:
        return {"error": f"Rows have mixed units {units}. Narrow the filters so a single unit remains (e.g. filter Unit or Statistics)."}

    series, seen, skipped = {}, set(), 0
    for r in rows:
        name = r[sc] if sc else yc
        if (name, r[xc]) in seen:
            return {"error": "Several rows share the same series and x value. Narrow the filters (add Country, Statistics or "
                             "Statistics_detail) or use series_by='Statistics_detail'."}
        seen.add((name, r[xc]))
        n = _num(r[yc])
        skipped += n is None
        series.setdefault(name, {})[r[xc]] = n
    xs = sorted({r[xc] for r in rows}, key=lambda v: (_num(v) is None, _num(v) if _num(v) is not None else 0, v))
    out_series = [{"name": n, "values": [pts.get(xv) for xv in xs]} for n, pts in series.items()]
    if all(v is None for s_ in out_series for v in s_["values"]):
        return {"error": "None of the matching values are numeric (they are codes such as W, NA or ranges)."}
    return {"x": xs, "series": out_series, "y_label": units[0] if units else yc, "skipped": skipped,
            "dataset": key, "rows_used": len(rows)}
