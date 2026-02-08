"""Study plan model."""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class StudyResource(BaseModel):
    """Reference to study material."""
    source: str  # e.g., "textbook", "syllabus"
    file_id: str
    pages: Optional[list[int]] = None
    chapter: Optional[int] = None
    section: Optional[str] = None


class PracticeItem(BaseModel):
    """Practice question or exercise."""
    description: str  # e.g., "Review Questions 1-5"
    pages: Optional[list[int]] = None
    difficulty: Optional[str] = None  # "easy", "medium", "hard"


class StudyTopicItem(BaseModel):
    """Single topic in a study plan with resources."""
    topic_id: str
    topic_text: str  # The actual topic from coverage
    chapter: int
    chapter_title: str
    
    # Resources found via RAG
    textbook_resources: list[StudyResource] = Field(default_factory=list)
    practice_items: list[PracticeItem] = Field(default_factory=list)
    
    # Study metadata
    priority: int = 1  # 1=high, 2=medium, 3=low
    estimated_hours: Optional[float] = None
    notes: Optional[str] = None


class StudyPlan(BaseModel):
    """Complete study plan for an exam."""
    exam_id: str
    exam_name: str
    exam_date: Optional[str] = None
    course: Optional[str] = None
    
    study_topics: list[StudyTopicItem] = Field(default_factory=list)
    
    # Metadata
    generated_at: str
    total_topics: int = 0
    total_estimated_hours: Optional[float] = None
