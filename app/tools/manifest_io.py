"""Manifest I/O: load, save, and update logic (Phase 1)."""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import uuid

from app.models.manifest import Manifest, ManifestFile
from app.tools.fs_scan import scan_uploads


def load_manifest(manifest_path: Path) -> Optional[Manifest]:
    """Load manifest from JSON file. Returns None if not found or invalid."""
    if not manifest_path.exists():
        return None
    
    try:
        data = json.loads(manifest_path.read_text())
        return Manifest(**data)
    except Exception:
        return None


def save_manifest(manifest: Manifest, manifest_path: Path) -> None:
    """Save manifest to JSON file atomically (write temp then replace)."""
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to temp file first
    temp_path = manifest_path.with_suffix(".tmp")
    temp_path.write_text(manifest.model_dump_json(indent=2))
    
    # Atomic replace
    temp_path.replace(manifest_path)


def update_manifest(uploads_dir: Path, manifest_path: Path) -> dict:
    """
    Update manifest based on current files in uploads_dir.
    
    Returns summary dict with:
        - new: int (count of new files)
        - stale: int (count of changed files)
        - unchanged: int (count of unchanged files)
        - total: int (total files in manifest)
    """
    # Scan current files
    scanned_files = scan_uploads(uploads_dir)
    
    # Load existing manifest or create new one
    manifest = load_manifest(manifest_path)
    if manifest is None:
        manifest = Manifest(
            version=1,
            last_scan=datetime.now(timezone.utc).isoformat(),
            files=[]
        )
    
    # Build lookup: path -> ManifestFile
    existing_files = {f.path: f for f in manifest.files}
    
    # Track stats
    stats = {"new": 0, "stale": 0, "unchanged": 0}
    
    # Process scanned files
    updated_files = []
    for scan_info in scanned_files:
        path = scan_info["path"]
        sha256 = scan_info["sha256"]
        
        if path not in existing_files:
            # New file
            file_entry = ManifestFile(
                file_id=_generate_file_id(),
                path=path,
                filename=scan_info["filename"],
                sha256=sha256,
                size_bytes=scan_info["size_bytes"],
                modified_time=scan_info["modified_time"],
                doc_type="unknown",
                status="new",
                derived=[]
            )
            stats["new"] += 1
        else:
            # Existing file - check if changed
            existing = existing_files[path]
            if existing.sha256 != sha256:
                # File changed (stale)
                existing.sha256 = sha256
                existing.size_bytes = scan_info["size_bytes"]
                existing.modified_time = scan_info["modified_time"]
                existing.status = "stale"
                stats["stale"] += 1
            else:
                # Unchanged - preserve existing status
                stats["unchanged"] += 1
            file_entry = existing
        
        updated_files.append(file_entry)
    
    # Update manifest
    manifest.files = updated_files
    manifest.last_scan = datetime.now(timezone.utc).isoformat()
    
    # Save atomically
    save_manifest(manifest, manifest_path)
    
    stats["total"] = len(updated_files)
    return stats


def _generate_file_id() -> str:
    """Generate a stable file ID (UUID)."""
    return str(uuid.uuid4())
