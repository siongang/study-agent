"""Retrieve relevant chunks from the vector store for RAG."""
from typing import Any


def retrieve(
    collection: Any,
    query_embedding: list[float],
    top_k: int = 5,
    where: dict | None = None,
) -> list[dict]:
    """Return top_k nearest chunks with metadata."""
    if collection is None:
        return []
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=top_k,
        where=where,
    )
    docs = []
    if result["ids"] and result["ids"][0]:
        for i, id_ in enumerate(result["ids"][0]):
            docs.append({
                "id": id_,
                "metadata": (result.get("metadatas") or [[]])[0][i] if result.get("metadatas") else {},
                "distance": (result.get("distances") or [[]])[0][i] if result.get("distances") else None,
            })
    return docs
