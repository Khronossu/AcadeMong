"""Mode selector — explicit UI-driven routing between Flow A and Flow B.

Why not LLM-based intent detection?
  CLAUDE.md §6.1: "Instead of relying on LLM intent classification (which is
  prone to errors), the system uses explicit mode selection from the frontend UI."
  The frontend sends ai_mode as part of session creation; this module validates
  and normalises that value so the rest of the system can trust it.
"""

from __future__ import annotations

VALID_MODES = {"dreamer", "tcas_rag"}


def validate_mode(ai_mode: str) -> str:
    """Validate and normalise the ai_mode string sent by the frontend.

    Returns the normalised mode string ("dreamer" or "tcas_rag").
    Raises ValueError for any unrecognised value so the API can return 422.
    """
    mode = ai_mode.lower().strip()
    if mode not in VALID_MODES:
        raise ValueError(
            f"Invalid ai_mode '{ai_mode}'. Must be one of: {sorted(VALID_MODES)}"
        )
    return mode
