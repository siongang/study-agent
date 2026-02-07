"""Ingest agent: processes uploads, extracts text, chunks, and indexes."""
from google.adk.agents.llm_agent import Agent

ingest_agent = Agent(
    model="gemini-2.5-flash",
    name="ingest_agent",
    description="Processes documents: PDF extraction, chunking, embedding, and indexing.",
    instruction="Use fs_scan, pdf_extract, chunking, embed, and vector_store tools to ingest user content.",
)
