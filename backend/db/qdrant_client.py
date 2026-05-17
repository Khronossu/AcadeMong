"""Qdrant client singleton — mirrors the postgres.py pattern.

A single QdrantClient instance is created on first access and reused for
the lifetime of the process. The client connects to the Qdrant service
whose address is read from QDRANT_HOST / QDRANT_PORT env vars.
"""

from __future__ import annotations

import os

from qdrant_client import AsyncQdrantClient, QdrantClient

TCAS_COLLECTION = "tcas_docs"
CAREERS_COLLECTION = "careers"

_client: QdrantClient | None = None
_async_client: AsyncQdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    """Sync client — used by ingestion CLI scripts."""
    global _client
    if _client is None:
        host = os.getenv("QDRANT_HOST", "qdrant")
        port = int(os.getenv("QDRANT_PORT", 6333))
        _client = QdrantClient(host=host, port=port)
    return _client


def get_async_qdrant_client() -> AsyncQdrantClient:
    """Async client — used by the FastAPI runtime (rag_engine)."""
    global _async_client
    if _async_client is None:
        host = os.getenv("QDRANT_HOST", "qdrant")
        port = int(os.getenv("QDRANT_PORT", 6333))
        _async_client = AsyncQdrantClient(host=host, port=port)
    return _async_client
