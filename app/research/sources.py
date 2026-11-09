"""Source registry + citation helpers.

Every source (web page or paper) gets a global id. Search summaries carry [id]
markers, the writer reuses them, and finalize() renumbers them in reading order.
"""
import re
from dataclasses import dataclass, asdict
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode


def normalize_url(url: str) -> str:
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith("utm_")]
    return urlunparse(p._replace(query=urlencode(q), fragment=""))


@dataclass
class Source:
    id: int
    kind: str  # "web", "paper" or "doc" (local knowledge base)
    title: str
    url: str
    authors: str = ""
    year: int | None = None
    venue: str = ""
    cited_by: int | None = None
    snippet: str = ""
    page: int | None = None


class SourceRegistry:
    def __init__(self):
        self._by_url: dict[str, Source] = {}
        self._by_id: dict[int, Source] = {}

    def add(self, kind: str, title: str, url: str, **kw) -> Source:
        key = normalize_url(url)
        if key in self._by_url:
            return self._by_url[key]
        src = Source(id=len(self._by_id) + 1, kind=kind, title=title or urlparse(key).netloc, url=key, **kw)
        self._by_url[key] = src
        self._by_id[src.id] = src
        return src

    def get(self, sid: int) -> Source | None:
        return self._by_id.get(sid)


def cite_web_result(result, registry: SourceRegistry) -> str:
    """Rebuild a web-search answer with [id] markers inserted at each url_citation."""
    for item in result.new_items:
        if getattr(item, "type", "") != "message_output_item":
            continue
        chunks = []
        for part in getattr(item.raw_item, "content", []) or []:
            text = getattr(part, "text", None)
            if text is None:
                continue
            anns = [a for a in (getattr(part, "annotations", None) or [])
                    if getattr(a, "type", "") == "url_citation" and getattr(a, "url", None)]
            marks = []
            for a in anns:
                snippet = text[max(a.start_index, 0):a.end_index].strip()[:220]
                src = registry.add("web", getattr(a, "title", "") or "", a.url, snippet=snippet)
                if not src.snippet:
                    src.snippet = snippet
                marks.append((a.end_index, src.id))
            for end, sid in sorted(marks, key=lambda m: m[0], reverse=True):
                text = text[:end] + f"[{sid}]" + text[end:]
            chunks.append(text)
        if chunks:
            return "\n".join(chunks)
    return str(result.final_output)


_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\](?!\()")


def finalize(markdown: str, registry: SourceRegistry):
    """Renumber citations by first appearance, drop unknown ids, return used sources."""
    mapping: dict[int, int] = {}

    def repl(m):
        out = []
        for raw in re.findall(r"\d+", m.group(1)):
            old = int(raw)
            if registry.get(old) is None:
                continue  # hallucinated id
            mapping.setdefault(old, len(mapping) + 1)
            out.append(f"[{mapping[old]}]")
        return "".join(out)

    new_md = _CITE.sub(repl, markdown)
    sources = []
    for old, new in sorted(mapping.items(), key=lambda kv: kv[1]):
        d = asdict(registry.get(old))
        d.pop("id")
        d["n"] = new
        sources.append(d)
    return new_md, sources
