"""Extracted text model for cached PDF extractions (Phase 2)."""
from pydantic import BaseModel, Field, field_validator


class ExtractedText(BaseModel):
    """Cached extracted text from a PDF file."""
    file_id: str
    path: str  # relative path from uploads/
    num_pages: int
    pages: list[str] = Field(default_factory=list)  # text per page
    full_text: str = ""  # concatenated all pages
    first_page: str = ""  # convenience field for first page
    extracted_at: str  # ISO timestamp
    
    @field_validator('num_pages')
    @classmethod
    def validate_num_pages(cls, v: int) -> int:
        """Ensure num_pages is non-negative."""
        if v < 0:
            raise ValueError('num_pages must be non-negative')
        return v
