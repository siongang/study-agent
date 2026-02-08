"""Generate embeddings for chunks (e.g. via Google GenAI)."""
from typing import Any
import os


def embed_texts(texts: list[str], model_name: str = "text-embedding-004") -> list[list[float]]:
    """Return embedding vectors for each text. Implement with google.genai."""
    try:
        from google import genai
        
        api_key = os.getenv("GOOGLE_API_KEY")
        client = genai.Client(api_key=api_key) if api_key else genai.Client()
        
        # Embed content using the new API
        embeddings = []
        for text in texts:
            result = client.models.embed_content(
                model=model_name,
                content=text
            )
            embeddings.append(result.embeddings[0].values)
        
        return embeddings
    except Exception:
        return [[0.0] * 768 for _ in texts]
