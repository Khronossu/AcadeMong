"""RAG engine — dense retrieval with cross-encoder reranking.

Retrieval pipeline (per CLAUDE.md §6.3):
  1. Metadata filter (year, university) applied at Qdrant query time.
  2. Dense search via nomic-embed-text (top PREFETCH_K candidates).
  3. Cross-encoder (BAAI/bge-reranker-base) reranks candidates.
  4. Returns top RERANKER_TOP_K chunk texts prefixed with source info.

Note: BM25 sparse vectors planned but deferred — fastembed's onnxruntime
has no Python 3.14 wheels. Dense + reranker is the active retrieval strategy.

Graceful degradation: returns [] if Qdrant is unreachable so tcas_rag still
functions from SQL eligibility data alone.
"""

from __future__ import annotations

import os

from qdrant_client.models import FieldCondition, Filter, MatchValue
from sentence_transformers import CrossEncoder

from db.qdrant_client import TCAS_COLLECTION, get_qdrant_client
from models.ollama_client import embed

_EMBEDDING_MODEL = "nomic-embed-text"
_RERANKER_MODEL = "BAAI/bge-reranker-base"
_PREFETCH_K = 20

_reranker: CrossEncoder | None = None


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
        query_filter = _build_filter(filters)

        results = client.search(
            collection_name=TCAS_COLLECTION,
            query_vector=dense_vec,
            query_filter=query_filter,
            limit=_PREFETCH_K,
            with_payload=True,
        )

        if not results:
            return []

        candidates = [(r.payload["text"], r.payload) for r in results]
        pairs = [(query, text) for text, _ in candidates]

        reranker = _get_reranker()
        scores = reranker.predict(pairs)

        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)

        chunks = []
        for _, (text, payload) in ranked[:top_k]:
            university = payload.get("university") or ""
            page = payload.get("page", "?")
            prefix = f"[ที่มา: {university} หน้า {page}]" if university else f"[หน้า {page}]"
            chunks.append(f"{prefix}\n{text}")

        return chunks

    except Exception:
        return []
