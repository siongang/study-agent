"""Classify documents (e.g. syllabus, textbook, notes) for routing."""
from pathlib import Path


def classify_doc(path: str | Path, text_sample: str = "") -> str:
    """Return a simple label: syllabus, textbook, notes, other."""
    path = Path(path)
    name = path.name.lower()
    if "syllabus" in name or "overview" in name:
        return "syllabus"
    if "textbook" in name or "edition" in name or "chapter" in name:
        return "textbook"
    if "notes" in name or "summary" in name:
        return "notes"
    return "other"
