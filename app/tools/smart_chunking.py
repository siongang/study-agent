"""Smart chunking with semantic boundaries - only processes required chapters for better quality."""
from pathlib import Path
from typing import Optional, Set, List, Tuple
import json

from app.models.chunks import Chunk
from app.models.textbook_metadata import TextbookMetadata
from app.models.coverage import ExamCoverage
from app.tools.text_extraction import load_extracted_text
from app.tools.semantic_chunking import chunk_pages_semantic, chunk_page_ranges_semantic


def load_toc_metadata(file_id: str, textbook_metadata_dir: Path) -> Optional[TextbookMetadata]:
    """Load TOC metadata for a textbook."""
    metadata_path = textbook_metadata_dir / f"{file_id}.json"
    if not metadata_path.exists():
        return None
    
    try:
        data = json.loads(metadata_path.read_text(encoding='utf-8'))
        return TextbookMetadata(**data)
    except Exception as e:
        print(f"      ⚠ Failed to load TOC: {e}")
        return None


def get_required_chapters_from_coverage(
    coverage_dir: Path
) -> Set[int]:
    """Find all chapters required across all exams."""
    required_chapters = set()
    
    if not coverage_dir.exists():
        return required_chapters
    
    coverage_files = list(coverage_dir.glob("*.json"))
    print(f"    - Checking {len(coverage_files)} exam coverage file(s)...")
    
    for coverage_file in coverage_files:
        try:
            data = json.loads(coverage_file.read_text(encoding='utf-8'))
            coverage = ExamCoverage(**data)
            
            chapters_before = len(required_chapters)
            required_chapters.update(coverage.chapters)
            new_chapters = len(required_chapters) - chapters_before
            
            print(f"      * {coverage.exam_name}: chapters {coverage.chapters} (+{new_chapters} new)")
            
        except Exception as e:
            print(f"      ⚠ Failed to load {coverage_file.name}: {e}")
            continue
    
    return required_chapters


def get_page_ranges_for_chapters(
    chapter_numbers: Set[int],
    toc_metadata: Optional[TextbookMetadata]
) -> List[Tuple[int, int]]:
    """Convert chapter numbers to page ranges using TOC metadata."""
    if not toc_metadata or not toc_metadata.chapters:
        return []
    
    page_ranges = []
    for chapter in toc_metadata.chapters:
        if chapter.chapter in chapter_numbers:
            page_ranges.append((chapter.page_start, chapter.page_end))
    
    # Sort by page_start
    page_ranges.sort(key=lambda x: x[0])
    return page_ranges


def chunk_textbook_smart(
    file_id: str,
    extracted_text_dir: Path,
    textbook_metadata_dir: Path,
    coverage_dir: Path,
    filename: str,
    target_tokens: int = 700,
    max_tokens: int = 900,
    overlap_tokens: int = 100
) -> List[Chunk]:
    """
    Chunk only the chapters required by exams using semantic boundaries.
    
    Focus: High-quality, semantically coherent chunks for better RAG retrieval.
    No tagging needed - the RAG system will find relevant chunks naturally.
    
    Args:
        file_id: File identifier
        extracted_text_dir: Directory containing extracted text
        textbook_metadata_dir: Directory with textbook TOC metadata
        coverage_dir: Directory with exam coverage JSONs
        filename: Original filename
        target_tokens: Target tokens per chunk (default 700)
        max_tokens: Maximum tokens per chunk (default 900)
        overlap_tokens: Token overlap between chunks (default 100)
        
    Returns:
        List of Chunk objects with high-quality semantic boundaries
    """
    print(f"  [1/5] Loading extracted text...", flush=True)
    extracted = load_extracted_text(file_id, extracted_text_dir)
    if extracted is None:
        print(f"  ✗ Failed to load extracted text")
        return []
    print(f"  ✓ Loaded {len(extracted.pages)} pages")
    
    print(f"  [2/5] Loading TOC metadata...", flush=True)
    toc_metadata = load_toc_metadata(file_id, textbook_metadata_dir)
    if not toc_metadata or not toc_metadata.chapters:
        print(f"  ⚠ No TOC - chunking all pages with semantic boundaries")
        return _chunk_all_pages_semantic(
            extracted.pages, file_id, filename, target_tokens, max_tokens, overlap_tokens, None
        )
    print(f"  ✓ Loaded TOC with {len(toc_metadata.chapters)} chapters")
    
    print(f"  [3/5] Finding required chapters from exam coverage...", flush=True)
    required_chapters = get_required_chapters_from_coverage(coverage_dir)
    if not required_chapters:
        print(f"  ⚠ No coverage found - chunking all pages with semantic boundaries")
        return _chunk_all_pages_semantic(
            extracted.pages, file_id, filename, target_tokens, max_tokens, overlap_tokens, toc_metadata
        )
    print(f"  ✓ Required chapters: {sorted(required_chapters)}")
    
    print(f"  [4/5] Mapping chapters to page ranges...", flush=True)
    page_ranges = get_page_ranges_for_chapters(required_chapters, toc_metadata)
    if not page_ranges:
        print(f"  ⚠ Could not map chapters - chunking all pages")
        return _chunk_all_pages_semantic(
            extracted.pages, file_id, filename, target_tokens, max_tokens, overlap_tokens, toc_metadata
        )
    
    # Calculate total pages to chunk
    total_pages_to_chunk = sum(end - start + 1 for start, end in page_ranges)
    total_pages = len(extracted.pages)
    
    print(f"  ✓ Page ranges mapped:")
    for start, end in page_ranges:
        chapter_num = None
        for ch in toc_metadata.chapters:
            if ch.page_start == start:
                chapter_num = ch.chapter
                break
        print(f"    - Pages {start}-{end} ({end-start+1} pages) [Chapter {chapter_num}]")
    print(f"  ✓ Total: {total_pages_to_chunk}/{total_pages} pages ({100*total_pages_to_chunk/total_pages:.1f}%)")
    
    print(f"  [5/5] Chunking with semantic boundaries...", flush=True)
    
    # Use semantic chunking on the required page ranges
    chunk_objs = chunk_page_ranges_semantic(
        pages=extracted.pages,
        page_ranges=page_ranges,
        file_id=file_id,
        filename=filename,
        target_tokens=target_tokens,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens
    )
    
    # Convert to Chunk model objects with chapter metadata
    chunks = []
    for idx, chunk_obj in enumerate(chunk_objs):
        # Find which chapter this chunk belongs to based on page_start
        chapter_number = None
        chapter_title = None
        
        if toc_metadata:
            for chapter in toc_metadata.chapters:
                if chapter.page_start <= chunk_obj.page_start <= chapter.page_end:
                    chapter_number = chapter.chapter
                    chapter_title = chapter.title
                    break
        
        chunk_id = Chunk.generate_chunk_id(
            file_id=file_id,
            page_start=chunk_obj.page_start,
            page_end=chunk_obj.page_end,
            chunk_index=idx
        )
        
        chunk = Chunk(
            chunk_id=chunk_id,
            file_id=file_id,
            filename=filename,
            text=chunk_obj.text,
            page_start=chunk_obj.page_start,
            page_end=chunk_obj.page_end,
            token_count=chunk_obj.token_count,
            section_type="other",  # Generic default - RAG handles classification
            chapter_number=chapter_number,  # CRITICAL for linking topics to chunks
            chapter_title=chapter_title,     # CRITICAL for citations
            chunk_index=idx
        )
        chunks.append(chunk)
    
    # Log chapter distribution
    chapter_counts = {}
    for chunk in chunks:
        if chunk.chapter_number:
            chapter_counts[chunk.chapter_number] = chapter_counts.get(chunk.chapter_number, 0) + 1
    
    print(f"  ✓ Created {len(chunks)} semantic chunks")
    if chapter_counts:
        chapter_summary = ", ".join(f"Ch{k}: {v}" for k, v in sorted(chapter_counts.items()))
        print(f"    Chapters: {chapter_summary}")
    
    return chunks


def _chunk_all_pages_semantic(
    pages: List[str],
    file_id: str,
    filename: str,
    target_tokens: int,
    max_tokens: int,
    overlap_tokens: int,
    toc_metadata: Optional[TextbookMetadata] = None
) -> List[Chunk]:
    """
    Fallback: chunk all pages with semantic boundaries.
    
    Used when we can't determine required chapters from coverage.
    Still adds chapter metadata if TOC available.
    """
    print(f"    - Chunking all {len(pages)} pages with semantic boundaries...")
    
    chunk_objs = chunk_pages_semantic(
        pages=pages,
        file_id=file_id,
        filename=filename,
        target_tokens=target_tokens,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens
    )
    
    # Convert to Chunk model objects with chapter metadata
    chunks = []
    for idx, chunk_obj in enumerate(chunk_objs):
        # Find which chapter this chunk belongs to based on page_start
        chapter_number = None
        chapter_title = None
        
        if toc_metadata:
            for chapter in toc_metadata.chapters:
                if chapter.page_start <= chunk_obj.page_start <= chapter.page_end:
                    chapter_number = chapter.chapter
                    chapter_title = chapter.title
                    break
        
        chunk_id = Chunk.generate_chunk_id(
            file_id=file_id,
            page_start=chunk_obj.page_start,
            page_end=chunk_obj.page_end,
            chunk_index=idx
        )
        
        chunk = Chunk(
            chunk_id=chunk_id,
            file_id=file_id,
            filename=filename,
            text=chunk_obj.text,
            page_start=chunk_obj.page_start,
            page_end=chunk_obj.page_end,
            token_count=chunk_obj.token_count,
            section_type="other",
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            chunk_index=idx
        )
        chunks.append(chunk)
    
    print(f"  ✓ Created {len(chunks)} semantic chunks from all pages")
    return chunks
