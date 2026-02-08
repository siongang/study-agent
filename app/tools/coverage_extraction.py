"""Orchestrator for exam coverage extraction with manifest integration (Phase 4)."""
from pathlib import Path
from typing import Optional

from app.models.manifest import Manifest
from app.tools.manifest_io import load_manifest, save_manifest
from app.tools.text_extraction import load_extracted_text
from app.tools.coverage_extract import extract_coverage


def extract_all_exam_overviews(
    manifest_path: Path,
    extracted_text_dir: Path,
    coverage_dir: Path,
    progress_callback: Optional[callable] = None
) -> dict:
    """
    Extract coverage from all exam_overview documents.
    
    Updates manifest with derived artifact paths.
    
    Args:
        manifest_path: Path to manifest.json
        extracted_text_dir: Directory with extracted text files
        coverage_dir: Directory to save coverage JSON files
        progress_callback: Optional callback(file_entry) for progress reporting
    
    Returns:
        dict with stats: {"extracted": int, "skipped": int, "failed": int}
    """
    # Load manifest
    manifest = load_manifest(manifest_path)
    if manifest is None:
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    
    # Create output directory
    coverage_dir.mkdir(parents=True, exist_ok=True)
    
    # Track stats
    stats = {"extracted": 0, "skipped": 0, "failed": 0}
    
    # Process each exam_overview file
    for file_entry in manifest.files:
        if file_entry.doc_type != "exam_overview":
            stats["skipped"] += 1
            continue
        
        if file_entry.status != "processed":
            stats["skipped"] += 1
            continue
        
        # Check if already extracted (artifact exists)
        coverage_artifact = f"state/coverage/{file_entry.file_id}.json"
        if coverage_artifact in file_entry.derived:
            stats["skipped"] += 1
            continue
        
        # Report progress
        if progress_callback:
            progress_callback(file_entry)
        
        # Load extracted text
        extracted = load_extracted_text(file_entry.file_id, extracted_text_dir)
        if extracted is None:
            stats["failed"] += 1
            continue
        
        # Extract coverage using LLM
        coverage, error = extract_coverage(
            full_text=extracted.full_text,
            filename=file_entry.filename,
            file_id=file_entry.file_id
        )
        
        if coverage is not None:
            # Save coverage JSON using file_id to avoid collisions
            output_path = coverage_dir / f"{file_entry.file_id}.json"
            output_path.write_text(coverage.model_dump_json(indent=2))
            
            # Update manifest entry
            if coverage_artifact not in file_entry.derived:
                file_entry.derived.append(coverage_artifact)
            
            stats["extracted"] += 1
        else:
            stats["failed"] += 1
            # Optionally log error
            if hasattr(file_entry, 'error'):
                file_entry.error = f"Coverage extraction: {error}"
    
    # Save updated manifest
    save_manifest(manifest, manifest_path)
    
    return stats
