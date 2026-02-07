"""Chunk and embedding models for RAG."""
from pydantic import BaseModel
from typing import Optional


class Chunk(BaseModel):
    """A text chunk with optional metadata."""
    id: str
    text: str
    source: str = ""
    start_token: Optional[int] = None
    end_token: Optional[int] = None


class ChunkWithEmbedding(Chunk):
    """Chunk plus its embedding vector."""
    embedding: list[float] = []
