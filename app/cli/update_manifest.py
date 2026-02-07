"""CLI to update manifest from uploads directory (Phase 1)."""
from pathlib import Path
import sys

from app.tools.manifest_io import update_manifest, load_manifest


def main():
    """Update manifest and print summary."""
    # Get paths relative to project root
    project_root = Path(__file__).parent.parent.parent
    uploads_dir = project_root / "storage" / "uploads"
    manifest_path = project_root / "storage" / "state" / "manifest.json"
    
    # Check if uploads dir exists
    if not uploads_dir.exists():
        print(f"Error: uploads directory not found at {uploads_dir}")
        sys.exit(1)
    
    print(f"Scanning uploads: {uploads_dir}")
    print(f"Manifest: {manifest_path}")
    print()
    
    # Update manifest
    stats = update_manifest(uploads_dir, manifest_path)
    
    # Print summary
    print("=== Manifest Update Summary ===")
    print(f"New files:       {stats['new']}")
    print(f"Stale files:     {stats['stale']}")
    print(f"Unchanged files: {stats['unchanged']}")
    print(f"Total files:     {stats['total']}")
    print()
    
    # Show file details
    manifest = load_manifest(manifest_path)
    if manifest and manifest.files:
        print("=== Files ===")
        for file in manifest.files:
            status_marker = {
                "new": "[NEW]",
                "stale": "[STALE]",
                "processed": "[OK]",
                "error": "[ERROR]"
            }.get(file.status, f"[{file.status}]")
            print(f"{status_marker:10} {file.filename:50} ({file.doc_type})")
    
    print()
    print(f"Last scan: {manifest.last_scan if manifest else 'N/A'}")


if __name__ == "__main__":
    main()
