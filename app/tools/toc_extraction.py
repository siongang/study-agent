"""Orchestrator for textbook TOC extraction with manifest integration (Phase 4.5)."""
from pathlib import Path
from typing import Optional

from app.models.manifest import Manifest
from app.tools.manifest_io import load_manifest, save_manifest
from app.tools.text_extraction import load_extracted_text
from app.tools.toc_extract import extract_toc


def extract_all_textbook_tocs(
    manifest_path: Path,
    extracted_text_dir: Path,
    output_dir: Path,
    progress_callback: Optional[callable] = None,
    force: bool = False
) -> dict:
    """
    Extract TOC from all textbook documents.
    
    Updates manifest with derived artifact paths.
    Automatically retries failed extractions (where chapters list is empty).
    
    Args:
        manifest_path: Path to manifest.json
        extracted_text_dir: Directory with extracted text files
        output_dir: Directory to save textbook_metadata JSON files
        progress_callback: Optional callback(file_entry) for progress reporting
        force: If True, re-extract even if already successfully extracted
    
    Returns:
        dict with stats: {"extracted": int, "skipped": int, "failed": int, "total_chapters": int}
    """
    # Load manifest
    manifest = load_manifest(manifest_path)
    if manifest is None:
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Track stats
    stats = {"extracted": 0, "skipped": 0, "failed": 0, "total_chapters": 0}
    
    # Process each textbook file
    for file_entry in manifest.files:
        if file_entry.doc_type != "textbook":
            stats["skipped"] += 1
            continue
        
        if file_entry.status != "processed":
            stats["skipped"] += 1
            continue
        
        # Check if already extracted AND successful (artifact exists with chapters)
        toc_artifact = f"state/textbook_metadata/{file_entry.file_id}.json"
        if toc_artifact in file_entry.derived and not force:
            # Check if extraction was actually successful
            metadata_path = output_dir / f"{file_entry.file_id}.json"
            if metadata_path.exists():
                import json
                try:
                    existing_metadata = json.loads(metadata_path.read_text())
                    # If chapters exist, skip. If empty, re-extract (it failed before)
                    if existing_metadata.get("chapters"):
                        stats["skipped"] += 1
                        continue
                except:
                    pass  # Re-extract if we can't read the file
            # If we get here, either file doesn't exist or extraction failed - re-extract
        
        # If force flag is set, remove from derived so we re-add it after extraction
        if force and toc_artifact in file_entry.derived:
            file_entry.derived.remove(toc_artifact)
        
        # Report progress
        if progress_callback:
            progress_callback(file_entry)
        
        # Load extracted text
        extracted = load_extracted_text(file_entry.file_id, extracted_text_dir)
        if extracted is None:
            stats["failed"] += 1
            continue
        
        # Extract TOC using LLM
        metadata, error = extract_toc(
            file_id=file_entry.file_id,
            pages=extracted.pages,
            filename=file_entry.filename
        )
        
        if metadata is not None:
            # Save textbook metadata JSON
            output_path = output_dir / f"{file_entry.file_id}.json"
            output_path.write_text(metadata.model_dump_json(indent=2))
            
            # Update manifest entry
            if toc_artifact not in file_entry.derived:
                file_entry.derived.append(toc_artifact)
            
            stats["extracted"] += 1
            stats["total_chapters"] += len(metadata.chapters)
            
            if error:
                # Extraction succeeded but with warnings
                print(f"  Warning: {error}")
        else:
            stats["failed"] += 1
            # Optionally log error
            if hasattr(file_entry, 'error') and error:
                file_entry.error = f"TOC extraction: {error}"
    
    # Save updated manifest
    save_manifest(manifest, manifest_path)
    
    return stats


def extract_single_textbook_toc(
    file_id: str,
    manifest_path: Path,
    extracted_text_dir: Path,
    output_dir: Path
) -> Optional[dict]:
    """
    Extract TOC for a single textbook by file_id.
    
    Args:
        file_id: File ID to process
        manifest_path: Path to manifest.json
        extracted_text_dir: Directory with extracted text files
        output_dir: Directory to save textbook_metadata JSON files
    
    Returns:
        dict with result or None if file not found
    """
    # Load manifest
    manifest = load_manifest(manifest_path)
    if manifest is None:
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    
    # Find file entry
    file_entry = None
    for entry in manifest.files:
        if entry.file_id == file_id:
            file_entry = entry
            break
    
    if file_entry is None:
        print(f"Error: File ID {file_id} not found in manifest")
        return None
    
    if file_entry.doc_type != "textbook":
        print(f"Error: File {file_entry.filename} is not a textbook (type: {file_entry.doc_type})")
        return None
    
    if file_entry.status != "processed":
        print(f"Error: File {file_entry.filename} has not been processed (status: {file_entry.status})")
        return None
    
    # Load extracted text
    extracted = load_extracted_text(file_entry.file_id, extracted_text_dir)
    if extracted is None:
        print(f"Error: Extracted text not found for {file_entry.filename}")
        return None
    
    # Extract TOC
    print(f"Extracting TOC from: {file_entry.filename}")
    metadata, error = extract_toc(
        file_id=file_entry.file_id,
        pages=extracted.pages,
        filename=file_entry.filename
    )
    
    if metadata is not None:
        # Create output directory
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save textbook metadata JSON
        output_path = output_dir / f"{file_entry.file_id}.json"
        output_path.write_text(metadata.model_dump_json(indent=2))
        
        # Update manifest entry
        toc_artifact = f"state/textbook_metadata/{file_entry.file_id}.json"
        if toc_artifact not in file_entry.derived:
            file_entry.derived.append(toc_artifact)
        
        # Save updated manifest
        save_manifest(manifest, manifest_path)
        
        return {
            "filename": file_entry.filename,
            "toc_pages": metadata.toc_source_pages,
            "num_chapters": len(metadata.chapters),
            "page_range": (
                min(c.page_start for c in metadata.chapters) if metadata.chapters else None,
                max(c.page_end for c in metadata.chapters) if metadata.chapters else None
            ),
            "notes": metadata.notes
        }
    else:
        print(f"Error extracting TOC: {error}")
        return None
