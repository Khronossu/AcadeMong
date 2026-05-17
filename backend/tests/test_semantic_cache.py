"""Unit tests for memory/semantic_cache.py.

Redis is mocked via unittest.mock so these tests run without a live Redis instance.
The semantic_cache module imports redis_pool from session_memory at module-load time,
so we patch it at the source using monkeypatch.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import memory.semantic_cache as sc
from memory.semantic_cache import _embedding_cache_key


# ── Cache key determinism ─────────────────────────────────────────────────────

def test_same_vector_produces_same_key():
    v = [0.1] * 768
    assert _embedding_cache_key(v) == _embedding_cache_key(v)


def test_different_vectors_produce_different_keys():
    v1 = [0.1] * 768
    v2 = [0.2] * 768
    assert _embedding_cache_key(v1) != _embedding_cache_key(v2)


def test_key_has_correct_prefix_and_length():
    key = _embedding_cache_key([0.5] * 768)
    assert key.startswith("rag_cache:")
    # prefix (10 chars) + colon already counted + 16 hex chars
    assert len(key) == len("rag_cache:") + 16


def test_key_is_deterministic_across_calls():
    v = [float(i) / 1000 for i in range(768)]
    k1 = _embedding_cache_key(v)
    k2 = _embedding_cache_key(v)
    assert k1 == k2


def test_short_vector_does_not_crash():
    """Vectors shorter than 64 dims are handled gracefully."""
    key = _embedding_cache_key([0.1] * 10)
    assert key.startswith("rag_cache:")


# ── get_cached_rag ────────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis(monkeypatch):
    """Return a MagicMock redis pool patched into the semantic_cache module."""
    pool = MagicMock()
    monkeypatch.setattr(sc, "redis_pool", pool)
    return pool


async def test_get_returns_none_on_cache_miss(mock_redis):
    mock_redis.get = AsyncMock(return_value=None)
    result = await sc.get_cached_rag([0.1] * 768)
    assert result is None


async def test_get_returns_chunks_on_cache_hit(mock_redis):
    chunks = ["chunk A", "chunk B"]
    mock_redis.get = AsyncMock(return_value=json.dumps(chunks))
    result = await sc.get_cached_rag([0.1] * 768)
    assert result == chunks


async def test_get_returns_none_when_pool_is_none(monkeypatch):
    monkeypatch.setattr(sc, "redis_pool", None)
    result = await sc.get_cached_rag([0.1] * 768)
    assert result is None


async def test_get_returns_none_on_redis_error(mock_redis):
    mock_redis.get = AsyncMock(side_effect=ConnectionError("Redis down"))
    result = await sc.get_cached_rag([0.1] * 768)
    assert result is None


# ── set_cached_rag ────────────────────────────────────────────────────────────

async def test_set_stores_chunks_without_ttl(mock_redis):
    mock_redis.set = AsyncMock()
    chunks = ["chunk X", "chunk Y"]
    vec = [0.3] * 768
    await sc.set_cached_rag(vec, chunks)

    key = _embedding_cache_key(vec)
    mock_redis.set.assert_called_once_with(key, json.dumps(chunks))


async def test_set_does_nothing_when_pool_is_none(monkeypatch):
    monkeypatch.setattr(sc, "redis_pool", None)
    # Should not raise
    await sc.set_cached_rag([0.1] * 768, ["chunk"])


async def test_set_silently_ignores_redis_error(mock_redis):
    mock_redis.set = AsyncMock(side_effect=ConnectionError("Redis down"))
    # Should not raise
    await sc.set_cached_rag([0.1] * 768, ["chunk"])


async def test_set_then_get_round_trip(mock_redis):
    """set then get with the same vector returns the same chunks."""
    chunks = ["สวัสดี", "AcadeMong"]
    vec = [0.7] * 768
    stored: dict = {}

    async def fake_set(key, val):
        stored[key] = val

    async def fake_get(key):
        return stored.get(key)

    mock_redis.set = fake_set
    mock_redis.get = fake_get

    await sc.set_cached_rag(vec, chunks)
    result = await sc.get_cached_rag(vec)
    assert result == chunks


# ── flush_rag_cache ───────────────────────────────────────────────────────────

async def test_flush_deletes_all_rag_keys(mock_redis):
    existing_keys = ["rag_cache:abc123", "rag_cache:def456"]
    mock_redis.keys = AsyncMock(return_value=existing_keys)
    mock_redis.delete = AsyncMock(return_value=2)

    count = await sc.flush_rag_cache()
    assert count == 2
    mock_redis.delete.assert_called_once_with(*existing_keys)


async def test_flush_returns_zero_when_no_keys(mock_redis):
    mock_redis.keys = AsyncMock(return_value=[])
    count = await sc.flush_rag_cache()
    assert count == 0


async def test_flush_returns_zero_when_pool_is_none(monkeypatch):
    monkeypatch.setattr(sc, "redis_pool", None)
    count = await sc.flush_rag_cache()
    assert count == 0


async def test_flush_returns_zero_on_redis_error(mock_redis):
    mock_redis.keys = AsyncMock(side_effect=ConnectionError("Redis down"))
    count = await sc.flush_rag_cache()
    assert count == 0


async def test_flush_uses_correct_key_pattern(mock_redis):
    mock_redis.keys = AsyncMock(return_value=[])
    await sc.flush_rag_cache()
    mock_redis.keys.assert_called_once_with("rag_cache:*")
