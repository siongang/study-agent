"""Topic coverage extracted from syllabus/outline."""
from pydantic import BaseModel
from typing import Optional


class TopicRef(BaseModel):
    """A topic or section from coverage."""
    id: str
    title: str
    order: Optional[int] = None


class Coverage(BaseModel):
    """Coverage for a course or document."""
    source: str = ""
    topics: list[TopicRef] = []
