from pydantic import BaseModel, Field
from agents import Agent

from .config import MODEL

INSTRUCTIONS = (
    "You are a senior researcher writing a cohesive, detailed report (at least 1000 words, markdown) for a research "
    "query about rare earth elements. You are given WEB SEARCH RESULTS and ACADEMIC PAPER RESULTS (from OpenAlex). "
    "Plan an outline first, then write the report with exactly these two top-level sections, using ## headings and "
    "no other top-level sections (no summary, synthesis or conclusion section):\n"
    "## Findings from Web Search - built only from the web search results.\n"
    "## Findings from Academic Papers - built only from the academic paper results; name the kind of evidence "
    "(review, experiment, model) and the year where it helps.\n\n"
    "CITATIONS: the research text contains markers like [12]. Cite in-text by placing the marker right after the "
    "claim it supports, exactly as written, using separate brackets for several sources, e.g. [3][8] (never [3, 8]). "
    "Only use markers that appear in the research text, never invent or alter numbers, and do not cite a source for "
    "something it does not support. Do not write a references or bibliography section; it is generated automatically. "
    "If one of the two sections has no results, say so briefly in that section instead of filling it from memory."
)


class ReportData(BaseModel):
    short_summary: str = Field(description="A short 2-3 sentence summary of the findings.")
    markdown_report: str = Field(description="The final report, with [n] citation markers.")
    follow_up_questions: list[str] = Field(description="Suggested topics to research further.")


writer_agent = Agent(
    name="WriterAgent",
    instructions=INSTRUCTIONS,
    model=MODEL,
    output_type=ReportData,
)
