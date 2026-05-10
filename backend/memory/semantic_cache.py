"""Semantic cache for RAG retrieval — reduces repeat Qdrant + reranker calls.

Cache key: SHA-256 of the first 64 dense-embedding floats quantized to int8.
  - Same query text → same nomic-embed-text output → same key → cache hit.
  - Near-duplicate queries that share the same embedding also hit.

Permanence strategy:
  - No TTL. Entries persist until explicitly flushed.
  - flush_rag_cache() is called by the PDF ingestion pipeline (ingest_pdfs.py)
    after a successful Qdrant indexing run, ensuring the cache never serves
    chunks that were superseded by updated PDFs.

Graceful degradation: all public functions catch Redis errors and return
None / 0 so the RAG engine continues without caching on connectivity issues.
"""

from __future__ import annotations

import hashlib
import json
import logging
import struct

from memory.session_memory import redis_pool

logger = logging.getLogger(__name__)

_KEY_PREFIX = "rag_cache"


def _embedding_cache_key(dense_vec: list[float]) -> str:
    """Return a deterministic Redis key for the given dense embedding vector.

    Quantizes the first 64 dimensions to signed int8 (clipping to [-127, 127]),
    packs them to bytes, and takes the first 16 hex chars of SHA-256.
    """
    sample = dense_vec[:64]
    quantized = bytes(
        max(-127, min(127, int(round(v * 127)))) & 0xFF
        for v in sample
    )
    digest = hashlib.sha256(quantized).hexdigest()[:16]
    return f"{_KEY_PREFIX}:{digest}"


async def get_cached_rag(dense_vec: list[float]) -> list[str] | None:
    """Return cached RAG chunks for this embedding, or None on miss/error."""
    if not redis_pool:
        return None
    try:
        key = _embedding_cache_key(dense_vec)
        raw = await redis_pool.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.debug("Semantic cache GET failed (degraded): %s", exc)
        return None


async def set_cached_rag(dense_vec: list[float], chunks: list[str]) -> None:
    """Persist RAG chunks to Redis permanently (no TTL)."""
    if not redis_pool:
        return
    try:
        key = _embedding_cache_key(dense_vec)
        await redis_pool.set(key, json.dumps(chunks))
    except Exception as exc:
        logger.debug("Semantic cache SET failed (degraded): %s", exc)


async def flush_rag_cache() -> int:
    """Delete all rag_cache:* keys from Redis. Returns the number of keys deleted.

    Called by the PDF ingestion pipeline after a successful Qdrant re-index so
    stale chunk results are never served from cache.
    """
    if not redis_pool:
        return 0
    try:
        keys = await redis_pool.keys(f"{_KEY_PREFIX}:*")
        if not keys:
            return 0
        return await redis_pool.delete(*keys)
    except Exception as exc:
        logger.warning("Semantic cache flush failed: %s", exc)
        return 0
