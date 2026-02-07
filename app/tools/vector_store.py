"""Vector store (e.g. ChromaDB/FAISS) for RAG index."""
from pathlib import Path
from typing import Any


def get_or_create_index(persist_dir: Path, collection_name: str = "chunks") -> Any:
    """Return a ChromaDB collection or FAISS index for persist_dir."""
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(persist_dir))
        return client.get_or_create_collection(collection_name)
    except Exception:
        return None


def add_vectors(collection: Any, ids: list[str], embeddings: list[list[float]], metadatas: list[dict] | None = None) -> None:
    """Add embeddings to the collection."""
    if collection is None:
        return
    collection.add(ids=ids, embeddings=embeddings, metadatas=metadatas or [])
