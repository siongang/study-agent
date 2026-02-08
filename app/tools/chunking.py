"""Split text into chunks with token-aware boundaries and accurate page metadata."""
import tiktoken
from typing import Optional


def get_encoding(name: str = "cl100k_base") -> tiktoken.Encoding:
    """Return tiktoken encoding for token counting."""
    return tiktoken.get_encoding(name)


def chunk_pages_with_metadata(
    pages: list[str],
    file_id: str,
    filename: str,
    max_tokens: int = 700,
    overlap_tokens: int = 100,
    page_window: int = 2,
    encoding_name: str = "cl100k_base",
) -> list[dict]:
    """
    Split pages into chunks with accurate page tracking.
    
    Process pages in windows to handle content that spans pages.
    
    Args:
        pages: List of page texts
        file_id: Unique file identifier
        filename: Original filename
        max_tokens: Maximum tokens per chunk
        overlap_tokens: Token overlap between chunks
        page_window: Number of pages to process together (default 2)
        encoding_name: Tiktoken encoding name
        
    Returns:
        List of dicts with:
            - text: chunk content
            - metadata: {file_id, filename, chunk_index, page_start, page_end, etc.}
    """
    import sys
    print(f"      → chunk_pages_with_metadata: Starting with {len(pages)} pages", flush=True)
    sys.stdout.flush()
    
    if overlap_tokens >= max_tokens:
        raise ValueError(
            f"overlap_tokens ({overlap_tokens}) must be less than max_tokens ({max_tokens})"
        )

    enc = get_encoding(encoding_name)
    all_chunks = []
    global_chunk_index = 0
    
    # Process pages in sliding windows
    print(f"      → Processing {len(pages)} pages in windows of {page_window}...", flush=True)
    sys.stdout.flush()
    
    for page_idx in range(len(pages)):
        if page_idx % 50 == 0:
            print(f"      → Processing page {page_idx}/{len(pages)}...", flush=True)
            sys.stdout.flush()
        # Create a window of pages (e.g., page i and i+1)
        page_window_end = min(page_idx + page_window, len(pages))
        window_pages = pages[page_idx:page_window_end]
        window_text = "\n".join(window_pages)
        
        # Calculate page numbers (1-indexed)
        page_start = page_idx + 1
        page_end = page_window_end
        
        # Tokenize the window
        tokens = enc.encode(window_text)
        
        # Skip if window is too small
        if len(tokens) < 50:
            continue
        
        # Chunk this window
        start = 0
        window_chunks = []
        
        while start < len(tokens):
            end = min(start + max_tokens, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = enc.decode(chunk_tokens)
            
            # Only add non-empty chunks
            if chunk_text.strip():
                window_chunks.append({
                    "text": chunk_text,
                    "metadata": {
                        "file_id": file_id,
                        "filename": filename,
                        "chunk_index": global_chunk_index,
                        "page_start": page_start,
                        "page_end": page_end if page_end > page_start else page_start,
                        "token_count": len(chunk_tokens),
                    }
                })
                global_chunk_index += 1
            
            if end >= len(tokens):
                break
            start = max(0, end - overlap_tokens)
        
        # Add chunks from this window (skip first chunk if not first page to avoid duplicates)
        if page_idx == 0:
            all_chunks.extend(window_chunks)
        else:
            # Skip first chunk to avoid overlap with previous window
            all_chunks.extend(window_chunks[1:] if len(window_chunks) > 1 else [])
    
    print(f"      → Chunking complete: {len(all_chunks)} total chunks created", flush=True)
    sys.stdout.flush()
    
    return all_chunks


def chunk_text(
    text: str,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
    encoding_name: str = "cl100k_base",
) -> list[str]:
    """Split text into chunks by token count with overlap (simple version)."""
    if overlap_tokens >= max_tokens:
        raise ValueError(
            f"overlap_tokens ({overlap_tokens}) must be less than max_tokens ({max_tokens})"
        )
    enc = get_encoding(encoding_name)
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(enc.decode(chunk_tokens))
        if end >= len(tokens):
            break
        start = max(0, end - overlap_tokens)
    return chunks
