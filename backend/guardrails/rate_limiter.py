"""Rate limiter — per-user sliding window counters in Redis.

Keys:
    ratelimit:chat:{user_id}:{YYYYMMDD_HH}   → int  (60 req/hr max)
    ratelimit:ingest:{user_id}:{YYYYMMDD_HH} → int  (10 req/hr max)
    quota:{user_id}:{YYYYMMDD}               → int  (daily total, no hard cap — analytics only)

TTL: 3600s (auto-expire after the hour window closes).
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException, status
import memory.session_memory as _session_memory
from middleware.metrics import rate_limit_exceeded as _metric_rate_limit


def _redis():
    """Access pool lazily so we always get the initialized instance."""
    return _session_memory.redis_pool

CHAT_LIMIT_PER_HOUR = 60
INGEST_LIMIT_PER_HOUR = 10


def _hour_key(prefix: str, user_id: str) -> str:
    now = datetime.now(timezone.utc)
    window = now.strftime("%Y%m%d_%H")
    return f"ratelimit:{prefix}:{user_id}:{window}"


def _day_key(user_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"quota:{user_id}:{today}"


async def check_chat_rate(user_id: str | UUID) -> None:
    """Raise HTTP 429 if user exceeds 60 chat messages/hr."""
    if os.getenv("DISABLE_RATE_LIMIT"):
        return
    r = _redis()
    uid = str(user_id)
    key = _hour_key("chat", uid)
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, 3600)
    day_key = _day_key(uid)
    await r.incr(day_key)
    await r.expire(day_key, 86400)

    if count > CHAT_LIMIT_PER_HOUR:
        _metric_rate_limit(uid, "chat")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"เกินขีดจำกัด {CHAT_LIMIT_PER_HOUR} ข้อความต่อชั่วโมง กรุณารอแล้วลองใหม่",
            headers={"Retry-After": "3600"},
        )


async def check_ingest_rate(user_id: str | UUID) -> None:
    """Raise HTTP 429 if user exceeds 10 ingestion requests/hr."""
    r = _redis()
    uid = str(user_id)
    key = _hour_key("ingest", uid)
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, 3600)

    if count > INGEST_LIMIT_PER_HOUR:
        _metric_rate_limit(uid, "ingest")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"เกินขีดจำกัด {INGEST_LIMIT_PER_HOUR} คำขอต่อชั่วโมง",
            headers={"Retry-After": "3600"},
        )


async def get_usage(user_id: str | UUID) -> dict:
    """Return current hour + today usage counts for a user (admin/debug use)."""
    r = _redis()
    uid = str(user_id)
    chat_hr = await r.get(_hour_key("chat", uid))
    ingest_hr = await r.get(_hour_key("ingest", uid))
    day_total = await r.get(_day_key(uid))

    return {
        "chat_this_hour": int(chat_hr or 0),
        "chat_limit_per_hour": CHAT_LIMIT_PER_HOUR,
        "ingest_this_hour": int(ingest_hr or 0),
        "ingest_limit_per_hour": INGEST_LIMIT_PER_HOUR,
        "total_today": int(day_total or 0),
    }
