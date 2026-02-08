"""Chunk model for document text chunks."""
from pydantic import BaseModel, Field
from typing import Optional, Literal
import hashlib


class Chunk(BaseModel):
    """Represents a chunk of text from a document."""
    chunk_id: str
    file_id: str
    filename: str
    text: str
    page_start: int  # 1-indexed
    page_end: int    # 1-indexed
    token_count: int
    section_type: Literal["explanation", "problems", "summary", "other"] = "other"
    chapter_number: Optional[int] = None
    chapter_title: Optional[str] = None
    chunk_index: int = 0
    
    @staticmethod
    def generate_chunk_id(file_id: str, page_start: int, page_end: int, chunk_index: int) -> str:
        """Generate deterministic chunk ID based on file and page range."""
        unique_str = f"{file_id}:{page_start}-{page_end}:{chunk_index}"
        return hashlib.sha1(unique_str.encode()).hexdigest()[:16]
