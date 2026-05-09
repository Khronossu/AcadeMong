"""Long-term memory — PostgreSQL helpers for chat sessions and messages.

Why a separate module from session_memory?
  session_memory.py owns Redis (fast, ephemeral, per-session window).
  long_term_memory.py owns Postgres (durable, queryable, full history).
  Keeping them separate means each can be swapped or tested independently.
"""

from __future__ import annotations

from uuid import UUID

from db.postgres import execute, fetch, fetchrow


async def create_chat_session(user_id: UUID, ai_mode: str) -> UUID:
    """Insert a new chat_sessions row and return its id."""
    row = await fetchrow(
        "INSERT INTO chat_sessions (user_id, ai_mode) VALUES ($1, $2) RETURNING id",
        user_id, ai_mode,
    )
    return row["id"]


async def save_message(session_id: UUID, role: str, content: str) -> UUID:
    """Persist one chat_messages row and return its id."""
    row = await fetchrow(
        "INSERT INTO chat_messages (session_id, role, content) VALUES ($1, $2, $3) RETURNING id",
        session_id, role, content,
    )
    return row["id"]


async def get_session(session_id: UUID) -> dict | None:
    """Fetch a chat_sessions row by id, or None if not found.

    Includes user_id so callers can verify ownership before exposing
    session data to the requesting user.
    """
    row = await fetchrow(
        "SELECT id, user_id, ai_mode, created_at FROM chat_sessions WHERE id = $1",
        session_id,
    )
    return dict(row) if row else None
