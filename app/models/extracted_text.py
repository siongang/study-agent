"""Extracted text model for cached PDF extractions (Phase 2)."""
from pydantic import BaseModel, Field


class ExtractedText(BaseModel):
    """Cached extracted text from a PDF file."""
    file_id: str
    path: str  # relative path from uploads/
    num_pages: int
    pages: list[str] = Field(default_factory=list)  # text per page
    full_text: str = ""  # concatenated all pages
    first_page: str = ""  # convenience field for first page
    extracted_at: str  # ISO timestamp
