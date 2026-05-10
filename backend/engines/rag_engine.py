"""RAG engine — hybrid BM25+dense retrieval with cross-encoder reranking.

Retrieval pipeline (per CLAUDE.md §6.3):
  1. Metadata filter (year, university) applied at Qdrant query time.
  2. Prefetch dense results (nomic-embed-text) + sparse BM25 results.
  3. Single Qdrant query_points call fuses both via Reciprocal Rank Fusion.
  4. Top-20 candidates sent to cross-encoder (BAAI/bge-reranker-base).
  5. Returns top RERANKER_TOP_K chunk texts, each prefixed with source info.

Graceful degradation: if Qdrant is unreachable, returns [] so tcas_rag
still functions from SQL eligibility data alone (no exception propagation).
"""

from __future__ import annotations

import os

from fastembed import SparseTextEmbedding
from qdrant_client.models import Filter, FieldCondition, MatchValue, Prefetch, FusionQuery, Fusion
from sentence_transformers import CrossEncoder

from db.qdrant_client import TCAS_COLLECTION, get_qdrant_client
from models.ollama_client import embed

_EMBEDDING_MODEL = "nomic-embed-text"
_BM25_MODEL = "Qdrant/bm25"
_RERANKER_MODEL = "BAAI/bge-reranker-base"
_PREFETCH_K = 20

_sparse_model: SparseTextEmbedding | None = None
_reranker: CrossEncoder | None = None


def _get_sparse_model() -> SparseTextEmbedding:
    global _sparse_model
    if _sparse_model is None:
        _sparse_model = SparseTextEmbedding(model_name=_BM25_MODEL)
    return _sparse_model


def _get_reranker() -> CrossEncoder:
    global _reranker
    if _reranker is None:
        _reranker = CrossEncoder(_RERANKER_MODEL)
    return _reranker


def _build_filter(filters: dict | None) -> Filter | None:
    if not filters:
        return None
    conditions = []
    if filters.get("university"):
        conditions.append(FieldCondition(key="university", match=MatchValue(value=filters["university"])))
    if filters.get("year"):
        conditions.append(FieldCondition(key="year", match=MatchValue(value=filters["year"])))
    return Filter(must=conditions) if conditions else None


async def retrieve_context(
    query: str,
    filters: dict | None = None,
    top_k: int | None = None,
) -> list[str]:
    """Return top-K relevant chunk texts for the given query.

    Args:
        query:   User's natural-language question.
        filters: Optional dict with "university" and/or "year" keys.
        top_k:   Number of chunks to return (default: RERANKER_TOP_K env var or 3).

    Returns [] on Qdrant connection error (graceful degradation).
    """
    if top_k is None:
        top_k = int(os.getenv("RERANKER_TOP_K", 3))

    try:
        client = get_qdrant_client()

        dense_vec = await embed(_EMBEDDING_MODEL, query)

        sparse_model = _get_sparse_model()
        sparse_result = next(sparse_model.embed([query]))
        sparse_vec = {"indices": sparse_result.indices.tolist(), "values": sparse_result.values.tolist()}

        query_filter = _build_filter(filters)

        results = client.query_points(
            collection_name=TCAS_COLLECTION,
            prefetch=[
                Prefetch(query=dense_vec, using="dense", limit=_PREFETCH_K, filter=query_filter),
                Prefetch(query=sparse_vec, using="sparse", limit=_PREFETCH_K, filter=query_filter),
            ],
            query=FusionQuery(fusion=Fusion.RRF),
            limit=_PREFETCH_K,
        ).points

        if not results:
            return []

        candidates = [(r.payload["text"], r.payload) for r in results]
        pairs = [(query, text) for text, _ in candidates]

        reranker = _get_reranker()
        scores = reranker.predict(pairs)

        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)

        chunks = []
        for _, (text, payload) in ranked[:top_k]:
            source = payload.get("source_url") or payload.get("source_path", "")
            university = payload.get("university") or ""
            page = payload.get("page", "?")
            prefix = f"[ที่มา: {university} หน้า {page}]" if university else f"[หน้า {page}]"
            chunks.append(f"{prefix}\n{text}")

        return chunks

    except Exception:
        return []
