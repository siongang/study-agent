"""Study plan model."""
from pydantic import BaseModel
from typing import Optional


class PlanItem(BaseModel):
    """Single item in a study plan."""
    topic_id: str
    title: str
    priority: int = 0
    readiness: float = 0.0


class StudyPlan(BaseModel):
    """Generated study plan."""
    topics: list[PlanItem] = []
    priorities: dict[str, int] = {}
