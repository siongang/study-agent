"""CLI to extract exam coverage from exam overviews (Phase 4)."""
from pathlib import Path
import sys

from dotenv import load_dotenv
from tqdm import tqdm

from app.tools.coverage_extraction import extract_all_exam_overviews
from app.tools.manifest_io import load_manifest
from app.models.coverage import ExamCoverage


def main():
    """Extract coverage from all exam overview documents."""
    load_dotenv()
    
    project_root = Path(__file__).parent.parent.parent
    manifest_path = project_root / "storage" / "state" / "manifest.json"
    extracted_text_dir = project_root / "storage" / "state" / "extracted_text"
    coverage_dir = project_root / "storage" / "state" / "coverage"
    
    if not manifest_path.exists():
        print("Error: manifest.json not found. Run update_manifest first.")
        sys.exit(1)
    
    manifest = load_manifest(manifest_path)
    if manifest is None:
        print("Error: Failed to load manifest")
        sys.exit(1)
    
    exam_overviews = [
        f for f in manifest.files 
        if f.doc_type == "exam_overview" and f.status == "processed"
    ]
    
    if not exam_overviews:
        print("No exam overview documents found.")
        print("Run classify_docs first to identify exam overviews.")
        return
    
    # Check if already extracted
    needs_extraction = [
        f for f in exam_overviews
        if not any("coverage" in artifact for artifact in f.derived)
    ]
    
    if not needs_extraction:
        print("All exam overviews already have coverage extracted.")
        print("\nExisting coverage:")
        _show_coverage_summary(coverage_dir)
        return
    
    print(f"Extracting coverage from {len(needs_extraction)} exam overview(s)...\n")
    
    pbar = tqdm(total=len(needs_extraction), desc="Extracting coverage", unit="exam")
    
    def progress_callback(file_entry):
        pbar.set_postfix_str(file_entry.filename[:40])
        pbar.update(1)
    
    try:
        stats = extract_all_exam_overviews(
            manifest_path=manifest_path,
            extracted_text_dir=extracted_text_dir,
            coverage_dir=coverage_dir,
            progress_callback=progress_callback
        )
        
        pbar.close()
        
        print("\n=== Extraction Summary ===")
        print(f"Successfully extracted: {stats['extracted']}")
        print(f"Failed:                 {stats['failed']}")
        print(f"Skipped:                {stats['skipped']}")
        
        if stats['extracted'] > 0:
            print("\n=== Coverage Files ===")
            _show_coverage_summary(coverage_dir)
        
    except Exception as e:
        pbar.close()
        print(f"\nError during extraction: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _show_coverage_summary(coverage_dir: Path):
    """Display summary of extracted coverage files."""
    if not coverage_dir.exists():
        return
    
    for coverage_file in sorted(coverage_dir.glob("*.json")):
        try:
            coverage = ExamCoverage.model_validate_json(coverage_file.read_text())
            chapters_str = ", ".join(map(str, coverage.chapters))
            print(f"  [{coverage.exam_id:20}] {coverage.exam_name}")
            print(f"    Date: {coverage.exam_date or 'Not specified'}")
            print(f"    Chapters: {chapters_str}")
            print(f"    Topics: {len(coverage.topics)} chapters with details")
        except Exception:
            print(f"  [ERROR] Could not parse {coverage_file.name}")


if __name__ == "__main__":
    main()
