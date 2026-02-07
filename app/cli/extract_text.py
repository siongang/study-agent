"""CLI to extract text from PDFs with progress display (Phase 2)."""
from pathlib import Path
import sys

from tqdm import tqdm

from app.tools.text_extraction import extract_all_pending
from app.tools.manifest_io import load_manifest


def main():
    """Extract text from all pending PDFs and show progress."""
    # Get paths relative to project root
    project_root = Path(__file__).parent.parent.parent
    uploads_dir = project_root / "storage" / "uploads"
    manifest_path = project_root / "storage" / "state" / "manifest.json"
    extracted_text_dir = project_root / "storage" / "state" / "extracted_text"
    
    # Check if manifest exists
    if not manifest_path.exists():
        print("Error: manifest.json not found. Run update_manifest first.")
        sys.exit(1)
    
    # Load manifest to count pending files
    manifest = load_manifest(manifest_path)
    if manifest is None:
        print("Error: Failed to load manifest")
        sys.exit(1)
    
    pending_files = [f for f in manifest.files if f.status in ("new", "stale")]
    
    if not pending_files:
        print("No files to extract (all files already processed).")
        return
    
    print(f"Extracting text from {len(pending_files)} PDF(s)...\n")
    
    # Create progress bar
    pbar = tqdm(total=len(pending_files), desc="Extracting PDFs", unit="file")
    
    def progress_callback(file_entry):
        """Update progress bar with current file."""
        pbar.set_postfix_str(file_entry.filename[:40])
        pbar.update(1)
    
    # Extract all pending
    try:
        stats = extract_all_pending(
            uploads_dir=uploads_dir,
            manifest_path=manifest_path,
            extracted_text_dir=extracted_text_dir,
            progress_callback=progress_callback
        )
        
        pbar.close()
        
        # Print summary
        print("\n=== Extraction Summary ===")
        print(f"Successfully processed: {stats['processed']}")
        print(f"Failed:                 {stats['failed']}")
        print(f"Skipped:                {stats['skipped']}")
        
        # Show details of failed files if any
        if stats['failed'] > 0:
            manifest = load_manifest(manifest_path)
            failed = [f for f in manifest.files if f.status == "error"]
            print("\n=== Failed Files ===")
            for file in failed:
                print(f"  {file.filename}: {file.error}")
        
    except Exception as e:
        pbar.close()
        print(f"\nError during extraction: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
