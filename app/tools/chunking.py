"""Split text into chunks with optional token-aware boundaries."""
import tiktoken


def get_encoding(name: str = "cl100k_base") -> tiktoken.Encoding:
    """Return tiktoken encoding for token counting."""
    return tiktoken.get_encoding(name)


def chunk_text(
    text: str,
    max_tokens: int = 512,
    overlap_tokens: int = 64,
    encoding_name: str = "cl100k_base",
) -> list[str]:
    """Split text into chunks by token count with overlap."""
    enc = get_encoding(encoding_name)
    tokens = enc.encode(text)
    chunks = []
    start = 0
    while start < len(tokens):
        end = min(start + max_tokens, len(tokens))
        chunk_tokens = tokens[start:end]
        chunks.append(enc.decode(chunk_tokens))
        start = end - overlap_tokens
        if start >= len(tokens):
            break
    return chunks
