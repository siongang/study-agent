"""Storage and retrieval for text chunks."""
from pathlib import Path
import json
from typing import Optional

from app.models.chunks import Chunk


def save_chunks_jsonl(chunks: list[Chunk], output_path: Path) -> None:
    """
    Save chunks to JSONL format (one JSON object per line).
    
    Args:
        chunks: List of Chunk objects
        output_path: Path to output JSONL file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with output_path.open('w', encoding='utf-8') as f:
        for chunk in chunks:
            f.write(chunk.model_dump_json() + '\n')


def load_chunks_jsonl(input_path: Path) -> list[Chunk]:
    """
    Load chunks from JSONL file.
    
    Args:
        input_path: Path to JSONL file
        
    Returns:
        List of Chunk objects
    """
    if not input_path.exists():
        return []
    
    chunks = []
    with input_path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    chunk_data = json.loads(line)
                    chunks.append(Chunk(**chunk_data))
                except Exception as e:
                    print(f"Warning: Failed to parse chunk line: {e}")
                    continue
    
    return chunks


def append_chunks_jsonl(chunks: list[Chunk], output_path: Path) -> None:
    """
    Append chunks to existing JSONL file.
    
    Args:
        chunks: List of Chunk objects to append
        output_path: Path to output JSONL file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with output_path.open('a', encoding='utf-8') as f:
        for chunk in chunks:
            f.write(chunk.model_dump_json() + '\n')


def get_chunk_by_id(chunk_id: str, chunks_path: Path) -> Optional[Chunk]:
    """
    Find a specific chunk by ID.
    
    Args:
        chunk_id: The chunk ID to find
        chunks_path: Path to JSONL file
        
    Returns:
        Chunk object if found, None otherwise
    """
    chunks = load_chunks_jsonl(chunks_path)
    for chunk in chunks:
        if chunk.chunk_id == chunk_id:
            return chunk
    return None


def build_chunk_index(chunks_path: Path, index_path: Path) -> None:
    """
    Build a lookup index mapping chunk_id to file position for fast access.
    
    Args:
        chunks_path: Path to JSONL file
        index_path: Path to save index JSON
    """
    chunks = load_chunks_jsonl(chunks_path)
    
    # Create index: chunk_id -> {file_id, page_start, page_end, section_type, chapter_number}
    index = {}
    for chunk in chunks:
        index[chunk.chunk_id] = {
            "file_id": chunk.file_id,
            "filename": chunk.filename,
            "chunk_index": chunk.chunk_index,
            "page_start": chunk.page_start,
            "page_end": chunk.page_end,
            "section_type": chunk.section_type,
            "chapter_number": chunk.chapter_number,
        }
    
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, indent=2))


def get_chunks_by_file_id(file_id: str, chunks_path: Path) -> list[Chunk]:
    """
    Get all chunks belonging to a specific file.
    
    Args:
        file_id: The file ID to filter by
        chunks_path: Path to JSONL file
        
    Returns:
        List of chunks for that file
    """
    chunks = load_chunks_jsonl(chunks_path)
    return [chunk for chunk in chunks if chunk.file_id == file_id]
