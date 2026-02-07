"""Tutor agent: answers questions using RAG over ingested content."""
from google.adk.agents.llm_agent import Agent

tutor_agent = Agent(
    model="gemini-2.5-flash",
    name="tutor_agent",
    description="Answers questions using retrieved context from the vector store.",
    instruction="Use retrieve and readiness tools to answer user questions from ingested materials.",
)
