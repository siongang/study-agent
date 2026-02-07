"""Compute or estimate readiness per topic from chunks/scores."""
from typing import Any


def get_readiness(topic_id: str, store: Any = None) -> float:
    """Return a readiness score in [0, 1] for the topic. Stub."""
    return 0.0


def update_readiness(topic_id: str, score: float, store: Any = None) -> None:
    """Persist readiness for a topic. Stub."""
    pass
