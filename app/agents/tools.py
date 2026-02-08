"""ADK tool wrappers for all Study Agent functionality.

Each tool is a Python function that wraps existing CLI/tool logic.
Tools are organized by agent ownership but all can be used by root_agent.
"""
from pathlib import Path
from datetime import date, timedelta
import json
import os
import logging
from typing import Literal, Optional

# Set up logging
logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Import all the core functionality
from app.tools.manifest_io import load_manifest, save_manifest, update_manifest
from app.tools.fs_scan import scan_uploads, compute_sha256
from app.tools.pdf_extract import extract_text_from_pdf
from app.tools.doc_classify import classify_document as classify_doc_llm
from app.tools.coverage_extract import extract_coverage as extract_coverage_llm
from app.tools.toc_extract import extract_toc
from app.tools.smart_chunking import chunk_textbook_smart
from app.tools.embed import embed_texts
from app.tools.embedding_cache import get_or_compute_embeddings
from app.tools.faiss_index import build_faiss_index, build_chunk_mapping, search_index, load_faiss_index, load_chunk_mapping, retrieve_chunks_with_text
from app.tools.rag_scout import enrich_coverage
from app.tools.study_planner import generate_multi_exam_plan
from app.tools.plan_export import export_to_markdown, export_to_csv, export_to_json
from app.tools.chunk_store import save_chunks_jsonl, load_chunks_jsonl, append_chunks_jsonl
from app.tools.intelligent_planner import analyze_study_load as analyze_load_impl, prioritize_topics as prioritize_impl

from app.models.manifest import Manifest, ManifestFile
from app.models.coverage import ExamCoverage
from app.models.enriched_coverage import EnrichedCoverage
from app.models.plan import StudyPlan


# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
UPLOADS_DIR = PROJECT_ROOT / "storage" / "uploads"
STATE_DIR = PROJECT_ROOT / "storage" / "state"


# ============================================================================
# INGEST AGENT TOOLS
# ============================================================================

def list_files() -> dict:
    """
    List all files in the manifest with their IDs, names, types, and statuses.
    Use this to see what files are available for processing.
    
    Returns:
        dict with:
        - status: "success" or "error"
        - files: list of file entries with file_id, filename, doc_type, status, size
        - total_files: total count
        - by_status: breakdown by status (new, processed, stale, error)
    """
    try:
        manifest_path = STATE_DIR / "manifest.json"
        manifest = load_manifest(manifest_path)
        
        if not manifest:
            return {
                "status": "success",
                "files": [],
                "total_files": 0,
                "by_status": {"new": 0, "processed": 0, "stale": 0, "error": 0},
                "message": "No files found. Upload PDFs to storage/uploads/ directory."
            }
        
        files = []
        by_status = {"new": 0, "processed": 0, "stale": 0, "error": 0}
        
        for file in manifest.files:
            file_info = {
                "file_id": file.file_id,
                "filename": file.filename,
                "doc_type": file.doc_type,
                "status": file.status,
                "size_mb": round(file.size_bytes / 1024 / 1024, 2)
            }
            files.append(file_info)
            by_status[file.status] = by_status.get(file.status, 0) + 1
        
        return {
            "status": "success",
            "files": files,
            "total_files": len(files),
            "by_status": by_status,
            "message": f"Found {len(files)} files. {by_status['new']} need processing."
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to list files: {str(e)}"
        }


def sync_files() -> dict:
    """
    Scan uploads directory and update manifest with new/modified files.
    Returns detailed file list so agent knows what to process.
    
    Returns:
        dict with:
        - status: "success" or "error"
        - new_files: list of new file entries (with file_id, filename, status)
        - updated_files: list of updated file entries
        - all_files: complete list of all files with IDs and statuses
        - total_files: total file count
        - message: summary message
    """
    try:
        logger.info("🔄 Syncing files from uploads directory...")
        manifest_path = STATE_DIR / "manifest.json"
        
        # Use the existing update_manifest logic
        stats = update_manifest(UPLOADS_DIR, manifest_path)
        logger.info(f"✅ Sync complete: {stats['new']} new, {stats['stale']} updated, {stats['unchanged']} unchanged")
        
        # Load manifest to get file details
        manifest = load_manifest(manifest_path)
        
        # Extract file details for agent to use
        all_files = []
        new_files = []
        updated_files = []
        
        for file in manifest.files:
            file_info = {
                "file_id": file.file_id,
                "filename": file.filename,
                "doc_type": file.doc_type,
                "status": file.status,
                "size_mb": round(file.size_bytes / 1024 / 1024, 2)
            }
            all_files.append(file_info)
            
            if file.status == "new":
                new_files.append(file_info)
            elif file.status == "stale":
                updated_files.append(file_info)
        
        return {
            "status": "success",
            "new_files": new_files,
            "updated_files": updated_files,
            "all_files": all_files,
            "total_files": len(all_files),
            "message": f"Found {len(new_files)} new files, {len(updated_files)} updated files, {stats['unchanged']} unchanged. Use file_id from the lists to process files."
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Sync failed: {str(e)}"
        }


def extract_text(file_id: str) -> dict:
    """
    Extract text from a PDF file and cache it.
    
    Args:
        file_id: File ID from manifest
        
    Returns:
        dict with:
        - status: "success" or "error"
        - file_id: the file ID
        - pages_extracted: number of pages
        - output_path: path to extracted text JSON
        - message: summary message
    """
    try:
        # Load manifest to get file path
        manifest = load_manifest(STATE_DIR / "manifest.json")
        file_entry = next((f for f in manifest.files if f.file_id == file_id), None)
        
        if not file_entry:
            return {
                "status": "error",
                "message": f"File {file_id} not found in manifest"
            }
        
        pdf_path = UPLOADS_DIR / file_entry.path
        output_path = STATE_DIR / "extracted_text" / f"{file_id}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check cache: skip if already extracted and status is processed
        if output_path.exists() and file_entry.status not in ["new", "stale"]:
            with open(output_path) as f:
                cached_data = json.load(f)
            logger.info(f"✓ Using cached extraction for {file_entry.filename}")
            return {
                "status": "success",
                "file_id": file_id,
                "pages_extracted": len(cached_data.get("pages", [])),
                "output_path": str(output_path),
                "message": f"Already extracted (cached) - {len(cached_data.get('pages', []))} pages",
                "cached": True
            }
        
        # Extract text
        logger.info(f"📄 Extracting text from {file_entry.filename}...")
        extracted_text, error = extract_text_from_pdf(pdf_path, file_id, file_entry.path)
        
        if error or not extracted_text:
            return {
                "status": "error",
                "message": f"Failed to extract text: {error or 'Unknown error'}"
            }
        
        logger.info(f"✅ Extracted {len(extracted_text.pages)} pages from {file_entry.filename}")
        
        # Save to cache
        with open(output_path, 'w') as f:
            json.dump(extracted_text.model_dump(mode='json'), f, indent=2, default=str)
        
        # Update manifest
        file_entry.status = "processed"
        if str(output_path.relative_to(PROJECT_ROOT)) not in file_entry.derived:
            file_entry.derived.append(str(output_path.relative_to(PROJECT_ROOT)))
        save_manifest(manifest, STATE_DIR / "manifest.json")
        
        return {
            "status": "success",
            "file_id": file_id,
            "pages_extracted": len(extracted_text.pages),
            "output_path": str(output_path),
            "message": f"Extracted {len(extracted_text.pages)} pages"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Text extraction failed: {str(e)}"
        }


def classify_document(file_id: str) -> dict:
    """
    Classify a document as textbook, exam_overview, or syllabus.
    
    Args:
        file_id: File ID from manifest
        
    Returns:
        dict with:
        - status: "success" or "error"
        - file_id: the file ID
        - doc_type: "textbook", "exam_overview", or "syllabus"
        - confidence: 0.0-1.0
        - reasoning: explanation
        - message: summary message
    """
    try:
        # Load manifest FIRST to get file_entry
        manifest = load_manifest(STATE_DIR / "manifest.json")
        file_entry = next((f for f in manifest.files if f.file_id == file_id), None)
        if not file_entry:
            return {
                "status": "error",
                "message": f"File {file_id} not found in manifest"
            }
        
        # Load extracted text
        text_path = STATE_DIR / "extracted_text" / f"{file_id}.json"
        if not text_path.exists():
            return {
                "status": "error",
                "message": f"Extracted text not found for {file_id}. Run extract_text first."
            }
        
        with open(text_path) as f:
            extracted_text_data = json.load(f)
        
        # Classify using LLM (now file_entry.filename is available)
        result = classify_doc_llm(
            first_page=extracted_text_data.get("first_page", ""),
            filename=file_entry.filename,
            full_text_sample=extracted_text_data.get("full_text", "")[:2000]
        )
        
        doc_type = result["doc_type"]
        confidence = result["confidence"]
        reasoning = result["reasoning"]
        
        # Update manifest with classification results
        file_entry.doc_type = doc_type
        file_entry.doc_confidence = confidence
        file_entry.doc_reasoning = reasoning
        save_manifest(manifest, STATE_DIR / "manifest.json")
        
        return {
            "status": "success",
            "file_id": file_id,
            "doc_type": doc_type,
            "confidence": confidence,
            "reasoning": reasoning,
            "message": f"Classified as {doc_type} (confidence: {confidence:.2f})"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Classification failed: {str(e)}"
        }


def extract_toc_tool(file_id: str) -> dict:
    """
    Extract table of contents from a textbook.
    
    Args:
        file_id: Textbook file ID
        
    Returns:
        dict with:
        - status: "success" or "error"
        - file_id: the file ID
        - chapters: list of chapter dicts
        - output_path: path to TOC JSON
        - message: summary message
    """
    try:
        # Load extracted text
        text_path = STATE_DIR / "extracted_text" / f"{file_id}.json"
        if not text_path.exists():
            return {
                "status": "error",
                "message": f"Extracted text not found for {file_id}"
            }
        
        with open(text_path) as f:
            extracted_text_data = json.load(f)
        
        # Get file entry for filename
        manifest = load_manifest(STATE_DIR / "manifest.json")
        file_entry = next((f for f in manifest.files if f.file_id == file_id), None)
        if not file_entry:
            return {"status": "error", "message": f"File {file_id} not found in manifest"}
        
        # Validate prerequisite: doc_type must be textbook
        if file_entry.doc_type != "textbook":
            return {
                "status": "error",
                "message": f"Cannot extract TOC: doc_type is '{file_entry.doc_type}', expected 'textbook'. Run classify_document first."
            }
        
        # Check cache: skip if TOC already extracted and status is processed
        output_path = STATE_DIR / "textbook_metadata" / f"{file_id}.json"
        if output_path.exists() and file_entry.status not in ["new", "stale"]:
            with open(output_path) as f:
                cached_toc = json.load(f)
            logger.info(f"✓ Using cached TOC for {file_entry.filename}")
            return {
                "status": "success",
                "file_id": file_id,
                "chapters": cached_toc.get("chapters", []),
                "output_path": str(output_path),
                "message": f"Already extracted (cached) - {len(cached_toc.get('chapters', []))} chapters",
                "cached": True
            }
        
        # Extract TOC
        toc_metadata, error = extract_toc(
            file_id=file_id,
            pages=extracted_text_data.get("pages", []),
            filename=file_entry.filename,
            max_toc_pages=30
        )
        
        if error or not toc_metadata:
            return {
                "status": "error",
                "message": f"TOC extraction failed: {error or 'Unknown error'}"
            }
        
        # Save TOC
        output_path = STATE_DIR / "textbook_metadata" / f"{file_id}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(toc_metadata.model_dump(mode='json'), f, indent=2, default=str)
        
        # Update manifest (already loaded above)
        if str(output_path.relative_to(PROJECT_ROOT)) not in file_entry.derived:
            file_entry.derived.append(str(output_path.relative_to(PROJECT_ROOT)))
        save_manifest(manifest, STATE_DIR / "manifest.json")
        
        return {
            "status": "success",
            "file_id": file_id,
            "chapters": [ch.model_dump() for ch in toc_metadata.chapters],
            "output_path": str(output_path),
            "message": f"Extracted {len(toc_metadata.chapters)} chapters"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"TOC extraction failed: {str(e)}"
        }


def chunk_textbook(file_id: str) -> dict:
    """
    Chunk a textbook into semantic units with chapter metadata.
    
    Args:
        file_id: Textbook file ID
        
    Returns:
        dict with:
        - status: "success" or "error"
        - file_id: the file ID
        - chunks_created: number of chunks
        - output_path: path to chunks JSONL
        - message: summary message
    """
    try:
        # Get file entry for filename
        manifest = load_manifest(STATE_DIR / "manifest.json")
        if not manifest:
            return {"status": "error", "message": "Manifest not found"}
        
        file_entry = next((f for f in manifest.files if f.file_id == file_id), None)
        if not file_entry:
            return {"status": "error", "message": f"File {file_id} not found in manifest"}
        
        # Check if extracted text exists
        text_path = STATE_DIR / "extracted_text" / f"{file_id}.json"
        if not text_path.exists():
            return {"status": "error", "message": f"Extracted text not found for {file_id}. Run extract_text first."}
        
        # Validate prerequisite: doc_type must be textbook
        if file_entry.doc_type != "textbook":
            return {
                "status": "error",
                "message": f"Cannot chunk: doc_type is '{file_entry.doc_type}', expected 'textbook'. Only textbooks can be chunked."
            }
        
        # Validate prerequisite: TOC metadata should exist (optional but recommended)
        toc_path = STATE_DIR / "textbook_metadata" / f"{file_id}.json"
        if not toc_path.exists():
            logger.warning(f"⚠️  No TOC metadata found for {file_entry.filename}. Will use semantic chunking without chapter boundaries.")
        
        # Check cache: skip if already chunked and status is processed
        chunks_path = STATE_DIR / "chunks" / "chunks.jsonl"
        if chunks_path.exists() and file_entry.status not in ["new", "stale"]:
            # Check if this file already has chunks
            existing_chunks = load_chunks_jsonl(chunks_path)
            file_chunks = [c for c in existing_chunks if c.get("file_id") == file_id]
            if file_chunks:
                logger.info(f"✓ Using cached chunks for {file_entry.filename}")
                return {
                    "status": "success",
                    "file_id": file_id,
                    "chunks_created": len(file_chunks),
                    "output_path": str(chunks_path),
                    "message": f"Already chunked (cached) - {len(file_chunks)} chunks",
                    "cached": True
                }
        
        # Chunk using smart chunking (handles TOC if available, falls back to semantic chunking)
        extracted_text_dir = STATE_DIR / "extracted_text"
        textbook_metadata_dir = STATE_DIR / "textbook_metadata"
        coverage_dir = STATE_DIR / "coverage"
        
        chunks = chunk_textbook_smart(
            file_id=file_id,
            extracted_text_dir=extracted_text_dir,
            textbook_metadata_dir=textbook_metadata_dir,
            coverage_dir=coverage_dir,
            filename=file_entry.filename,
            target_tokens=700,
            max_tokens=900,
            overlap_tokens=100
        )
        
        # Save chunks
        chunks_dir = STATE_DIR / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)
        chunks_path = chunks_dir / "chunks.jsonl"
        
        # Append to existing chunks file
        append_chunks_jsonl(chunks, chunks_path)
        
        # Update manifest
        derived_path = str(chunks_path.relative_to(PROJECT_ROOT))
        if derived_path not in file_entry.derived:
            file_entry.derived.append(derived_path)
        save_manifest(manifest, STATE_DIR / "manifest.json")
        
        return {
            "status": "success",
            "file_id": file_id,
            "chunks_created": len(chunks),
            "output_path": str(chunks_path),
            "message": f"Created {len(chunks)} chunks"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Chunking failed: {str(e)}"
        }


def build_index() -> dict:
    """
    Generate embeddings for all chunks and build FAISS index.
    
    Returns:
        dict with:
        - status: "success" or "error"
        - total_chunks: number of chunks indexed
        - index_path: path to FAISS index
        - mapping_path: path to row-to-chunk mapping
        - message: summary message
    """
    try:
        chunks_path = STATE_DIR / "chunks" / "chunks.jsonl"
        if not chunks_path.exists():
            return {
                "status": "error",
                "message": "No chunks found. Run chunk_textbook first."
            }
        
        # Load chunks
        chunks = load_chunks_jsonl(chunks_path)
        logger.info(f"📦 Loaded {len(chunks)} chunks from {chunks_path}")
        
        # Validate prerequisite: at least one chunk must exist
        if not chunks or len(chunks) == 0:
            return {
                "status": "error",
                "message": "No chunks loaded. Ensure textbooks are chunked before building index."
            }
        
        # Generate embeddings with caching
        cache_dir = STATE_DIR / "embeddings"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"🔮 Computing embeddings for {len(chunks)} chunks (using cache)...")
        
        # Define embedding function
        def embed_fn(texts):
            return embed_texts(
                texts,
                model="gemini-embedding-001",
                task_type="RETRIEVAL_DOCUMENT",
                batch_size=100
            )
        
        # Get or compute embeddings with cache
        embeddings, stats = get_or_compute_embeddings(
            chunks=chunks,
            cache_dir=cache_dir,
            embed_function=embed_fn,
            show_progress=False
        )
        
        logger.info(f"✅ Embeddings ready: {stats['total']} total ({stats['cached']} cached, {stats['computed']} computed)")
        
        # Build index
        index_dir = STATE_DIR / "index"
        index_dir.mkdir(parents=True, exist_ok=True)
        index_path = index_dir / "faiss.index"
        mapping_path = index_dir / "row_to_chunk_id.json"
        
        logger.info("🏗️  Building FAISS index...")
        build_faiss_index(embeddings, index_path, normalize=True)
        
        logger.info("🗺️  Building chunk mapping...")
        build_chunk_mapping(chunks, mapping_path)
        
        logger.info(f"✅ Index built successfully: {len(chunks)} chunks indexed")
        
        return {
            "status": "success",
            "total_chunks": len(chunks),
            "index_path": str(index_path),
            "mapping_path": str(mapping_path),
            "message": f"Indexed {len(chunks)} chunks"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Index building failed: {str(e)}"
        }


# ============================================================================
# PLANNER AGENT TOOLS
# ============================================================================

def get_current_date() -> dict:
    """
    Get the current date and time information.
    
    Returns:
        dict with:
        - status: "success"
        - today: current date in YYYY-MM-DD format
        - day_of_week: name of the day (Monday, Tuesday, etc.)
        - message: human-readable current date
    """
    today = date.today()
    day_name = today.strftime("%A")
    
    return {
        "status": "success",
        "today": today.isoformat(),
        "day_of_week": day_name,
        "message": f"Today is {day_name}, {today.strftime('%B %d, %Y')}"
    }


def extract_coverage(file_id: str) -> dict:
    """
    Extract exam coverage from an exam overview PDF.
    
    Args:
        file_id: Exam overview file ID
        
    Returns:
        dict with:
        - status: "success" or "error"
        - exam_id: extracted exam ID
        - exam_name: exam name
        - chapters: list of chapters covered
        - total_topics: count of learning objectives
        - output_path: path to coverage JSON
        - message: summary message
    """
    try:
        # Load extracted text
        text_path = STATE_DIR / "extracted_text" / f"{file_id}.json"
        if not text_path.exists():
            return {"status": "error", "message": f"Extracted text not found for {file_id}"}
        
        with open(text_path) as f:
            extracted_text_data = json.load(f)
        
        # Get file entry for filename
        manifest = load_manifest(STATE_DIR / "manifest.json")
        file_entry = next((f for f in manifest.files if f.file_id == file_id), None)
        if not file_entry:
            return {"status": "error", "message": f"File {file_id} not found in manifest"}
        
        # Validate prerequisite: doc_type should be exam_overview
        if file_entry.doc_type not in ["exam_overview", "unknown"]:
            return {
                "status": "error",
                "message": f"Cannot extract coverage: doc_type is '{file_entry.doc_type}', expected 'exam_overview'. This tool is for exam overview documents."
            }
        
        # Extract coverage
        coverage, error = extract_coverage_llm(
            full_text=extracted_text_data.get("full_text", ""),
            filename=file_entry.filename,
            file_id=file_id,
            max_chars=8000
        )
        
        if error or not coverage:
            return {"status": "error", "message": f"Coverage extraction failed: {error or 'Unknown error'}"}
        
        # Save coverage
        coverage_dir = STATE_DIR / "coverage"
        coverage_dir.mkdir(parents=True, exist_ok=True)
        coverage_path = coverage_dir / f"{file_id}.json"
        
        with open(coverage_path, 'w') as f:
            json.dump(coverage.model_dump(mode='json'), f, indent=2, default=str)
        
        # Update manifest (already loaded above)
        derived_path = str(coverage_path.relative_to(PROJECT_ROOT))
        if derived_path not in file_entry.derived:
            file_entry.derived.append(derived_path)
        save_manifest(manifest, STATE_DIR / "manifest.json")
        
        total_topics = sum(len(ch.bullets) for ch in coverage.topics)
        
        return {
            "status": "success",
            "exam_id": coverage.exam_id,
            "exam_name": coverage.exam_name,
            "chapters": coverage.chapters,
            "total_topics": total_topics,
            "output_path": str(coverage_path),
            "message": f"Extracted {total_topics} topics across {len(coverage.chapters)} chapters"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Coverage extraction failed: {str(e)}"
        }


def _update_manifest_enriched(manifest_path: Path, exam_file_id: str, enriched_artifact: str) -> None:
    """Add enriched coverage artifact to manifest for the given file_id if present."""
    manifest = load_manifest(manifest_path)
    if manifest is None:
        return
    updated = False
    for file_entry in manifest.files:
        if file_entry.file_id == exam_file_id:
            if enriched_artifact not in file_entry.derived:
                file_entry.derived.append(enriched_artifact)
                updated = True
            break
    if updated:
        save_manifest(manifest, manifest_path)


def enrich_coverage_tool(exam_file_id: str, force: bool = False) -> dict:
    """
    Enrich exam coverage with textbook evidence via RAG.
    
    Args:
        exam_file_id: Exam overview file ID
        force: Recompute even if enriched coverage already exists
        
    Returns:
        dict with:
        - status: "success" or "error"
        - exam_id: exam ID
        - total_topics: number of topics enriched
        - high_confidence_count: topics with confidence >= 0.75
        - medium_confidence_count: topics with 0.6 <= confidence < 0.75
        - low_confidence_count: topics with confidence < 0.6
        - output_path: path to enriched coverage JSON
        - message: summary message
    """
    try:
        manifest_path = STATE_DIR / "manifest.json"
        enriched_dir = STATE_DIR / "enriched_coverage"
        enriched_path = enriched_dir / f"{exam_file_id}.json"
        enriched_artifact = f"storage/state/enriched_coverage/{exam_file_id}.json"

        # Short-circuit if enriched coverage already exists (unless forced)
        if enriched_path.exists() and not force:
            try:
                with open(enriched_path) as f:
                    enriched_data = json.load(f)
                enriched = EnrichedCoverage(**enriched_data)
                _update_manifest_enriched(manifest_path, exam_file_id, enriched_artifact)
                return {
                    "status": "success",
                    "exam_id": enriched.exam_id,
                    "total_topics": enriched.total_topics,
                    "high_confidence_count": enriched.high_confidence_count,
                    "medium_confidence_count": enriched.medium_confidence_count,
                    "low_confidence_count": enriched.low_confidence_count,
                    "output_path": str(enriched_path),
                    "message": f"Enriched coverage already exists for {exam_file_id}. Skipping recompute."
                }
            except Exception as e:
                logger.warning("Failed to load cached enriched coverage for %s: %s", exam_file_id, e)

        # Load coverage
        coverage_path = STATE_DIR / "coverage" / f"{exam_file_id}.json"
        if not coverage_path.exists():
            return {"status": "error", "message": f"Coverage not found for {exam_file_id}. Run extract_coverage first."}
        
        with open(coverage_path) as f:
            coverage_data = json.load(f)
        coverage = ExamCoverage(**coverage_data)
        
        # Check index exists
        index_path = STATE_DIR / "index" / "faiss.index"
        mapping_path = STATE_DIR / "index" / "row_to_chunk_id.json"
        chunks_path = STATE_DIR / "chunks" / "chunks.jsonl"
        
        if not index_path.exists():
            return {"status": "error", "message": "FAISS index not found. Run build_index first."}
        
        # Enrich coverage
        print(f"Enriching {coverage.exam_name}...")
        enriched = enrich_coverage(
            coverage=coverage,
            index_path=index_path,
            mapping_path=mapping_path,
            chunks_path=chunks_path,
            top_k=10,
            min_score=0.6,
            use_chapter_filter=True
        )
        
        # Save enriched coverage
        enriched_dir.mkdir(parents=True, exist_ok=True)
        
        with open(enriched_path, 'w') as f:
            json.dump(enriched.model_dump(mode='json'), f, indent=2, default=str)

        _update_manifest_enriched(manifest_path, exam_file_id, enriched_artifact)
        
        return {
            "status": "success",
            "exam_id": enriched.exam_id,
            "total_topics": enriched.total_topics,
            "high_confidence_count": enriched.high_confidence_count,
            "medium_confidence_count": enriched.medium_confidence_count,
            "low_confidence_count": enriched.low_confidence_count,
            "output_path": str(enriched_path),
            "message": f"Enriched {enriched.total_topics} topics: {enriched.high_confidence_count} high confidence, {enriched.low_confidence_count} low confidence"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Enrichment failed: {str(e)}"
        }


def analyze_study_load(
    exam_file_ids: list[str],
    start_date: str,
    end_date: str,
    minutes_per_day: int = 90
) -> dict:
    """
    Analyze study workload and feasibility before creating a plan.
    
    Args:
        exam_file_ids: List of exam file IDs
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        minutes_per_day: Target study minutes per day
        
    Returns:
        dict with:
        - status: "success" or "error"
        - total_topics: Number of topics
        - total_time_needed_hours: Estimated hours needed
        - time_available_hours: Hours available
        - feasibility: "comfortable" | "realistic" | "tight" | "impossible"
        - recommendation: Suggested strategy
        - message: Summary message
    """
    try:
        enriched_dir = STATE_DIR / "enriched_coverage"
        
        enriched_paths = []
        for exam_id in exam_file_ids:
            path = enriched_dir / f"{exam_id}.json"
            if not path.exists():
                return {
                    "status": "error",
                    "message": f"Enriched coverage not found for {exam_id}. Run enrich_coverage_tool first."
                }
            enriched_paths.append(path)
        
        # Parse dates
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        
        # Analyze
        analysis = analyze_load_impl(enriched_paths, start, end, minutes_per_day)
        
        # Format message
        feasibility_emoji = {
            "comfortable": "✅",
            "realistic": "👍",
            "tight": "⚠️",
            "impossible": "❌"
        }
        emoji = feasibility_emoji.get(analysis["feasibility"], "")
        
        message = f"{emoji} {analysis['feasibility'].title()}: Need {analysis['total_time_needed_hours']}h, have {analysis['time_available_hours']}h available ({analysis['coverage_percentage']}% coverage)"
        
        return {
            "status": "success",
            **analysis,
            "message": message
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Analysis failed: {str(e)}"
        }


def generate_plan(
    exam_file_ids: list[str],
    start_date: str,
    end_date: str,
    minutes_per_day: int = 90,
    strategy: Literal["round_robin", "priority_first", "balanced"] = "balanced",
    generate_questions: bool = True
) -> dict:
    """
    Generate a multi-exam interleaved study plan.
    
    Args:
        exam_file_ids: List of exam file IDs
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        minutes_per_day: Target study minutes per day
        strategy: Scheduling strategy
        generate_questions: Whether to generate study questions
        
    Returns:
        dict with:
        - status: "success" or "error"
        - plan_id: generated plan ID
        - total_days: number of study days
        - total_hours: total study hours
        - total_topics: number of topics
        - output_path: path to plan JSON
        - message: summary message
    """
    try:
        # Validate enriched coverage exists for all exams
        enriched_paths = []
        for exam_id in exam_file_ids:
            enriched_path = STATE_DIR / "enriched_coverage" / f"{exam_id}.json"
            if not enriched_path.exists():
                return {
                    "status": "error",
                    "message": f"Enriched coverage not found for {exam_id}. Run enrich_coverage_tool first."
                }
            enriched_paths.append(enriched_path)
        
        # Parse dates
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        
        # Generate plan
        print(f"Generating study plan for {len(exam_file_ids)} exam(s)...")
        plan = generate_multi_exam_plan(
            enriched_coverage_paths=enriched_paths,
            start_date=start,
            end_date=end,
            minutes_per_day=minutes_per_day,
            strategy=strategy,
            generate_questions=generate_questions
        )
        
        # Save plan
        plans_dir = STATE_DIR / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plans_dir / f"{plan.plan_id}.json"
        
        with open(plan_path, 'w') as f:
            json.dump(plan.model_dump(mode='json'), f, indent=2, default=str)
        
        return {
            "status": "success",
            "plan_id": plan.plan_id,
            "total_days": plan.total_days,
            "total_hours": plan.total_study_hours,
            "total_topics": plan.total_topics,
            "output_path": str(plan_path),
            "message": f"Created {plan.total_days}-day plan with {plan.total_topics} topics ({plan.total_study_hours:.1f} hours)"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Plan generation failed: {str(e)}"
        }


def generate_smart_plan(
    exam_file_ids: list[str],
    start_date: str,
    end_date: str,
    minutes_per_day: int = 90,
    priority_strategy: Literal["comprehensive", "balanced", "prioritized", "cramming"] = "balanced",
    scheduling_strategy: Literal["round_robin", "priority_first", "balanced"] = "priority_first",
    generate_questions: bool = True
) -> dict:
    """
    Generate an intelligent study plan with LLM-powered topic prioritization.
    
    This version uses LLM to analyze topic importance and assign priorities (critical/high/medium/low/optional).
    All topics are included in the plan but tagged by priority for flexible studying.
    
    Args:
        exam_file_ids: List of exam file IDs
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        minutes_per_day: Target study minutes per day
        priority_strategy: How to prioritize topics:
            - "comprehensive": Study everything thoroughly
            - "balanced": Mix of depth and breadth (default)
            - "prioritized": Focus on high-value topics
            - "cramming": Only critical must-know topics
        scheduling_strategy: How to schedule topics (default: "priority_first")
        generate_questions: Whether to generate study questions
        
    Returns:
        dict with:
        - status: "success" or "error"
        - plan_id: generated plan ID
        - total_days: number of study days
        - total_hours: total study hours
        - total_topics: number of topics
        - priority_breakdown: Count by priority level
        - output_path: path to plan JSON
        - message: summary message
    """
    try:
        # Validate enriched coverage exists for all exams
        enriched_paths = []
        for exam_id in exam_file_ids:
            enriched_path = STATE_DIR / "enriched_coverage" / f"{exam_id}.json"
            if not enriched_path.exists():
                return {
                    "status": "error",
                    "message": f"Enriched coverage not found for {exam_id}. Run enrich_coverage_tool first."
                }
            enriched_paths.append(enriched_path)
        
        # Parse dates
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
        
        # Generate plan with intelligent priorities
        print(f"Generating SMART study plan for {len(exam_file_ids)} exam(s) (priority strategy: {priority_strategy})...")
        plan = generate_multi_exam_plan(
            enriched_coverage_paths=enriched_paths,
            start_date=start,
            end_date=end,
            minutes_per_day=minutes_per_day,
            strategy=scheduling_strategy,
            generate_questions=generate_questions,
            use_intelligent_priorities=True,
            priority_strategy=priority_strategy
        )
        
        # Calculate priority breakdown
        priority_counts = {
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "optional": 0
        }
        for day in plan.days:
            for block in day.blocks:
                priority_counts[block.priority] = priority_counts.get(block.priority, 0) + 1
        
        # Save plan
        plans_dir = STATE_DIR / "plans"
        plans_dir.mkdir(parents=True, exist_ok=True)
        plan_path = plans_dir / f"{plan.plan_id}.json"
        
        with open(plan_path, 'w') as f:
            json.dump(plan.model_dump(mode='json'), f, indent=2, default=str)
        
        return {
            "status": "success",
            "plan_id": plan.plan_id,
            "total_days": plan.total_days,
            "total_hours": plan.total_study_hours,
            "total_topics": plan.total_topics,
            "priority_breakdown": priority_counts,
            "output_path": str(plan_path),
            "message": f"Created smart plan: {plan.total_topics} topics over {plan.total_days} days ({plan.total_study_hours:.1f}h total) - {priority_counts['critical']} critical, {priority_counts['high']} high, {priority_counts['medium']} medium priority"
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "message": f"Smart plan generation failed: {str(e)}"
        }


def export_plan(
    plan_id: str,
    format: Literal["json", "csv", "md", "markdown"] = "md"
) -> dict:
    """
    Export a study plan to readable format.
    
    Args:
        plan_id: Plan ID (UUID)
        format: Export format
        
    Returns:
        dict with:
        - status: "success" or "error"
        - plan_id: the plan ID
        - format: export format
        - output_path: path to exported file
        - message: summary message
    """
    try:
        # Load plan
        plan_path = STATE_DIR / "plans" / f"{plan_id}.json"
        if not plan_path.exists():
            return {"status": "error", "message": f"Plan {plan_id} not found"}
        
        with open(plan_path) as f:
            plan_data = json.load(f)
        plan = StudyPlan(**plan_data)
        
        # Determine output path
        format_ext = "md" if format in ["md", "markdown"] else format
        output_path = STATE_DIR / "plans" / f"{plan_id}.{format_ext}"
        
        # Export
        if format in ["md", "markdown"]:
            export_to_markdown(plan, output_path)
        elif format == "csv":
            export_to_csv(plan, output_path)
        elif format == "json":
            export_to_json(plan, output_path)
        
        return {
            "status": "success",
            "plan_id": plan_id,
            "format": format,
            "output_path": str(output_path),
            "message": f"Exported plan to {format.upper()}: {output_path}"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Export failed: {str(e)}"
        }


# ============================================================================
# TUTOR AGENT TOOLS
# ============================================================================

# Simple per-process retry guard for tutor search attempts.
# Resets when the query changes.
_TUTOR_LAST_QUERY: Optional[str] = None
_TUTOR_QUERY_ATTEMPTS: int = 0
_TUTOR_SEARCH_MAX_ATTEMPTS: int = int(os.getenv("TUTOR_SEARCH_MAX_ATTEMPTS", "2"))

def search_textbook(
    query: str,
    top_k: int = 5,
    exam_file_id: Optional[str] = None,
    textbook_file_id: Optional[str] = None,
    chapter_number: Optional[int] = None
) -> dict:
    """
    Search textbook using semantic similarity.
    
    Args:
        query: Search query (natural language)
        top_k: Number of results to return
        exam_file_id: Optional exam ID to filter by chapters
        textbook_file_id: Optional textbook file ID to filter by source file
        chapter_number: Optional chapter number to filter results
        
    Returns:
        dict with:
        - status: "success" or "error"
        - query: the search query
        - results: list of matching chunks with:
            - chunk_id
            - text
            - filename
            - page_start
            - page_end
            - chapter
            - score
        - message: summary message
    """
    try:
        # Guard against infinite retries on the same question.
        global _TUTOR_LAST_QUERY, _TUTOR_QUERY_ATTEMPTS
        normalized_query = " ".join(query.lower().split())
        if _TUTOR_LAST_QUERY == normalized_query:
            _TUTOR_QUERY_ATTEMPTS += 1
        else:
            _TUTOR_LAST_QUERY = normalized_query
            _TUTOR_QUERY_ATTEMPTS = 1

        if _TUTOR_QUERY_ATTEMPTS > _TUTOR_SEARCH_MAX_ATTEMPTS:
            return {
                "status": "error",
                "message": (
                    "Search retry limit reached for this question "
                    f"(max {_TUTOR_SEARCH_MAX_ATTEMPTS})."
                )
            }

        # Load index
        index_path = STATE_DIR / "index" / "faiss.index"
        mapping_path = STATE_DIR / "index" / "row_to_chunk_id.json"
        chunks_path = STATE_DIR / "chunks" / "chunks.jsonl"
        
        if not index_path.exists():
            return {"status": "error", "message": "FAISS index not found. Run build_index first."}
        
        index = load_faiss_index(index_path)
        mapping = load_chunk_mapping(mapping_path)
        
        # Embed query
        from app.tools.embed import embed_query
        query_embedding = embed_query(query)
        
        # Build filters
        filters = {"min_score": 0.5}
        
        # If exam scoped, filter by chapters
        if exam_file_id:
            coverage_path = STATE_DIR / "coverage" / f"{exam_file_id}.json"
            if coverage_path.exists():
                with open(coverage_path) as f:
                    coverage_data = json.load(f)
                coverage = ExamCoverage(**coverage_data)
                filters["chapter_number"] = coverage.chapters

        # If textbook scoped, filter by source file
        if textbook_file_id:
            filters["file_id"] = textbook_file_id

        # If chapter scoped, filter by chapter number
        if chapter_number is not None:
            filters["chapter_number"] = chapter_number
        
        # Search
        results = search_index(
            query_embedding=query_embedding,
            index=index,
            mapping=mapping,
            chunks_path=chunks_path,
            top_k=top_k,
            filters=filters
        )
        results = retrieve_chunks_with_text(results, chunks_path)
        
        # Format results
        formatted_results = []
        for result in results:
            text = result.get("text")
            if text is None:
                # Skip results without text to avoid KeyError downstream
                continue
            formatted_results.append({
                "chunk_id": result["chunk_id"],
                "text": text[:500] + "..." if len(text) > 500 else text,
                "filename": result["filename"],
                "page_start": result["page_start"],
                "page_end": result["page_end"],
                "chapter": result.get("chapter_number"),
                "score": result["score"]
            })
        
        return {
            "status": "success",
            "query": query,
            "results": formatted_results,
            "message": f"Found {len(formatted_results)} relevant chunks"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "message": f"Search failed: {str(e)}"
        }


# ============================================================================
# ROOT AGENT TOOLS (Orchestration)
# ============================================================================

def check_readiness(
    intent: str,
    exam_file_ids: Optional[list[str]] = None
) -> dict:
    """
    Check if system is ready for a given intent.
    
    Args:
        intent: User intent ("create_plan", "tutor", "search")
        exam_file_ids: Optional list of exam file IDs
        
    Returns:
        dict with:
        - ready: bool
        - missing: list of missing prerequisites
        - available_exams: list of available exam dicts
        - message: summary message
    """
    try:
        manifest = load_manifest(STATE_DIR / "manifest.json")
        
        missing = []
        available_exams = []
        
        # Check if index exists (required for all intents)
        index_path = STATE_DIR / "index" / "faiss.index"
        if not index_path.exists():
            missing.append({
                "type": "index",
                "message": "FAISS index not built. Upload textbook and run build_index."
            })
        
        # Get available exams (those with enriched coverage)
        enriched_dir = STATE_DIR / "enriched_coverage"
        if enriched_dir.exists():
            for enriched_path in enriched_dir.glob("*.json"):
                file_id = enriched_path.stem
                with open(enriched_path) as f:
                    enriched_data = json.load(f)
                available_exams.append({
                    "file_id": file_id,
                    "exam_name": enriched_data["exam_name"],
                    "exam_id": enriched_data["exam_id"],
                    "total_topics": enriched_data["total_topics"]
                })
        
        # Check specific intent requirements
        if intent == "create_plan" and exam_file_ids:
            for exam_id in exam_file_ids:
                enriched_path = STATE_DIR / "enriched_coverage" / f"{exam_id}.json"
                if not enriched_path.exists():
                    # Check if coverage exists (can enrich)
                    coverage_path = STATE_DIR / "coverage" / f"{exam_id}.json"
                    if coverage_path.exists():
                        missing.append({
                            "type": "enrichment",
                            "exam_file_id": exam_id,
                            "message": f"Exam coverage needs enrichment. Run enrich_coverage_tool({exam_id})."
                        })
                    else:
                        missing.append({
                            "type": "coverage",
                            "exam_file_id": exam_id,
                            "message": f"Exam coverage not extracted. Check if exam overview is uploaded."
                        })
        
        return {
            "ready": len(missing) == 0,
            "missing": missing,
            "available_exams": available_exams,
            "message": "System ready" if len(missing) == 0 else f"{len(missing)} prerequisite(s) missing"
        }
        
    except Exception as e:
        return {
            "ready": False,
            "missing": [],
            "available_exams": [],
            "message": f"Readiness check failed: {str(e)}"
        }


def list_available_exams() -> dict:
    """
    List all available exams (those with enriched coverage).
    
    Returns:
        dict with:
        - status: "success" or "error"
        - exams: list of exam dicts
        - message: summary message
    """
    try:
        exams = []
        enriched_dir = STATE_DIR / "enriched_coverage"
        
        if enriched_dir.exists():
            for enriched_path in enriched_dir.glob("*.json"):
                with open(enriched_path) as f:
                    enriched_data = json.load(f)
                exams.append({
                    "file_id": enriched_path.stem,
                    "exam_name": enriched_data["exam_name"],
                    "exam_id": enriched_data["exam_id"],
                    "exam_date": enriched_data.get("exam_date"),
                    "total_topics": enriched_data["total_topics"],
                    "high_confidence": enriched_data["high_confidence_count"],
                    "low_confidence": enriched_data["low_confidence_count"]
                })
        
        return {
            "status": "success",
            "exams": exams,
            "message": f"Found {len(exams)} exam(s)"
        }
        
    except Exception as e:
        return {
            "status": "error",
            "exams": [],
            "message": f"Failed to list exams: {str(e)}"
        }
