"""Embedder — adds dense vectors to each chunk via nomic-embed-text.

Dense vector: nomic-embed-text via ollama_client.embed() (768 dims).

Note: BM25 sparse vectors were planned but fastembed's onnxruntime dependency
has no Python 3.14 wheels yet. Dense + cross-encoder reranking is used instead.
"""

from __future__ import annotations

from models.ollama_client import embed

_EMBEDDING_MODEL = "nomic-embed-text"


async def embed_chunks(chunks: list[dict]) -> list[dict]:
    """Add dense_vector to each chunk dict. Processes sequentially to avoid overloading Ollama."""
    embedded: list[dict] = []
    for chunk in chunks:
        dense_vec = await embed(_EMBEDDING_MODEL, chunk["text"])
        embedded.append({**chunk, "dense_vector": dense_vec})
    return embedded
