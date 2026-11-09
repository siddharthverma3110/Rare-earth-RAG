"""Academic paper search via OpenAlex.

OpenAlex requires a free API key (since Feb 2026): set OPENALEX_API_KEY.
Failures are logged (see your Render logs) instead of being swallowed silently.
"""
import logging
import os
import re

import httpx

log = logging.getLogger("academic")
OPENALEX = "https://api.openalex.org/works"
_warned_nokey = False


def _abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    pos = {i: w for w, idxs in inv.items() for i in idxs}
    return " ".join(pos[i] for i in sorted(pos))


def _authors(names: list[str]) -> str:
    names = [n for n in names if n]
    return ", ".join(names[:3]) + (" et al." if len(names) > 3 else "")


def _paper(title, url, authors, year, venue, cited_by, abstract) -> dict:
    abstract = re.sub(r"\s+", " ", abstract or "").strip()
    return {"title": re.sub(r"\s+", " ", title).strip(), "url": url, "authors": authors, "year": year,
            "venue": venue, "cited_by": cited_by, "abstract": abstract[:900], "snippet": abstract[:280]}


async def _openalex(query: str, limit: int) -> list[dict]:
    params = {
        "search": query,
        "per-page": limit,
        "filter": "has_abstract:true",
        "select": "id,title,doi,publication_year,authorships,abstract_inverted_index,primary_location,cited_by_count",
        "api_key": os.environ["OPENALEX_API_KEY"],
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(OPENALEX, params=params)
            r.raise_for_status()
            works = r.json().get("results", [])
    except httpx.HTTPStatusError as e:
        log.warning("OpenAlex HTTP %s for %r: %s", e.response.status_code, query, e.response.text[:200])
        return []
    except Exception as e:
        log.warning("OpenAlex request failed for %r: %r", query, e)
        return []

    papers = []
    for w in works:
        loc = w.get("primary_location") or {}
        url = w.get("doi") or loc.get("landing_page_url") or w.get("id")
        if not w.get("title") or not url:
            continue
        names = [(a.get("author") or {}).get("display_name") for a in w.get("authorships") or []]
        papers.append(_paper(w["title"], url, _authors(names), w.get("publication_year"),
                             (loc.get("source") or {}).get("display_name") or "",
                             w.get("cited_by_count"), _abstract(w.get("abstract_inverted_index"))))
    return papers


async def search_papers(query: str, limit: int = 5) -> list[dict]:
    global _warned_nokey
    if not os.getenv("OPENALEX_API_KEY"):
        if not _warned_nokey:
            _warned_nokey = True
            log.warning("OPENALEX_API_KEY is not set, so academic search is disabled. "
                        "Get a free key at openalex.org/settings/api.")
        return []
    return await _openalex(query, limit)
