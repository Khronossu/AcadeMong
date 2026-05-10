"""Qdrant client singleton — mirrors the postgres.py pattern.

A single QdrantClient instance is created on first access and reused for
the lifetime of the process. The client connects to the Qdrant service
whose address is read from QDRANT_HOST / QDRANT_PORT env vars.
"""

from __future__ import annotations

import os

from qdrant_client import QdrantClient

TCAS_COLLECTION = "tcas_docs"

_client: QdrantClient | None = None


def get_qdrant_client() -> QdrantClient:
    global _client
    if _client is None:
        host = os.getenv("QDRANT_HOST", "qdrant")
        port = int(os.getenv("QDRANT_PORT", 6333))
        _client = QdrantClient(host=host, port=port)
    return _client
