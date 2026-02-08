"""Semantic-aware chunking with recursive character splitting for better RAG quality."""
import re
import tiktoken
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class ChunkWithPages:
    """A chunk with its text and page range."""
    text: str
    page_start: int
    page_end: int
    token_count: int


def get_encoding(name: str = "cl100k_base") -> tiktoken.Encoding:
    """Return tiktoken encoding for token counting."""
    return tiktoken.get_encoding(name)


class RecursiveCharacterSplitter:
    """
    Split text recursively on natural boundaries for semantic coherence.
    
    Tries to split on (in order):
    1. Double newlines (paragraph breaks)
    2. Single newlines (line breaks)
    3. Periods followed by spaces (sentence boundaries)
    4. Spaces (word boundaries)
    5. Characters (last resort)
    """
    
    def __init__(
        self,
        target_tokens: int = 700,
        max_tokens: int = 900,
        min_tokens: int = 100,
        overlap_tokens: int = 100,
        encoding_name: str = "cl100k_base"
    ):
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        self.overlap_tokens = overlap_tokens
        self.encoding = get_encoding(encoding_name)
        
        # Separators in order of preference (most semantic to least)
        self.separators = [
            "\n\n",  # Paragraph breaks (highest priority)
            "\n",    # Line breaks
            ". ",    # Sentence boundaries
            " ",     # Word boundaries
            ""       # Character level (last resort)
        ]
    
    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.encoding.encode(text))
    
    def split_text(self, text: str) -> List[str]:
        """
        Recursively split text into semantically coherent chunks.
        
        Args:
            text: Text to split
            
        Returns:
            List of text chunks
        """
        if not text.strip():
            return []
        
        token_count = self.count_tokens(text)
        
        # If text is already small enough, return it
        if token_count <= self.max_tokens:
            return [text]
        
        # Try each separator in order
        for separator in self.separators:
            if separator == "":
                # Last resort: character-level splitting
                return self._split_by_tokens(text)
            
            # Split by this separator
            splits = text.split(separator)
            
            # If we got multiple parts, try to combine them into chunks
            if len(splits) > 1:
                chunks = self._merge_splits(splits, separator)
                
                # Check if this produced good chunks
                if chunks:
                    return chunks
        
        # Fallback to token-based splitting
        return self._split_by_tokens(text)
    
    def _merge_splits(self, splits: List[str], separator: str) -> List[str]:
        """
        Merge splits into chunks that respect token limits with overlap.
        
        Args:
            splits: List of text segments
            separator: The separator used (to reconstruct text)
            
        Returns:
            List of merged chunks with overlap
        """
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for split in splits:
            if not split.strip():
                continue
            
            split_tokens = self.count_tokens(split)
            
            # If this split alone is too large, recursively split it
            if split_tokens > self.max_tokens:
                # Save current chunk if it exists
                if current_chunk:
                    chunks.append(separator.join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
                
                # Recursively split the large segment
                sub_chunks = self.split_text(split)
                chunks.extend(sub_chunks)
                continue
            
            # Check if adding this split would exceed max_tokens
            potential_tokens = current_tokens + split_tokens
            if separator:
                potential_tokens += self.count_tokens(separator)
            
            if current_chunk and potential_tokens > self.max_tokens:
                # Save current chunk
                chunks.append(separator.join(current_chunk))
                
                # Start new chunk with overlap from previous chunk
                # Keep last few splits for overlap
                overlap_chunk = []
                overlap_tokens = 0
                
                # Add splits from the end until we reach overlap_tokens
                for prev_split in reversed(current_chunk):
                    prev_tokens = self.count_tokens(prev_split)
                    if overlap_tokens + prev_tokens <= self.overlap_tokens:
                        overlap_chunk.insert(0, prev_split)
                        overlap_tokens += prev_tokens
                    else:
                        break
                
                # Start new chunk with overlap + current split
                current_chunk = overlap_chunk + [split]
                current_tokens = overlap_tokens + split_tokens
            else:
                # Add to current chunk
                current_chunk.append(split)
                current_tokens = potential_tokens
        
        # Add final chunk
        if current_chunk:
            chunks.append(separator.join(current_chunk))
        
        return chunks
    
    def _split_by_tokens(self, text: str) -> List[str]:
        """
        Fallback: split by tokens with overlap when semantic splitting fails.
        
        Args:
            text: Text to split
            
        Returns:
            List of chunks with overlap
        """
        tokens = self.encoding.encode(text)
        chunks = []
        
        start = 0
        while start < len(tokens):
            end = min(start + self.max_tokens, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = self.encoding.decode(chunk_tokens)
            
            if chunk_text.strip():
                chunks.append(chunk_text)
            
            # Move forward by (chunk_size - overlap)
            start = end - self.overlap_tokens
            if start >= len(tokens) - self.overlap_tokens:
                break
        
        return chunks
    


def chunk_pages_semantic(
    pages: List[str],
    file_id: str,
    filename: str,
    target_tokens: int = 700,
    max_tokens: int = 900,
    overlap_tokens: int = 100
) -> List[ChunkWithPages]:
    """
    Chunk pages into SMALL semantic pieces for RAG.
    
    Each page is split into multiple small chunks (~700 tokens each).
    Uses semantic boundaries (paragraphs/sentences) to keep ideas coherent.
    
    Args:
        pages: List of page texts (1-indexed)
        file_id: File identifier
        filename: Original filename
        target_tokens: Target tokens per chunk (default 700)
        max_tokens: Maximum tokens per chunk (default 900)
        overlap_tokens: Token overlap between chunks (default 100)
        
    Returns:
        List of small ChunkWithPages objects, each from a single page
    """
    splitter = RecursiveCharacterSplitter(
        target_tokens=target_tokens,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens
    )
    
    all_chunks = []
    
    # Process each page individually
    for page_idx, page_text in enumerate(pages):
        page_num = page_idx + 1  # 1-indexed
        
        if not page_text.strip():
            continue
        
        # Split this page into multiple small semantic chunks
        page_chunks = splitter.split_text(page_text)
        
        # Create chunk objects - all from the same page
        for chunk_text in page_chunks:
            if not chunk_text.strip():
                continue
                
            token_count = splitter.count_tokens(chunk_text)
            
            chunk = ChunkWithPages(
                text=chunk_text,
                page_start=page_num,
                page_end=page_num,  # Single page for accurate citation
                token_count=token_count
            )
            all_chunks.append(chunk)
    
    return all_chunks


def chunk_page_ranges_semantic(
    pages: List[str],
    page_ranges: List[Tuple[int, int]],
    file_id: str,
    filename: str,
    target_tokens: int = 700,
    max_tokens: int = 900,
    overlap_tokens: int = 100
) -> List[ChunkWithPages]:
    """
    Chunk specific page ranges into SMALL semantic pieces for RAG.
    
    Each page is split into multiple small chunks (~700 tokens each).
    Only processes pages in the specified ranges.
    
    Args:
        pages: Full list of page texts
        page_ranges: List of (start_page, end_page) tuples (1-indexed)
        file_id: File identifier  
        filename: Original filename
        target_tokens: Target tokens per chunk (default 700)
        max_tokens: Maximum tokens per chunk (default 900)
        overlap_tokens: Token overlap between chunks (default 100)
        
    Returns:
        List of small ChunkWithPages objects
    """
    splitter = RecursiveCharacterSplitter(
        target_tokens=target_tokens,
        max_tokens=max_tokens,
        overlap_tokens=overlap_tokens
    )
    
    all_chunks = []
    
    # Process each page range
    for range_start, range_end in page_ranges:
        # Convert to 0-indexed
        start_idx = range_start - 1
        end_idx = range_end  # Inclusive
        
        if start_idx < 0 or end_idx > len(pages):
            continue
        
        # Process each page in this range
        for page_idx in range(start_idx, end_idx):
            page_num = page_idx + 1
            page_text = pages[page_idx]
            
            if not page_text.strip():
                continue
            
            # Split this page into multiple small semantic chunks
            page_chunks = splitter.split_text(page_text)
            
            # Create chunk objects - all from the same page
            for chunk_text in page_chunks:
                if not chunk_text.strip():
                    continue
                    
                token_count = splitter.count_tokens(chunk_text)
                
                chunk = ChunkWithPages(
                    text=chunk_text,
                    page_start=page_num,
                    page_end=page_num,  # Single page for accurate citation
                    token_count=token_count
                )
                all_chunks.append(chunk)
    
    return all_chunks
