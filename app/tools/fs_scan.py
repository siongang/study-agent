"""Scan filesystem for uploads and compute SHA-256 hashes (Phase 1)."""
import hashlib
from pathlib import Path


def scan_uploads(uploads_dir: Path) -> list[dict]:
    """
    Scan uploads_dir recursively for PDF files and return file info.
    
    Returns list of dicts with:
        - path: str (relative to uploads_dir)
        - filename: str
        - sha256: str
        - size_bytes: int
        - modified_time: float (unix timestamp)
    """
    if not uploads_dir.is_dir():
        return []
    
    results = []
    for pdf_path in uploads_dir.rglob("*.pdf"):
        if not pdf_path.is_file():
            continue
        
        # Compute SHA-256
        sha256_hash = compute_sha256(pdf_path)
        
        # Get relative path from uploads_dir
        rel_path = pdf_path.relative_to(uploads_dir).as_posix()
        
        results.append({
            "path": rel_path,
            "filename": pdf_path.name,
            "sha256": sha256_hash,
            "size_bytes": pdf_path.stat().st_size,
            "modified_time": pdf_path.stat().st_mtime,
        })
    
    return results


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        # Read in chunks to handle large files
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()
