"""Generate embeddings for chunks (e.g. via Google GenAI)."""
from typing import Any


def embed_texts(texts: list[str], model_name: str = "text-embedding-004") -> list[list[float]]:
    """Return embedding vectors for each text. Implement with google.generativeai."""
    try:
        import google.generativeai as genai
        result = genai.embed_content(
            model=model_name, content=texts, task_type="retrieval_document"
        )
        emb = result.get("embedding", result)
        if emb and isinstance(emb[0], list):
            return emb
        return [emb] if emb else []
    except Exception:
        return [[0.0] * 768 for _ in texts]
