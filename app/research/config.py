import os

# Model used by the research agents (planner, searchers, writer). Must support OpenAI's hosted web search.
MODEL = os.getenv("RESEARCH_MODEL", "gpt-4o-mini")
