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
from engines.career_matcher import get_career_suggestions
from engines.eligibility_engine import check_eligibility
from engines.prompt_composer import compose_dreamer_prompt, compose_tcas_prompt
from engines.rag_engine import retrieve_context
from guardrails.numeric_validator import validate_numeric_claims
from guardrails.safety_filter import check_safety
from db.postgres import execute as _db_execute
from middleware.metrics import (
    guardrail_numeric_stripped,
    guardrail_citation_missing,
    rag_retrieval_miss,
)
from memory.long_term_memory import save_message
from memory.session_memory import (
    append_to_chat_window,
    get_chat_window,
    get_signals,
    get_user_session,
    increment_signal,
)
from models.model_router import get_model_config
from models.ollama_client import chat
from engines.summarizer import summarize_session
import asyncio


_COMPARISON_KW = ("เปรียบ", "compare", " vs ", "ต่าง", "ดีกว่า", "เทียบ", "versus")
_PREPARATION_KW = ("เตรียม", "prepare", "portfolio", "สัมภาษณ์", "ทำอย่างไร", "ขั้นตอน")

# Tags that must never appear in the final response shown to the user
_INTERNAL_TAGS = ("sql_result", "career_suggestions", "context")


def _strip_internal_tags(text: str) -> str:
    """Remove any internal XML tags that leaked into the LLM response."""
    import re
    for tag in _INTERNAL_TAGS:
        text = re.sub(rf"</?{tag}[^>]*>", "", text)
    return text.strip()


async def _update_signals(user_id: str, session_id: str, content: str) -> dict:
    """Increment per-session behavioral counters and return updated signals dict."""
    lower = content.lower()
    await increment_signal(user_id, session_id, "total_count")
    if any(kw in lower for kw in _COMPARISON_KW):
        await increment_signal(user_id, session_id, "comparison_count")
    if any(kw in lower for kw in _PREPARATION_KW):
        await increment_signal(user_id, session_id, "prep_count")
    if len(content.strip()) < 40:
        await increment_signal(user_id, session_id, "short_count")
    return await get_signals(user_id, session_id)


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
    signals = await _update_signals(str(user_id), str(session_id), content)
    career_suggestions = (
        await get_career_suggestions(str(user_id), history) if len(history) >= 2 else []
    )
    user_role = profile.get("role", "student")
    system_prompt = compose_dreamer_prompt(profile, career_suggestions, signals=signals, user_role=user_role)
    cfg = get_model_config("dreamer_chat")
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": content}]
    response = await chat(cfg["model"], messages, cfg["temperature"], cfg["top_p"], cfg["max_tokens"], mode="dreamer_chat")
    response = _strip_internal_tags(response)
    _safe, response, _ = await check_safety(content, response)
    return response


async def _enforce_citations(
    response: str,
    rag_context: list[str] | None,
    session_id,
) -> tuple[str, bool]:
    """Ensure every response that used RAG context has at least one citation.

    If the LLM already cited inline ([ที่มา: ...]), return as-is with ok=True.
    If RAG was used but no citation found, append a structured source footer
    and flag the response in the admin review queue (uncited RAG response).
    Returns (final_response, citation_was_present).
    """
    import re as _re

    if not rag_context:
        return response, True

    if "[ที่มา:" in response:
        return response, True

    # Extract all unique sources from the RAG chunks
    sources: list[str] = []
    for chunk in rag_context:
        m = _re.search(r"\[ที่มา: ([^\]]+)\]", chunk)
        if m and m.group(1) not in sources:
            sources.append(m.group(1))

    if sources:
        response += "\n\n---\n*ที่มาข้อมูล: " + " | ".join(sources) + "*"

    # Flag to admin review queue so uncited RAG responses can be reviewed
    try:
        await _db_execute(
            """INSERT INTO flagged_outputs (reason)
               VALUES ($1)""",
            f"Uncited RAG response — session {session_id}",
        )
    except Exception:
        pass  # never block the response over a logging write failure

    return response, False


async def handle_tcas_message(
    user_id: UUID,
    session_id: UUID,
    content: str,
    history: list[dict],
) -> str:
    """Generate a Flow B (TCAS advisor) response grounded in SQL eligibility data + RAG."""
    profile = await _load_user_profile(user_id)
    signals = await _update_signals(str(user_id), str(session_id), content)
    eligibility = await check_eligibility(user_id=user_id)
    rag_context = await retrieve_context(content)
    if not rag_context:
        rag_retrieval_miss(content[:60])
    user_role = profile.get("role", "student")
    system_prompt = compose_tcas_prompt(
        profile, eligibility, rag_context,
        message=content, signals=signals, user_role=user_role,
    )
    cfg = get_model_config("tcas_chat")
    messages = [{"role": "system", "content": system_prompt}] + history + [{"role": "user", "content": content}]
    response = await chat(cfg["model"], messages, cfg["temperature"], cfg["top_p"], cfg["max_tokens"], mode="tcas_chat")

    _valid, response, flags = validate_numeric_claims(response, eligibility, rag_context)
    if flags:
        import logging
        logging.getLogger(__name__).warning("Numeric claims stripped: %s", flags)
        guardrail_numeric_stripped(len(flags), session_id=str(session_id))

    response = _strip_internal_tags(response)
    response, citation_ok = await _enforce_citations(response, rag_context, session_id)
    if not citation_ok:
        import logging as _log
        _log.getLogger(__name__).warning(
            "RAG response missing inline citations — session %s; footer appended", session_id
        )
        guardrail_citation_missing(session_id=str(session_id))

    _safe, response, _ = await check_safety(content, response)
    return response


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

    # Trigger periodic background summarization (every 5 turns)
    signals = await get_signals(str(user_id), str(session_id))
    if signals.get("total_count", 0) > 0 and signals["total_count"] % 5 == 0:
        asyncio.create_task(summarize_session(user_id, session_id))

    return response
