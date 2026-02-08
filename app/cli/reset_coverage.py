"""CLI tool to reset coverage extraction status in manifest."""
from pathlib import Path
import sys

from app.tools.manifest_io import load_manifest, save_manifest


def main():
    """Remove coverage artifacts from manifest derived arrays."""
    project_root = Path(__file__).parent.parent.parent
    manifest_path = project_root / "storage" / "state" / "manifest.json"
    
    if not manifest_path.exists():
        print("Error: manifest.json not found")
        sys.exit(1)
    
    manifest = load_manifest(manifest_path)
    if manifest is None:
        print("Error: Failed to load manifest")
        sys.exit(1)
    
    # Count files that will be reset
    reset_count = 0
    
    for file_entry in manifest.files:
        if file_entry.doc_type == "exam_overview":
            # Remove any coverage artifacts from derived list
            original_count = len(file_entry.derived)
            file_entry.derived = [
                artifact for artifact in file_entry.derived 
                if "coverage" not in artifact
            ]
            if len(file_entry.derived) < original_count:
                reset_count += 1
                print(f"Reset: {file_entry.filename}")
    
    if reset_count > 0:
        save_manifest(manifest, manifest_path)
        print(f"\n✓ Reset {reset_count} exam overview(s)")
        print("You can now run 'python -m app.cli.extract_coverage' again")
    else:
        print("No coverage artifacts found in manifest")


if __name__ == "__main__":
    main()
