"""Pydantic models for textbook metadata and table of contents."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SectionInfo(BaseModel):
    """Information about a section/subsection within a chapter."""
    
    section: str = Field(..., description="Section number (e.g., '1.1', '1.2.3', 'A', etc.)")
    title: str = Field(..., description="Section title")
    page_start: int = Field(..., description="Starting page number of section")
    page_end: Optional[int] = Field(None, description="Ending page number (optional, inferred if not provided)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "section": "1.1",
                "title": "What is Statistics?",
                "page_start": 2,
                "page_end": 5
            }
        }


class ChapterInfo(BaseModel):
    """Information about a single chapter from textbook TOC."""
    
    chapter: int = Field(..., description="Chapter number (integer)")
    title: str = Field(..., description="Chapter title")
    page_start: int = Field(..., description="Starting page number of chapter")
    page_end: int = Field(..., description="Ending page number (exclusive)")
    sections: list[SectionInfo] = Field(default_factory=list, description="List of sections within chapter")
    
    class Config:
        json_schema_extra = {
            "example": {
                "chapter": 5,
                "title": "Causal Loop Diagrams",
                "page_start": 137,
                "page_end": 191,
                "sections": [
                    {
                        "section": "5.1",
                        "title": "Introduction",
                        "page_start": 137,
                        "page_end": 145
                    }
                ]
            }
        }


class TextbookMetadata(BaseModel):
    """Metadata for a textbook including table of contents."""
    
    file_id: str = Field(..., description="Unique file identifier")
    filename: str = Field(..., description="Original filename")
    doc_type: str = Field(default="textbook", description="Document type")
    extracted_at: datetime = Field(default_factory=datetime.now, description="Extraction timestamp")
    toc_source_pages: list[int] = Field(default_factory=list, description="Pages where TOC was found")
    chapters: list[ChapterInfo] = Field(default_factory=list, description="List of chapters")
    notes: str = Field(default="", description="Notes about extraction process")
    
    class Config:
        json_schema_extra = {
            "example": {
                "file_id": "17d50151-db40-466e-8791-9f869023eec4",
                "filename": "Sterman - Business Dynamics.pdf",
                "doc_type": "textbook",
                "extracted_at": "2026-02-08T01:23:45Z",
                "toc_source_pages": [17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28],
                "chapters": [
                    {
                        "chapter": 1,
                        "title": "Learning in and about Complex Systems",
                        "page_start": 3,
                        "page_end": 40
                    },
                    {
                        "chapter": 2,
                        "title": "System Dynamics in Action",
                        "page_start": 41,
                        "page_end": 82
                    }
                ],
                "notes": "TOC extracted successfully from pages 17-28"
            }
        }
