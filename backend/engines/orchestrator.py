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
from engines.rag_engine import retrieve_context
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


async def handle_tcas_message(
    user_id: UUID,
    session_id: UUID,
    content: str,
    history: list[dict],
) -> str:
    """Generate a Flow B (TCAS advisor) response grounded in SQL eligibility data + RAG."""
    profile = await _load_user_profile(user_id)
    eligibility = await check_eligibility(user_id=user_id)
    rag_context = await retrieve_context(content)
    system_prompt = compose_tcas_prompt(profile, eligibility, rag_context)
    cfg = get_model_config("tcas_chat")
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": content}]
    return await chat(cfg["model"], messages, cfg["temperature"], cfg["top_p"], cfg["max_tokens"])


async def handle_message(
    session_id: UUID,
    user_id: UUID,
    ai_mode: str,
    content: str,
) -> str:
    """Top-level dispatcher: load context → generate response → persist → return.

    Order matters:
      1. Load Redis window (fast, recent context for the model).
      2. Generate response (the only slow step — Ollama call).
      3. Persist to DB (durable history).
      4. Update Redis window (so next turn has fresh context).
    """
    history = await get_chat_window(str(user_id), str(session_id))

    if ai_mode == "dreamer":
        response = await handle_dreamer_message(user_id, session_id, content, history)
    else:
        response = await handle_tcas_message(user_id, session_id, content, history)

    await save_message(session_id, "user", content)
    await save_message(session_id, "assistant", response)

    await append_to_chat_window(str(user_id), str(session_id), "user", content)
    await append_to_chat_window(str(user_id), str(session_id), "assistant", response)

    return response
