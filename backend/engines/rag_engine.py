"""RAG engine — hybrid BM25+dense retrieval with cross-encoder reranking.

Retrieval pipeline (per CLAUDE.md §6.3):
  1. Metadata filter (year, university) applied at Qdrant query time.
  2. Dense search (nomic-embed-text) + sparse BM25 search run in parallel.
  3. Results merged via Reciprocal Rank Fusion (RRF, k=60).
  4. Top-20 RRF candidates reranked by cross-encoder (BAAI/bge-reranker-base).
  5. Returns top RERANKER_TOP_K chunk texts prefixed with source info.

Uses AsyncQdrantClient for non-blocking I/O in the FastAPI runtime.

Graceful degradation: returns [] if Qdrant is unreachable so tcas_rag
still functions from SQL eligibility data alone (no exception propagation).
"""

from __future__ import annotations

import asyncio
import os

from fastembed import SparseTextEmbedding
from qdrant_client.http.models import FieldCondition, Filter, MatchValue, NamedSparseVector, NamedVector, SparseVector
from sentence_transformers import CrossEncoder

from db.qdrant_client import TCAS_COLLECTION, get_async_qdrant_client
from memory.semantic_cache import get_cached_rag, set_cached_rag
from models.ollama_client import embed

_EMBEDDING_MODEL = "nomic-embed-text"
_BM25_MODEL = "Qdrant/bm25"
_RERANKER_MODEL = "BAAI/bge-reranker-base"
_PREFETCH_K = 20
_RRF_K = 60

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


def _rrf_merge(
    dense_hits: list,
    sparse_hits: list,
    k: int = _RRF_K,
) -> list[tuple[float, object]]:
    """Reciprocal Rank Fusion: merge two ranked lists into one by score."""
    scores: dict[int, float] = {}
    payloads: dict[int, object] = {}

    for rank, hit in enumerate(dense_hits):
        scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (k + rank + 1)
        payloads[hit.id] = hit.payload

    for rank, hit in enumerate(sparse_hits):
        scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (k + rank + 1)
        if hit.id not in payloads:
            payloads[hit.id] = hit.payload

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(score, payloads[pid]) for pid, score in ranked]


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
        client = get_async_qdrant_client()
        query_filter = _build_filter(filters)

        dense_vec, sparse_result = await asyncio.gather(
            embed(_EMBEDDING_MODEL, query),
            asyncio.to_thread(lambda: next(_get_sparse_model().embed([query]))),
        )

        cached = await get_cached_rag(dense_vec)
        if cached is not None:
            return cached[:top_k]

        sparse_vec = SparseVector(
            indices=sparse_result.indices.tolist(),
            values=sparse_result.values.tolist(),
        )

        dense_hits, sparse_hits = await asyncio.gather(
            client.search(
                collection_name=TCAS_COLLECTION,
                query_vector=NamedVector(name="dense", vector=dense_vec),
                query_filter=query_filter,
                limit=_PREFETCH_K,
                with_payload=True,
            ),
            client.search(
                collection_name=TCAS_COLLECTION,
                query_vector=NamedSparseVector(name="sparse", vector=sparse_vec),
                query_filter=query_filter,
                limit=_PREFETCH_K,
                with_payload=True,
            ),
        )

        merged = _rrf_merge(dense_hits, sparse_hits)
        if not merged:
            return []

        candidates = [(payload["text"], payload) for _, payload in merged]
        pairs = [(query, text) for text, _ in candidates]

        reranker = _get_reranker()
        scores = await asyncio.to_thread(reranker.predict, pairs)

        ranked = sorted(zip(scores, candidates), key=lambda x: x[0], reverse=True)

        chunks = []
        for _, (text, payload) in ranked[:top_k]:
            university = payload.get("university") or ""
            page = payload.get("page", "?")
            prefix = f"[ที่มา: {university} หน้า {page}]" if university else f"[หน้า {page}]"
            chunks.append(f"{prefix}\n{text}")

        await set_cached_rag(dense_vec, chunks)
        return chunks

    except Exception:
        return []
