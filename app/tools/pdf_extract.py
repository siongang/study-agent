"""Extract text from PDFs using PyMuPDF with pdfplumber fallback (Phase 2)."""
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.models.extracted_text import ExtractedText


def extract_text_from_pdf(
    file_path: Path,
    file_id: str,
    relative_path: str
) -> tuple[Optional[ExtractedText], Optional[str]]:
    """
    Extract text from a PDF file.
    
    Uses PyMuPDF (fitz) as primary method, falls back to pdfplumber if needed.
    
    Returns:
        (ExtractedText object, error_message)
        If successful: (ExtractedText, None)
        If failed: (None, error_message)
    """
    # Try PyMuPDF first
    result = _extract_with_pymupdf(file_path, file_id, relative_path)
    if result is not None:
        return result, None
    
    # Fallback to pdfplumber
    result = _extract_with_pdfplumber(file_path, file_id, relative_path)
    if result is not None:
        return result, None
    
    # Both failed
    return None, "Failed to extract text with both PyMuPDF and pdfplumber"


def _extract_with_pymupdf(
    file_path: Path,
    file_id: str,
    relative_path: str
) -> Optional[ExtractedText]:
    """Extract text using PyMuPDF (fitz). Returns None on failure."""
    try:
        import fitz
        
        doc = fitz.open(file_path)
        pages = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            pages.append(text)
        
        doc.close()
        
        full_text = "\n".join(pages)
        first_page = pages[0] if pages else ""
        
        return ExtractedText(
            file_id=file_id,
            path=relative_path,
            num_pages=len(pages),
            pages=pages,
            full_text=full_text,
            first_page=first_page,
            extracted_at=datetime.now(timezone.utc).isoformat()
        )
    except Exception:
        return None


def _extract_with_pdfplumber(
    file_path: Path,
    file_id: str,
    relative_path: str
) -> Optional[ExtractedText]:
    """Extract text using pdfplumber. Returns None on failure."""
    try:
        import pdfplumber
        
        pages = []
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages.append(text)
        
        full_text = "\n".join(pages)
        first_page = pages[0] if pages else ""
        
        return ExtractedText(
            file_id=file_id,
            path=relative_path,
            num_pages=len(pages),
            pages=pages,
            full_text=full_text,
            first_page=first_page,
            extracted_at=datetime.now(timezone.utc).isoformat()
        )
    except Exception:
        return None
