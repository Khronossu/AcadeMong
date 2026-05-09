"""Request orchestrator — routes a user message through the correct AI flow.

Flow A (dreamer):  profile → compose_dreamer_prompt → Typhoon2 → response
Flow B (tcas_rag): profile → check_eligibility → compose_tcas_prompt → Typhoon2 → response

After generation the orchestrator:
  1. Saves both the user message and the AI response to chat_messages (Postgres).
  2. Appends both to the Redis chat window for the next turn's context.

RAG retrieval (Phase 6) will be inserted into handle_tcas_message between the
eligibility check and the Ollama call — the slot is intentionally left open.
"""

from __future__ import annotations

from uuid import UUID

from db.postgres import fetchrow
from engines.eligibility_engine import check_eligibility
from engines.prompt_composer import compose_dreamer_prompt, compose_tcas_prompt
from memory.long_term_memory import save_message
from memory.session_memory import append_to_chat_window, get_chat_window, get_user_session
from models.model_router import get_model_config
from models.ollama_client import chat


async def _load_user_profile(user_id: UUID) -> dict:
    """Return the user's profile dict, preferring the Redis cache over a DB hit."""
    cached = await get_user_session(str(user_id))
    if cached:
        return cached
    row = await fetchrow(
        "SELECT gpax, current_school FROM user_profiles WHERE user_id = $1",
        user_id,
    )
    return dict(row) if row else {}


async def handle_dreamer_message(
    user_id: UUID,
    session_id: UUID,
    content: str,
    history: list[dict],
) -> str:
    """Generate a Flow A (Career Dreamer) response via Typhoon2."""
    profile = await _load_user_profile(user_id)
    system_prompt = compose_dreamer_prompt(profile)
    cfg = get_model_config("dreamer_chat")
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": content}]
    return await chat(cfg["model"], messages, cfg["temperature"], cfg["top_p"], cfg["max_tokens"])
