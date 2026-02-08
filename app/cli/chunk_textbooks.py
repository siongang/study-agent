"""CLI to chunk textbooks ONLY for required chapters (smart/fast chunking)."""
from pathlib import Path
import sys

from dotenv import load_dotenv
from tqdm import tqdm

from app.tools.manifest_io import load_manifest
from app.tools.chunk_store import save_chunks_jsonl, append_chunks_jsonl, build_chunk_index
from app.tools.smart_chunking import chunk_textbook_smart


def main():
    """Chunk only required chapters from textbooks (fast mode)."""
    print("="*60, flush=True)
    print("STARTING SMART CHUNKING CLI", flush=True)
    print("="*60, flush=True)
    
    print("\n[INIT] Loading environment...", flush=True)
    load_dotenv()
    
    print("[INIT] Setting up paths...", flush=True)
    project_root = Path(__file__).parent.parent.parent
    manifest_path = project_root / "storage" / "state" / "manifest.json"
    extracted_text_dir = project_root / "storage" / "state" / "extracted_text"
    textbook_metadata_dir = project_root / "storage" / "state" / "textbook_metadata"
    coverage_dir = project_root / "storage" / "state" / "coverage"
    chunks_output = project_root / "storage" / "state" / "chunks" / "chunks.jsonl"
    index_output = project_root / "storage" / "state" / "chunks" / "chunk_index.json"
    
    print(f"  - Project root: {project_root}", flush=True)
    print(f"  - Manifest: {manifest_path}", flush=True)
    print(f"  - Coverage dir: {coverage_dir}", flush=True)
    
    print(f"\n[CHECK] Manifest exists: {manifest_path.exists()}", flush=True)
    if not manifest_path.exists():
        print("Error: manifest.json not found. Run update_manifest first.", flush=True)
        sys.exit(1)
    
    print("[LOAD] Loading manifest...", flush=True)
    manifest = load_manifest(manifest_path)
    if manifest is None:
        print("Error: Failed to load manifest", flush=True)
        sys.exit(1)
    print(f"  ✓ Loaded {len(manifest.files)} files", flush=True)
    
    # Count textbooks
    print("\n[FILTER] Finding textbooks...", flush=True)
    textbooks = [
        f for f in manifest.files 
        if f.doc_type == "textbook" and f.status == "processed"
    ]
    print(f"  ✓ Found {len(textbooks)} textbooks:", flush=True)
    for i, tb in enumerate(textbooks):
        print(f"    {i+1}. {tb.filename[:60]}...", flush=True)
    
    if not textbooks:
        print("No textbook documents found.", flush=True)
        print("Run classify_docs first to identify textbooks.", flush=True)
        return
    
    print(f"\n{'='*60}", flush=True)
    print(f"Smart chunking {len(textbooks)} textbook(s) (only required chapters)...", flush=True)
    print(f"{'='*60}\n", flush=True)
    
    # Clear existing chunks file (rebuild)
    print("[SETUP] Clearing existing chunks...", flush=True)
    if chunks_output.exists():
        print(f"  - Removing old {chunks_output}", flush=True)
        chunks_output.unlink()
    
    print("[SETUP] Creating chunks directory...", flush=True)
    chunks_output.parent.mkdir(parents=True, exist_ok=True)
    
    stats = {
        "chunked": 0,
        "skipped": 0,
        "total_chunks": 0,
        "failed": 0,
        "with_toc": 0,
        "without_toc": 0
    }
    
    file_details = []
    
    print("\n[PROCESSING] Starting textbook chunking loop...\n", flush=True)
    
    for idx, file_entry in enumerate(textbooks):
        print(f"\n{'='*60}", flush=True)
        print(f"[{idx+1}/{len(textbooks)}] {file_entry.filename}", flush=True)
        print(f"{'='*60}", flush=True)
        sys.stdout.flush()
        
        try:
            print(f"[CALL] Calling chunk_textbook_smart()...", flush=True)
            print(f"  - file_id: {file_entry.file_id}", flush=True)
            print(f"  - filename: {file_entry.filename}", flush=True)
            sys.stdout.flush()
            
            # Smart chunk (only required chapters)
            chunks = chunk_textbook_smart(
                file_id=file_entry.file_id,
                extracted_text_dir=extracted_text_dir,
                textbook_metadata_dir=textbook_metadata_dir,
                coverage_dir=coverage_dir,
                filename=file_entry.filename,
                max_tokens=700,
                overlap_tokens=100
            )
            
            print(f"[RETURN] chunk_textbook_smart returned {len(chunks) if chunks else 0} chunks", flush=True)
            
            if not chunks:
                print(f"  ⚠ No chunks created", flush=True)
                stats["failed"] += 1
                continue
            
            print(f"[PROCESS] Processing {len(chunks)} chunks...", flush=True)
            
            # Track chapter metadata availability
            has_chapters = any(c.chapter_number is not None for c in chunks)
            if has_chapters:
                stats["with_toc"] += 1
            else:
                stats["without_toc"] += 1
            
            # Calculate chapter breakdown
            chapter_stats = {}
            
            for chunk in chunks:
                # Count by chapter (if available)
                if chunk.chapter_number is not None:
                    ch_key = f"Ch{chunk.chapter_number}"
                    chapter_stats[ch_key] = chapter_stats.get(ch_key, 0) + 1
            
            # Store details
            file_details.append({
                "filename": file_entry.filename,
                "num_chunks": len(chunks),
                "chapter_stats": chapter_stats,
                "has_chapters": has_chapters
            })
            
            # Append to master chunks file
            append_chunks_jsonl(chunks, chunks_output)
            
            # Update manifest
            chunks_artifact = "state/chunks/chunks.jsonl"
            if chunks_artifact not in file_entry.derived:
                file_entry.derived.append(chunks_artifact)
            
            stats["chunked"] += 1
            stats["total_chunks"] += len(chunks)
            
            print(f"  ✓ {len(chunks)} chunks created", flush=True)
            
        except Exception as e:
            print(f"\n[ERROR] Exception caught:", flush=True)
            print(f"  ✗ Error: {e}", flush=True)
            import traceback
            traceback.print_exc()
            sys.stdout.flush()
            stats["failed"] += 1
            continue
    
    # Save updated manifest
    print("\n[SAVE] Saving updated manifest...", flush=True)
    from app.tools.manifest_io import save_manifest
    save_manifest(manifest, manifest_path)
    print("  ✓ Manifest saved", flush=True)
    
    print("\n" + "="*60, flush=True)
    print("=== Chunking Summary ===", flush=True)
    print(f"Files chunked:    {stats['chunked']}")
    print(f"Total chunks:     {stats['total_chunks']}")
    print(f"Skipped:          {stats['skipped']}")
    print(f"Failed:           {stats['failed']}")
    print(f"With TOC data:    {stats['with_toc']}")
    print(f"Without TOC:      {stats['without_toc']}")
    
    # Show per-file breakdown
    if file_details:
        print("\n=== Per-File Details ===")
        for detail in file_details:
            print(f"\n{detail['filename']}")
            print(f"  * {detail['num_chunks']} chunks created")
            
            if detail['chapter_stats']:
                chapter_summary = ", ".join(
                    f"{ch}: {count}" 
                    for ch, count in sorted(detail['chapter_stats'].items(), key=lambda x: int(x[0][2:]))
                )
                print(f"  * Chapter breakdown: {chapter_summary}")
            else:
                print(f"  * No chapter metadata (TOC not available or not used)")
    
    if stats['total_chunks'] > 0:
        avg_chunks = stats['total_chunks'] / stats['chunked'] if stats['chunked'] > 0 else 0
        print(f"\nAverage chunks per file: {avg_chunks:.0f}")
        print(f"Chunks file: {chunks_output}")
        
        # Build chunk index
        print("\nBuilding chunk index...")
        build_chunk_index(chunks_output, index_output)
        print(f"Index saved: {index_output}")


if __name__ == "__main__":
    print(">>> ENTRY POINT REACHED <<<", flush=True)
    sys.stdout.flush()
    main()
    print("\n>>> SCRIPT COMPLETE <<<", flush=True)
    sys.stdout.flush()
