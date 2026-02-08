"""Exam coverage models (Phase 4)."""
from pydantic import BaseModel, Field, field_validator


class ChapterTopic(BaseModel):
    """Topics for a specific chapter."""
    chapter: int
    chapter_title: str
    bullets: list[str] = Field(default_factory=list)


class ExamCoverage(BaseModel):
    """Structured exam coverage extracted from exam overview."""
    exam_id: str
    exam_name: str
    exam_date: str | None = None
    chapters: list[int] = Field(default_factory=list)
    topics: list[ChapterTopic] = Field(default_factory=list)
    source_file_id: str
    generated_at: str
    
    @field_validator('exam_id')
    @classmethod
    def normalize_exam_id(cls, v: str) -> str:
        """Normalize exam_id to lowercase with underscores."""
        return v.lower().replace(' ', '_').replace('-', '_')
    
    @field_validator('chapters')
    @classmethod
    def sort_chapters(cls, v: list[int]) -> list[int]:
        """Ensure chapters are sorted."""
        return sorted(set(v))  # Remove duplicates and sort
