"""Semantic career matcher for Flow A (Career Dreamer).

Pipeline per dreamer turn:
  1. extract_profile(history) — Typhoon2 extracts {interests, strengths, career_goals} as JSON
  2. match_careers(profile_text)  — embed → search Qdrant careers collection
  3. save_recommendations(...)    — upsert top-K into user_recommended_careers
  4. get_career_suggestions(...)  — orchestrates 1-3, returns match list

Returns [] on any failure (graceful degradation — dreamer chat still works
from conversation history alone).
"""

from __future__ import annotations

import json
import re

from db.qdrant_client import CAREERS_COLLECTION, get_async_qdrant_client
from models.ollama_client import chat, embed

_EMBEDDING_MODEL = "nomic-embed-text"
_LLM_MODEL = "scb10x/llama3.1-typhoon2-8b-instruct"
_PROFILE_TOP_K = 5

_EXTRACT_SYSTEM = (
    "คุณเป็นผู้ช่วยสกัดข้อมูลโปรไฟล์อาชีพ ให้ตอบเฉพาะ JSON เท่านั้น ห้ามมีข้อความอื่น\n"
    "รูปแบบ: {\"interests\": [\"...\"], \"strengths\": [\"...\"], \"career_goals\": \"...\"}"
)


async def extract_profile(history: list[dict]) -> dict:
    """Call Typhoon2 to extract a structured career profile from conversation history.

    Returns dict with keys: interests, strengths, career_goals.
    Returns {} on parse failure.
    """
    conversation = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}" for msg in history[-10:]
    )
    user_prompt = (
        f"จากบทสนทนาต่อไปนี้ สกัดโปรไฟล์ความสนใจและจุดแข็งของนักเรียน:\n\n{conversation}"
    )

    try:
        raw = await chat(
            model=_LLM_MODEL,
            messages=[
                {"role": "system", "content": _EXTRACT_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            top_p=0.85,
            max_tokens=300,
        )
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {}
        return json.loads(match.group())
    except Exception:
        return {}


async def match_careers(profile_text: str, top_k: int = _PROFILE_TOP_K) -> list[dict]:
    """Embed profile_text and search the Qdrant careers collection.

    Returns list of {career_id, title, score, avg_salary_thb}.
    Returns [] on Qdrant error.
    """
    try:
        client = get_async_qdrant_client()
        vector = await embed(_EMBEDDING_MODEL, profile_text)
        hits = await client.search(
            collection_name=CAREERS_COLLECTION,
            query_vector=vector,
            limit=top_k,
            with_payload=True,
        )
        return [
            {
                "career_id": hit.payload.get("career_id", ""),
                "title": hit.payload.get("title", ""),
                "score": round(hit.score, 4),
                "avg_salary_thb": hit.payload.get("avg_salary_thb"),
            }
            for hit in hits
        ]
    except Exception:
        return []


async def save_recommendations(
    user_id: str,
    matches: list[dict],
    reasoning: str,
) -> None:
    """Upsert top-K career matches into user_recommended_careers."""
    from db.postgres import execute

    for match in matches:
        career_id = match.get("career_id")
        if not career_id:
            continue
        try:
            await execute(
                """
                INSERT INTO user_recommended_careers
                  (user_id, career_id, match_score, ai_reasoning)
                VALUES ($1::uuid, $2::uuid, $3, $4)
                ON CONFLICT (user_id, career_id) DO UPDATE SET
                  match_score  = EXCLUDED.match_score,
                  ai_reasoning = EXCLUDED.ai_reasoning
                """,
                user_id,
                career_id,
                match["score"],
                reasoning,
            )
        except Exception:
            pass


async def get_career_suggestions(
    user_id: str,
    history: list[dict],
) -> list[dict]:
    """Orchestrate extract → match → save → return matches.

    Returns [] if profile extraction yields nothing or Qdrant is unreachable.
    """
    profile = await extract_profile(history)
    if not profile:
        return []

    parts = []
    if profile.get("interests"):
        parts.append("ความสนใจ: " + ", ".join(profile["interests"]))
    if profile.get("strengths"):
        parts.append("จุดแข็ง: " + ", ".join(profile["strengths"]))
    if profile.get("career_goals"):
        parts.append("เป้าหมาย: " + profile["career_goals"])

    profile_text = " ".join(parts) if parts else ""
    if not profile_text:
        return []

    matches = await match_careers(profile_text)
    if not matches:
        return []

    reasoning = profile_text
    await save_recommendations(user_id, matches, reasoning)
    return matches
