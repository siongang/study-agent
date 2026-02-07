"""Verifier agent: checks answers or plan compliance."""
from google.adk.agents.llm_agent import Agent

verifier_agent = Agent(
    model="gemini-2.5-flash",
    name="verifier_agent",
    description="Verifies user answers or plan adherence.",
    instruction="Use retrieve and readiness to verify answers against ingested content.",
)
