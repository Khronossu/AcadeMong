"""Llama Guard 3 output safety filter.

Runs the AI's generated response through llama-guard3:1b to check for
unsafe content before it reaches the user. If flagged, returns a safe
refusal message instead.

Llama Guard output format:
    safe
  or
    unsafe
    S1,S6   ← violated category codes

Categories relevant to AcadeMong:
    S6  — Specialized Advice (medical, legal, financial — e.g. self-diagnosis)
    S10 — Hate (discriminatory content)
    S11 — Self-Harm (mental health crisis content)

The filter runs AFTER Typhoon2 generates a response and BEFORE it is
returned to the user. Cold-start ~3s (model loads on demand).
"""

from __future__ import annotations

import logging
import os

import httpx

from middleware.metrics import guardrail_safety_blocked

logger = logging.getLogger(__name__)

SAFETY_MODEL = os.getenv("SAFETY_MODEL", "llama-guard3:1b")
OLLAMA_BASE_URL = f"http://{os.getenv('OLLAMA_HOST', 'ollama')}:{os.getenv('OLLAMA_PORT', 11434)}"

# Categories we care about — others (e.g. S1 Violent Crimes) are very unlikely
# in a university admissions context and produce false positives
_WATCH_CATEGORIES = {"S10", "S11"}  # S6 (Specialized Advice) excluded — too aggressive for education context

_SAFE_REFUSAL = (
    "ขออภัย ฉันไม่สามารถตอบคำถามนี้ได้ "
    "หากคุณกำลังประสบปัญหาและต้องการความช่วยเหลือ "
    "กรุณาติดต่อผู้เชี่ยวชาญหรือสายด่วนสุขภาพจิต 1323 ค่ะ"
)

# Prompt template per Llama Guard 3 spec
_GUARD_TEMPLATE = """<|begin_of_text|><|start_header_id|>user<|end_header_id|>

Task: Check if there is unsafe content in the 'Agent' message according to our safety policy.

<BEGIN UNSAFE CONTENT CATEGORIES>
S1: Violent Crimes.
S2: Non-Violent Crimes.
S3: Sex Crimes.
S4: Child Exploitation.
S5: Defamation.
S6: Specialized Advice. Providing advice that requires professional expertise (medical diagnosis, legal advice, financial investment recommendations).
S7: Privacy.
S8: Intellectual Property.
S9: Indiscriminate Weapons.
S10: Hate. Content that discriminates or demeans based on race, gender, religion, nationality, disability.
S11: Self-Harm. Content that encourages or provides instructions for self-harm or suicide.
S12: Sexual Content.
S13: Elections.
</END UNSAFE CONTENT CATEGORIES>

<BEGIN CONVERSATION>
User: {user_message}
Agent: {agent_response}
</END CONVERSATION>

Provide your safety assessment for ONLY THE LAST Agent message:
- First line must read 'safe' or 'unsafe'.
- If unsafe, second line must include a comma-separated list of violated categories.
<|eot_id|><|start_header_id|>assistant<|end_header_id|>
"""


async def check_safety(user_message: str, agent_response: str) -> tuple[bool, str, list[str]]:
    """Run response through Llama Guard 3.

    Returns:
        (is_safe, final_response, violated_categories)
        - is_safe: True if safe or if the guard fails gracefully
        - final_response: original response if safe, refusal if unsafe
        - violated_categories: list of category codes if unsafe, else []
    """
    prompt = _GUARD_TEMPLATE.format(
        user_message=user_message[:500],    # cap to avoid huge prompts
        agent_response=agent_response[:1000],
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": SAFETY_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0, "num_predict": 20},
                },
            )
            resp.raise_for_status()
            output = resp.json().get("response", "").strip().lower()

    except Exception as e:
        # Guard failure → fail open (don't block the user, log the error)
        logger.warning("Llama Guard unavailable, failing open: %s", e)
        return True, agent_response, []

    if not output.startswith("unsafe"):
        return True, agent_response, []

    # Parse violated categories from second line
    lines = output.splitlines()
    categories: list[str] = []
    if len(lines) >= 2:
        categories = [c.strip().upper() for c in lines[1].split(",") if c.strip()]

    # Only block if a category we actively watch is violated
    watched = [c for c in categories if c in _WATCH_CATEGORIES]
    if not watched:
        # Flagged for something we don't act on (e.g. S8 IP) — log but pass through
        logger.info("Llama Guard flagged %s — not in watch list, passing through", categories)
        return True, agent_response, categories

    logger.warning("Llama Guard blocked response — categories: %s", watched)
    guardrail_safety_blocked(watched)
    return False, _SAFE_REFUSAL, watched
