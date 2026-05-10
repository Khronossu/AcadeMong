"""Qdrant ingester — collection management and chunk upsert.

Collection schema:
  - Named dense vector  "dense"  — 768 dims (nomic-embed-text), cosine distance
  - Named sparse vector "sparse" — BM25 (fastembed Qdrant/bm25)

Point ID is deterministic: SHA-256(doc_hash + chunk_index) truncated to 16 hex chars
then cast to int, so re-running the ingester is idempotent (same chunk = same ID).
"""

from __future__ import annotations

import hashlib

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

from db.qdrant_client import TCAS_COLLECTION

_DENSE_DIM = 768


def _chunk_id(doc_hash: str, chunk_index: int) -> int:
    """Stable integer point ID from (doc_hash, chunk_index)."""
    raw = f"{doc_hash}:{chunk_index}".encode()
    return int(hashlib.sha256(raw).hexdigest()[:16], 16)


def init_collection(client: QdrantClient) -> None:
    """Create tcas_docs collection if it doesn't already exist."""
    existing = {c.name for c in client.get_collections().collections}
    if TCAS_COLLECTION in existing:
        return

    client.create_collection(
        collection_name=TCAS_COLLECTION,
        vectors_config={
            "dense": VectorParams(size=_DENSE_DIM, distance=Distance.COSINE),
        },
        sparse_vectors_config={
            "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False)),
        },
    )


def upsert_chunks(client: QdrantClient, embedded_chunks: list[dict]) -> int:
    """Upsert embedded chunks into Qdrant. Returns count of points upserted."""
    if not embedded_chunks:
        return 0

    points = [
        PointStruct(
            id=_chunk_id(c["doc_hash"], c["chunk_index"]),
            vector={
                "dense": c["dense_vector"],
                "sparse": {
                    "indices": c["sparse_indices"],
                    "values": c["sparse_values"],
                },
            },
            payload={
                "text": c["text"],
                "page": c["page"],
                "chunk_index": c["chunk_index"],
                "doc_hash": c["doc_hash"],
                "source_path": c["source_path"],
                "university": c.get("university"),
                "major": c.get("major"),
                "round": c.get("round"),
                "year": c.get("year"),
                "source_url": c.get("source_url", ""),
            },
        )
        for c in embedded_chunks
    ]

    client.upsert(collection_name=TCAS_COLLECTION, points=points)
    return len(points)
