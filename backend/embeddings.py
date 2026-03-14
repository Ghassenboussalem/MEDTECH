"""
embeddings.py — ChromaDB vector store with nomic-embed-text (via Ollama).

Functions:
  add_chunks(notebook_id, chunks)  -> store embeddings
  query(notebook_id, question, k)  -> top-k similar chunks
  delete_collection(notebook_id)   -> remove all vectors for a notebook
"""
from pathlib import Path

import chromadb
import ollama

CHROMA_DIR = Path(__file__).parent.parent / "data" / "chroma"
EMBED_MODEL = "nomic-embed-text"


def _client() -> chromadb.PersistentClient:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def _collection(notebook_id: str):
    client = _client()
    # Collection name must be valid (alphanumeric + underscores/hyphens)
    safe_id = notebook_id.replace("-", "_")
    return client.get_or_create_collection(f"nb_{safe_id}", metadata={"hnsw:space": "cosine"})


def _embed(texts: list[str]) -> list[list[float]]:
    """Batch embed texts using nomic-embed-text via Ollama."""
    vectors = []
    for text in texts:
        resp = ollama.embeddings(model=EMBED_MODEL, prompt=text)
        vectors.append(resp["embedding"])
    return vectors


def add_chunks(notebook_id: str, chunks: list[dict]) -> None:
    """Embed and store chunks into the notebook's ChromaDB collection."""
    if not chunks:
        return
    collection = _collection(notebook_id)
    texts = [c["text"] for c in chunks]
    metadatas = [{"source": c["source"], "page": c.get("page", 0)} for c in chunks]
    # Build deterministic IDs so re-ingesting the same file doesn't duplicate
    start_id = collection.count()
    ids = [f"chunk_{start_id + i}" for i in range(len(chunks))]
    embeddings = _embed(texts)
    collection.upsert(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)


def query(notebook_id: str, question: str, k: int = 5) -> list[dict]:
    """Return top-k chunks most relevant to question."""
    collection = _collection(notebook_id)
    if collection.count() == 0:
        return []
    q_embedding = _embed([question])[0]
    results = collection.query(
        query_embeddings=[q_embedding],
        n_results=min(k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    chunks = []
    for doc, meta, dist in zip(
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        chunks.append({"text": doc, "source": meta["source"], "page": meta.get("page", 0), "score": 1 - dist})
    return chunks


def delete_collection(notebook_id: str) -> None:
    """Delete all vectors for a notebook."""
    client = _client()
    safe_id = notebook_id.replace("-", "_")
    try:
        client.delete_collection(f"nb_{safe_id}")
    except Exception:
        pass
