"""Embedder — adds dense and sparse vectors to each chunk.

Dense vector:  nomic-embed-text via ollama_client.embed() (768 dims).
Sparse vector: BM25 via fastembed SparseTextEmbedding model "Qdrant/bm25".

Both vectors are stored in Qdrant for hybrid search (prefetch + RRF fusion).
"""

from __future__ import annotations

from fastembed import SparseTextEmbedding
from models.ollama_client import embed

_EMBEDDING_MODEL = "nomic-embed-text"
_BM25_MODEL = "Qdrant/bm25"

_sparse_model: SparseTextEmbedding | None = None


def _get_sparse_model() -> SparseTextEmbedding:
    global _sparse_model
    if _sparse_model is None:
        _sparse_model = SparseTextEmbedding(model_name=_BM25_MODEL)
    return _sparse_model


async def embed_chunks(chunks: list[dict]) -> list[dict]:
    """Add dense_vector and sparse_vector to each chunk dict.

    Dense embeddings are fetched sequentially from Ollama to avoid overloading it.
    Sparse BM25 vectors are computed locally via fastembed (no network call).
    """
    texts = [c["text"] for c in chunks]

    sparse_model = _get_sparse_model()
    sparse_results = list(sparse_model.embed(texts))

    embedded: list[dict] = []
    for i, chunk in enumerate(chunks):
        dense_vec = await embed(_EMBEDDING_MODEL, chunk["text"])
        sparse = sparse_results[i]
        embedded.append({
            **chunk,
            "dense_vector": dense_vec,
            "sparse_indices": sparse.indices.tolist(),
            "sparse_values": sparse.values.tolist(),
        })

    return embedded
