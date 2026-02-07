"""Orchestrator for PDF text extraction with manifest integration (Phase 2)."""
import json
from pathlib import Path
from typing import Optional

from app.models.manifest import Manifest, ManifestFile
from app.models.extracted_text import ExtractedText
from app.tools.manifest_io import load_manifest, save_manifest
from app.tools.pdf_extract import extract_text_from_pdf


def extract_all_pending(
    uploads_dir: Path,
    manifest_path: Path,
    extracted_text_dir: Path,
    progress_callback: Optional[callable] = None
) -> dict:
    """
    Extract text from all PDFs with status in {"new", "stale"}.
    
    Updates manifest with:
    - derived artifact paths
    - status="processed" on success
    - status="error" + error message on failure
    
    Args:
        uploads_dir: Directory containing uploaded PDFs
        manifest_path: Path to manifest.json
        extracted_text_dir: Directory to save extracted text files
        progress_callback: Optional callback(file_entry) for progress reporting
    
    Returns:
        dict with stats: {"processed": int, "failed": int, "skipped": int}
    """
    # Load manifest
    manifest = load_manifest(manifest_path)
    if manifest is None:
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    
    # Create output directory
    extracted_text_dir.mkdir(parents=True, exist_ok=True)
    
    # Track stats
    stats = {"processed": 0, "failed": 0, "skipped": 0}
    
    # Process each file that needs extraction
    for file_entry in manifest.files:
        if file_entry.status not in ("new", "stale"):
            stats["skipped"] += 1
            continue
        
        # Report progress
        if progress_callback:
            progress_callback(file_entry)
        
        # Extract text
        file_path = uploads_dir / file_entry.path
        extracted, error = extract_text_from_pdf(
            file_path=file_path,
            file_id=file_entry.file_id,
            relative_path=file_entry.path
        )
        
        if extracted is not None:
            # Save extracted text
            output_path = extracted_text_dir / f"{file_entry.file_id}.json"
            _save_extracted_text(extracted, output_path)
            
            # Update manifest entry
            artifact_path = f"state/extracted_text/{file_entry.file_id}.json"
            if artifact_path not in file_entry.derived:
                file_entry.derived.append(artifact_path)
            file_entry.status = "processed"
            file_entry.error = None
            
            stats["processed"] += 1
        else:
            # Extraction failed
            file_entry.status = "error"
            file_entry.error = error or "Unknown extraction error"
            stats["failed"] += 1
    
    # Save updated manifest
    save_manifest(manifest, manifest_path)
    
    return stats


def _save_extracted_text(extracted: ExtractedText, output_path: Path) -> None:
    """Save ExtractedText to JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(extracted.model_dump_json(indent=2))


def load_extracted_text(file_id: str, extracted_text_dir: Path) -> Optional[ExtractedText]:
    """Load extracted text for a file_id. Returns None if not found."""
    path = extracted_text_dir / f"{file_id}.json"
    if not path.exists():
        return None
    
    try:
        data = json.loads(path.read_text())
        return ExtractedText(**data)
    except Exception:
        return None
