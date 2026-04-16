"""Postgres connection pool for AcadeMong.

Owns a single asyncpg pool shared across the app.
- Call `init_pool()` once on FastAPI startup (via lifespan).
- Call `close_pool()` once on shutdown.
- Anywhere in between, call `get_pool()` or use the helpers (fetch/fetchrow/execute).

Why a pool instead of opening a connection per request?
  Opening a Postgres connection costs a TCP handshake + auth (~10-50ms).
  A pool holds N pre-authenticated connections ready to go; acquiring one
  is near-instant. It also caps concurrency so 1000 concurrent requests
  don't open 1000 Postgres connections and kill the DB.
"""
import os
from typing import Optional

import asyncpg

# ── Module-level singleton ────────────────────────────────────────────────
# Python caches modules on import: everywhere that writes
#   `from db.postgres import get_pool`
# sees the SAME `_pool` variable. So a module-level variable is the
# simplest "global across the app" pattern.
#
# The leading underscore is a convention meaning "private". Nothing
# enforces it, but teammates know not to read/write `_pool` directly
# from outside this file — they should go through the functions below.
_pool: Optional[asyncpg.Pool] = None


# ── Lifecycle ──────────────────────────────────────────────────────────────
async def init_pool(min_size: int = 1, max_size: int = 10) -> asyncpg.Pool:
    """Create the shared pool. Idempotent: safe to call more than once.

    Called once on app startup. Reading env vars here (not at module top)
    means the module can be imported in tests without needing env set up.
    """
    # `global` is required because we REASSIGN _pool. Without it, Python
    # would create a new local variable shadowing the module-level one.
    global _pool

    # Idempotent guard: if already initialized, return existing pool.
    # This matters if startup is called twice (e.g., in tests, or if
    # FastAPI lifespan runs more than once for some reason).
    if _pool is not None:
        return _pool

    _pool = await asyncpg.create_pool(
        # Connection params from environment. Never hardcode credentials.
        host=os.getenv("POSTGRES_HOST"),
        # Default to "5432" string so int() always has something to parse.
        # If the env var is truly missing, this still fails loudly later,
        # which is what we want — loud failure > silent wrong connection.
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),

        # Pool sizing. For a single-instance POC these are sane defaults:
        #   min_size=1  → at least one warm connection always ready
        #   max_size=10 → cap concurrent DB work to protect Postgres
        # Tune upward if you see connection queuing under load.
        min_size=min_size,
        max_size=max_size,

        # Kills queries that run longer than 10s. Without this, a bad
        # query can hold a connection forever and starve the pool.
        command_timeout=10,
    )
    return _pool


async def close_pool() -> None:
    """Close the pool on shutdown. Safe to call if already closed."""
    global _pool

    # Nothing to do if never initialized or already closed.
    if _pool is None:
        return

    # Waits for in-flight queries to finish (up to the pool's close timeout),
    # then releases all connections cleanly.
    await _pool.close()

    # Reset to None so a later init_pool() would create a fresh pool.
    # Forgetting this line is a classic bug: the pool is closed but
    # _pool still points to the closed object, and get_pool() happily
    # hands out a dead reference.
    _pool = None


def get_pool() -> asyncpg.Pool:
    """Return the initialized pool. Raise if init_pool() wasn't called.

    Sync, not async: fetching the reference is just reading a variable.
    No I/O involved, no reason to make callers `await` it.
    """
    # Fail LOUDLY and EARLY if someone tries to query before the pool
    # exists. Silent auto-init here would hide bugs (e.g., a worker
    # starting up before the main app is ready).
    if _pool is None:
        raise RuntimeError(
            "Postgres pool not initialized. "
            "Make sure init_pool() is awaited on app startup."
        )
    return _pool


# ── Thin helpers ───────────────────────────────────────────────────────────
# These are optional sugar around `async with pool.acquire() as conn`.
# They exist so routes don't repeat the acquire/release dance on every
# query. If you need a transaction or multiple queries on the same
# connection, use `get_pool().acquire()` directly.

async def fetch(query: str, *args) -> list[asyncpg.Record]:
    """Run a query, return ALL rows as a list of asyncpg.Record.

    Use for SELECTs that return many rows.
    Records behave like both dicts (`row["name"]`) and tuples (`row[0]`).
    """
    # `async with` guarantees the connection is returned to the pool
    # even if the query raises. This is the #1 source of "mysteriously
    # exhausted pool" bugs — always use the context manager.
    async with get_pool().acquire() as conn:
        return await conn.fetch(query, *args)


async def fetchrow(query: str, *args) -> Optional[asyncpg.Record]:
    """Run a query, return the FIRST row or None if no rows.

    Use for SELECTs expecting 0 or 1 row (e.g., lookup by primary key).
    """
    async with get_pool().acquire() as conn:
        return await conn.fetchrow(query, *args)


async def execute(query: str, *args) -> str:
    """Run INSERT/UPDATE/DELETE, return the status string.

    asyncpg returns a tag like 'INSERT 0 1' (1 row inserted) or
    'UPDATE 3' (3 rows updated). Parse it if you care about affected
    row count; usually you don't.
    """
    async with get_pool().acquire() as conn:
        return await conn.execute(query, *args)


async def ping() -> bool:
    """Sanity check: the pool is alive and the DB responds to a trivial query.

    Use this in health endpoints instead of opening a fresh connection.
    """
    row = await fetchrow("SELECT 1 AS ok")
    # Defensive: check both that we got a row AND that the value is right.
    # If you just checked `row is not None`, a DB returning weird data
    # would still pass — unlikely but cheap to guard against.
    return row is not None and row["ok"] == 1
