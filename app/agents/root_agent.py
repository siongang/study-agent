"""Root agent: ADK entrypoint; routes to ingest, tutor, planner, verifier."""
from google.adk.agents.llm_agent import Agent

root_agent = Agent(
    model="gemini-2.5-flash",
    name="root_agent",
    description="A helpful assistant for study planning and tutoring.",
    instruction="Answer user questions and route to ingest, tutor, planner, or verifier as needed.",
)
