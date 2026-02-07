"""Planner agent: builds study plans from coverage and readiness."""
from google.adk.agents.llm_agent import Agent

planner_agent = Agent(
    model="gemini-2.5-flash",
    name="planner_agent",
    description="Creates study plans based on topic coverage and readiness.",
    instruction="Use coverage_extract, readiness, and study_plan tools to generate study plans.",
)
