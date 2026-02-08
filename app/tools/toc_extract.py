"""Extract table of contents from textbooks using LLM."""
import os
import re
import json
import logging
from typing import Optional, Tuple
from google import genai
from google.genai import types
from app.models.textbook_metadata import TextbookMetadata, ChapterInfo, SectionInfo

logger = logging.getLogger(__name__)


def extract_toc(
    file_id: str,
    pages: list[str],
    filename: str,
    max_toc_pages: int = 30
) -> Tuple[Optional[TextbookMetadata], Optional[str]]:
    """
    Extract table of contents from textbook pages using LLM.
    
    Args:
        file_id: Unique file identifier
        pages: List of page texts from extracted_text JSON
        filename: Original filename
        max_toc_pages: Maximum number of pages to search for TOC
        
    Returns:
        Tuple of (TextbookMetadata, error_message)
        Returns (metadata, None) on success
        Returns (None, error_msg) on failure
    """
    logger.info(f"Starting TOC extraction for file_id={file_id}, filename={filename}")
    logger.debug(f"Total pages available: {len(pages)}, searching first {max_toc_pages} pages")
    
    # Search first max_toc_pages for TOC
    toc_candidate_pages = pages[:min(max_toc_pages, len(pages))]
    
    # Find pages that likely contain TOC
    toc_pages_indices = _find_toc_pages(toc_candidate_pages)
    logger.info(f"TOC detection found pages: {toc_pages_indices}")
    
    if not toc_pages_indices:
        # No TOC found
        logger.warning(f"No TOC pages detected in first {max_toc_pages} pages")
        metadata = TextbookMetadata(
            file_id=file_id,
            filename=filename,
            doc_type="textbook",
            toc_source_pages=[],
            chapters=[],
            notes="No table of contents detected in first {} pages".format(max_toc_pages)
        )
        return metadata, None
    
    # Combine TOC pages
    logger.info(f"Combining {len(toc_pages_indices)} TOC pages...")
    toc_text = "\n\n---PAGE BREAK---\n\n".join(
        [toc_candidate_pages[i] for i in toc_pages_indices]
    )
    logger.debug(f"Combined TOC text length: {len(toc_text)} chars")
    
    # Extract chapters using LLM
    chapters, error = _extract_chapters_with_llm(toc_text)
    
    if error:
        logger.error(f"Chapter extraction failed: {error}")
        metadata = TextbookMetadata(
            file_id=file_id,
            filename=filename,
            doc_type="textbook",
            toc_source_pages=[p + 1 for p in toc_pages_indices],  # 1-indexed
            chapters=[],
            notes=f"TOC found on pages {toc_pages_indices} but extraction failed: {error}"
        )
        return metadata, error
    
    # Validate and post-process chapters
    logger.info(f"Validating and fixing {len(chapters)} extracted chapters...")
    chapters = _validate_and_fix_chapters(chapters)
    logger.info(f"Validation complete, final chapter count: {len(chapters)}")
    
    # Log summary
    logger.info(f"Extraction successful: {len(chapters)} chapters")
    for ch in chapters:
        logger.debug(f"  Ch {ch.chapter}: {ch.title} (pages {ch.page_start}-{ch.page_end})")
    
    metadata = TextbookMetadata(
        file_id=file_id,
        filename=filename,
        doc_type="textbook",
        toc_source_pages=[p + 1 for p in toc_pages_indices],  # 1-indexed
        chapters=chapters,
        notes=f"TOC extracted successfully from pages {[p+1 for p in toc_pages_indices]}"
    )
    
    logger.info("TOC extraction completed successfully")
    return metadata, None


def _find_toc_pages(pages: list[str]) -> list[int]:
    """
    Find pages that likely contain table of contents.
    
    Returns indices of pages (0-indexed).
    """
    toc_keywords = [
        r"table\s+of\s+contents",
        r"contents",
        r"chapter\s+\d+",
        r"part\s+[IVX]+",
    ]
    
    toc_pages = []
    
    for i, page_text in enumerate(pages):
        page_lower = page_text.lower()
        
        # Check for TOC keywords
        has_toc_keyword = any(re.search(pattern, page_lower) for pattern in toc_keywords)
        
        # Check for page number patterns (e.g., "Chapter 1 ... 15")
        has_page_numbers = bool(re.search(r'\d+\s*$', page_text, re.MULTILINE))
        
        # Check for dot leaders (.....) common in TOCs
        has_dot_leaders = '...' in page_text or '…' in page_text
        
        if has_toc_keyword or (has_page_numbers and has_dot_leaders):
            toc_pages.append(i)
            
    return toc_pages


def _extract_chapters_with_llm(toc_text: str) -> Tuple[list[ChapterInfo], Optional[str]]:
    """
    Use LLM to extract structured chapter information from TOC text.
    
    Returns:
        Tuple of (chapters_list, error_message)
    """
    try:
        logger.info("Starting LLM extraction of chapters and sections")
        
        # Load API key from environment
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.error("GOOGLE_API_KEY environment variable not set")
            return [], "GOOGLE_API_KEY environment variable not set"
        
        logger.debug(f"API key found: {api_key[:10]}...")
        client = genai.Client(api_key=api_key)
        
        prompt = """Extract the table of contents from this textbook. For each chapter, provide:

- chapter: chapter number (integer, e.g., 1, 2, 3)
- title: chapter title (string)
- page_start: page number where chapter begins (integer)
- page_end: page number where chapter ends (integer, infer from next chapter's start - 1)

Instructions:
- Only extract CHAPTER-level entries (not sections/subsections within chapters)
- If TOC has Parts and Chapters, extract only chapters (ignore parts)
- Handle Roman numerals by converting to integers for chapters
- For appendices, use numbers like 999, 998, etc.
- If a chapter has no clear end page, estimate based on next chapter
- Ignore preface, foreword, index, references unless they have chapter numbers
- Return ONLY valid JSON array, no other text

TOC Text:
{}

Return as JSON array:
```json
[
  {{"chapter": 1, "title": "...", "page_start": 1, "page_end": 40}},
  {{"chapter": 2, "title": "...", "page_start": 41, "page_end": 83}}
]
```""".format(toc_text[:10000])
        
        # Log the input TOC text
        toc_text_preview = toc_text[:10000]
        logger.info(f"TOC text length: {len(toc_text)} chars (sending first {len(toc_text_preview)} chars)")
        logger.debug("="*80)
        logger.debug("INPUT TOC TEXT:")
        logger.debug("="*80)
        logger.debug(toc_text_preview)
        logger.debug("="*80)
        
        # Use the model from environment or default to gemini-2.0-flash
        model_name = os.getenv("CHAT_MODEL", "gemini-2.0-flash")
        logger.info(f"Calling LLM ({model_name}) for TOC extraction (chapters-only)...")
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json",
                max_output_tokens=4096  # Sufficient for chapters-only extraction
            )
        )
        
        logger.info(f"LLM response received, length: {len(response.text)} chars")
        logger.debug("="*80)
        logger.debug("RAW LLM RESPONSE:")
        logger.debug("="*80)
        logger.debug(response.text)
        logger.debug("="*80)
        
        # Parse JSON response
        logger.info("Parsing JSON response...")
        chapters_data = json.loads(response.text)
        logger.info(f"JSON parsed successfully, found {len(chapters_data)} chapters")
        
        # Convert to ChapterInfo objects (chapters-only, no sections)
        logger.info("Converting JSON data to ChapterInfo objects...")
        chapters = []
        for i, item in enumerate(chapters_data):
            try:
                logger.debug(f"Processing chapter {i+1}/{len(chapters_data)}: {item.get('title', 'Unknown')}")
                
                # Ensure sections field exists but is empty for chapters-only extraction
                if 'sections' not in item:
                    item['sections'] = []
                
                chapter = ChapterInfo(**item)
                chapters.append(chapter)
            except Exception as e:
                logger.warning(f"Skipping invalid chapter entry at index {i}: {item}, error: {e}")
                continue
        
        logger.info(f"Successfully converted {len(chapters)} chapters")
        return chapters, None
        
    except json.JSONDecodeError as e:
        error_msg = f"JSON parsing failed: {str(e)}"
        logger.error(error_msg)
        logger.error(f"JSON decode error at line {e.lineno}, column {e.colno}, position {e.pos}")
        if hasattr(e, 'doc'):
            # Show context around the error
            doc = e.doc
            start = max(0, e.pos - 200)
            end = min(len(doc), e.pos + 200)
            context = doc[start:end]
            logger.error(f"Error context: ...{context}...")
        return [], error_msg
    except Exception as e:
        error_msg = f"LLM extraction failed: {str(e)}"
        logger.error(error_msg)
        logger.exception("Full exception traceback:")
        return [], error_msg


def _validate_and_fix_chapters(chapters: list[ChapterInfo]) -> list[ChapterInfo]:
    """
    Validate and fix common issues in extracted chapters.
    
    - Ensure chapters are sequential
    - Ensure page ranges don't overlap
    - Ensure page_start < page_end
    """
    if not chapters:
        return chapters
    
    # Sort by chapter number
    chapters.sort(key=lambda c: c.chapter)
    
    # Fix page_end values
    validated = []
    for i, chapter in enumerate(chapters):
        # Ensure page_start < page_end for chapter
        if chapter.page_start >= chapter.page_end:
            if i + 1 < len(chapters):
                # Use next chapter's start - 1
                chapter.page_end = chapters[i + 1].page_start - 1
            else:
                # Last chapter, add reasonable estimate
                chapter.page_end = chapter.page_start + 50
        
        validated.append(chapter)
    
    return validated
