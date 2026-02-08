"""Manifest of ingested documents and index state (Phase 1)."""
from pydantic import BaseModel, Field, field_validator
from typing import Literal


class ManifestFile(BaseModel):
    """Single file entry in the manifest."""
    file_id: str  # stable internal id, keep if unchanged
    path: str  # relative path from storage/uploads/
    filename: str
    sha256: str
    size_bytes: int
    modified_time: float  # unix timestamp
    doc_type: str = "unknown"
    status: Literal["new", "processed", "stale", "error"] = "new"
    derived: list[str] = Field(default_factory=list)  # derived artifact paths
    error: str | None = None  # optional error message for status="error"
    # Phase 3: classification metadata
    doc_confidence: float | None = None  # 0.0-1.0 confidence score
    doc_reasoning: str | None = None  # LLM reasoning for classification
    
    @field_validator('sha256')
    @classmethod
    def validate_sha256(cls, v: str) -> str:
        """Ensure SHA256 is valid hex string of correct length."""
        if len(v) != 64:
            raise ValueError('SHA256 must be 64 characters')
        if not all(c in '0123456789abcdef' for c in v.lower()):
            raise ValueError('SHA256 must be valid hex')
        return v.lower()
    
    @field_validator('size_bytes')
    @classmethod
    def validate_size(cls, v: int) -> int:
        """Ensure size is positive."""
        if v < 0:
            raise ValueError('size_bytes must be non-negative')
        return v
    
    @field_validator('doc_confidence')
    @classmethod
    def validate_confidence(cls, v: float | None) -> float | None:
        """Ensure confidence is between 0 and 1."""
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError('doc_confidence must be between 0.0 and 1.0')
        return v


class Manifest(BaseModel):
    """State of uploads and indexing."""
    version: int = 1
    last_scan: str  # ISO timestamp
    files: list[ManifestFile] = Field(default_factory=list)
