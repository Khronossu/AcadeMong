import os
import json
from typing import Optional
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal

import redis.asyncio as aioredis

redis_pool: Optional[aioredis.Redis] = None


def init_redis_pool():
    """Initializes the Redis connection pool."""
    global redis_pool
    if redis_pool is None:
        redis_host = os.getenv('REDIS_HOST')
        redis_port = os.getenv('REDIS_PORT')

        if not redis_host or not redis_port:
            raise ValueError(
                "REDIS_HOST and REDIS_PORT environment variables must be set."
            )

        redis_pool = aioredis.from_url(
            f"redis://{redis_host}:{redis_port}",
            encoding="utf-8",
            decode_responses=True
        )


async def close_redis_pool():
    """Closes the Redis connection pool."""
    if redis_pool:
        await redis_pool.close()


def _session_serializer(obj):
    """Helper to serialize types not supported by default json."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


async def set_user_session(user_id: str, session_data: dict, expires_in_seconds: int = 3600):
    if not redis_pool:
        raise ConnectionError("Redis pool is not initialized.")
    session_key = f"session:{user_id}:profile"
    profile_json = json.dumps(session_data, default=_session_serializer)
    await redis_pool.set(session_key, profile_json, ex=expires_in_seconds)


async def get_user_session(user_id: str) -> dict | None:
    if not redis_pool:
        raise ConnectionError("Redis pool is not initialized.")
    session_key = f"session:{user_id}:profile"
    raw = await redis_pool.get(session_key)
    return json.loads(raw) if raw else None


_WINDOW_SIZE = 10  # max messages kept hot in Redis per session


async def get_chat_window(user_id: str, session_id: str) -> list[dict]:
    """Return the in-session message window from Redis (empty list if not found)."""
    if not redis_pool:
        raise ConnectionError("Redis pool is not initialized.")
    raw = await redis_pool.get(f"session:{user_id}:{session_id}:window")
    return json.loads(raw) if raw else []


async def set_chat_window(user_id: str, session_id: str, messages: list[dict], ttl: int = 7200):
    """Overwrite the message window in Redis. TTL defaults to 2 hours."""
    if not redis_pool:
        raise ConnectionError("Redis pool is not initialized.")
    await redis_pool.set(
        f"session:{user_id}:{session_id}:window",
        json.dumps(messages, default=_session_serializer),
        ex=ttl,
    )


async def append_to_chat_window(user_id: str, session_id: str, role: str, content: str, ttl: int = 7200):
    """Append one message to the window, trimming to _WINDOW_SIZE most recent."""
    messages = await get_chat_window(user_id, session_id)
    messages.append({"role": role, "content": content})
    if len(messages) > _WINDOW_SIZE:
        messages = messages[-_WINDOW_SIZE:]
    await set_chat_window(user_id, session_id, messages, ttl=ttl)
