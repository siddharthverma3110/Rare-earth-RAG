from pydantic import BaseModel, Field
from agents import Agent

from .config import MODEL

HOW_MANY_SEARCHES = 5
HOW_MANY_KB = 3

INSTRUCTIONS = (
    "You are a helpful research assistant. Given a query about rare earth elements and critical minerals, plan three kinds of searches:\n"
    f"1. web_searches: exactly {HOW_MANY_SEARCHES} general web search queries (news, reports, official sources, explainers).\n"
    f"2. academic_searches: exactly {HOW_MANY_SEARCHES} queries for an academic paper database. Write them as short "
    "keyword phrases of scholarly terminology (3-7 words, no questions, no operators) covering different angles "
    "such as mechanisms, methods, evidence, reviews and open problems.\n"
    f"3. kb_searches: exactly {HOW_MANY_KB} short keyword queries (2-5 words) for the user's own library of rare earth "
    "documents (production, reserves, prices, magnets, supply chains, processing, policy).\n"
    "For each query give a short reason it matters to the original question."
)


class WebSearchItem(BaseModel):
    reason: str = Field(description="Why this search is important to the query.")
    query: str = Field(description="The search term to use.")


class ResearchPlan(BaseModel):
    web_searches: list[WebSearchItem] = Field(description="General web searches.")
    academic_searches: list[WebSearchItem] = Field(description="Academic paper searches.")
    kb_searches: list[WebSearchItem] = Field(description="Searches of the internal document library.")


planner_agent = Agent(
    name="PlannerAgent",
    instructions=INSTRUCTIONS,
    model=MODEL,
    output_type=ResearchPlan,
)
