import asyncio

from agents import Runner, trace

from .. import rag
from .academic import search_papers
from .academic_agent import academic_agent
from .planner_agent import HOW_MANY_KB, HOW_MANY_SEARCHES, ResearchPlan, WebSearchItem, planner_agent
from .search_agent import search_agent
from .sources import SourceRegistry, cite_web_result, finalize
from .writer_agent import ReportData, writer_agent


class ResearchManager:
    async def run(self, query: str):
        """Yield ("status", text) events and finally ("report", {markdown, sources, follow_ups})."""
        registry = SourceRegistry()
        with trace("Research trace"):
            yield ("status", "Planning searches...")
            plan = await self.plan_searches(query)
            w, a, k = len(plan.web_searches), len(plan.academic_searches), len(plan.kb_searches)
            yield ("status", f"Planned {w + a + k} searches ({w} web, {a} academic, {k} library), running in parallel...")
            web, academic, kb = await asyncio.gather(
                self.perform_web(plan.web_searches, registry),
                self.perform_academic(plan.academic_searches, registry),
                self.perform_kb([query] + [i.query for i in plan.kb_searches], registry),
            )
            yield ("status", "Searches complete, writing report...")
            report = await self.write_report(query, kb, web, academic)
            markdown, sources = finalize(report.markdown_report, registry)
            yield ("report", {"markdown": markdown, "sources": sources, "follow_ups": report.follow_up_questions[:4]})

    async def plan_searches(self, query: str) -> ResearchPlan:
        result = await Runner.run(planner_agent, f"Query: {query}")
        plan = result.final_output_as(ResearchPlan)
        plan.web_searches = plan.web_searches[:HOW_MANY_SEARCHES]
        plan.academic_searches = plan.academic_searches[:HOW_MANY_SEARCHES]
        plan.kb_searches = plan.kb_searches[:HOW_MANY_KB]
        return plan

    async def perform_kb(self, queries: list[str], registry: SourceRegistry) -> list[str]:
        """Search the local document library (no LLM call: excerpts go straight to the writer)."""
        seen, lines = set(), []
        for q in queries:
            for c in rag.search(q, 3):
                if c["id"] in seen:
                    continue
                seen.add(c["id"])
                page = c.get("page")
                title = c["title"] + (f", p.{page}" if page else "")
                s = registry.add("doc", title, f"kb://{c['source']}/{page or 0}/{c['id']}", page=page, snippet=c["text"][:280])
                lines.append(f"[{s.id}] {title} ({c['source']})\n{c['text'][:700]}")
        return lines

    async def perform_web(self, items: list[WebSearchItem], registry: SourceRegistry) -> list[str]:
        results = await asyncio.gather(*(self.web_search(i, registry) for i in items))
        return [r for r in results if r]

    async def perform_academic(self, items: list[WebSearchItem], registry: SourceRegistry) -> list[str]:
        results = await asyncio.gather(*(self.academic_search(i, registry) for i in items))
        return [r for r in results if r]

    async def web_search(self, item: WebSearchItem, registry: SourceRegistry) -> str | None:
        prompt = f"Search term: {item.query}\nReason for searching: {item.reason}"
        try:
            result = await Runner.run(search_agent, prompt)
            return f"Search: {item.query}\n{cite_web_result(result, registry)}"
        except Exception:
            return None

    async def academic_search(self, item: WebSearchItem, registry: SourceRegistry) -> str | None:
        papers = await search_papers(item.query)
        if not papers:
            return None
        lines = []
        for p in papers:
            s = registry.add("paper", p["title"], p["url"], authors=p["authors"], year=p["year"],
                             venue=p["venue"], cited_by=p["cited_by"], snippet=p["snippet"])
            meta = ", ".join(str(x) for x in (p["authors"], p["year"], p["venue"]) if x)
            lines.append(f"[{s.id}] {s.title} ({meta})\nAbstract: {p['abstract']}")
        prompt = (f"Search term: {item.query}\nReason for searching: {item.reason}\n\nPapers:\n"
                  + "\n\n".join(lines))
        try:
            result = await Runner.run(academic_agent, prompt)
            return f"Search: {item.query}\n{result.final_output}"
        except Exception:
            return None

    async def write_report(self, query: str, kb: list[str], web: list[str], academic: list[str]) -> ReportData:
        prompt = (
            f"Original query: {query}\n\n"
            "## KNOWLEDGE BASE EXCERPTS\n" + ("\n\n".join(kb) or "(none: nothing relevant in the document library)") + "\n\n"
            "## WEB SEARCH RESULTS\n" + ("\n\n".join(web) or "(none)") + "\n\n"
            "## ACADEMIC PAPER RESULTS\n" + ("\n\n".join(academic) or "(none: the academic search service returned no papers or was unavailable)")
        )
        result = await Runner.run(writer_agent, prompt)
        return result.final_output_as(ReportData)
