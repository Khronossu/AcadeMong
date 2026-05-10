"""Numeric claim validator — Layer 5 output guardrail (CLAUDE.md §17).

Parses LLM output for numeric claims (GPAX, scores, seat counts) and verifies
each against the authoritative SQL result block and retrieved RAG context.
Any GPAX-range number (0.00–9.99) not present in either source is stripped and
flagged. Non-GPAX numbers (rankings, counts) are left untouched.

Usage:
    valid, cleaned, flags = validate_numeric_claims(llm_output, sql_results, rag_chunks)
    if flags:
        logger.warning("Numeric claims stripped: %s", flags)
    return cleaned   # always return cleaned — never raise to the user
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# GPAX values are the only numbers we hard-strip: they must come from SQL.
_GPAX_PATTERN = re.compile(r"\b([0-9]\.[0-9]{2})\b")

# Extract any number from text (used to build the allowed-numbers set from context).
_ANY_NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\b")

_REPLACEMENT = "[ข้อมูลไม่พบในฐานข้อมูล]"


def _allowed_numbers(sql_results: list[dict], rag_context: list[str]) -> set[str]:
    """Build the set of numeric values present in authoritative sources."""
    allowed: set[str] = set()

    for row in sql_results:
        for val in row.values():
            if val is None:
                continue
            if isinstance(val, (int, float)):
                # Normalize to string with 2 decimal places for GPAX-range floats
                allowed.add(f"{float(val):.2f}")
                allowed.add(str(int(val)) if float(val) == int(val) else str(val))
            else:
                for m in _ANY_NUMBER_PATTERN.findall(str(val)):
                    allowed.add(m)

    for chunk in rag_context:
        for m in _ANY_NUMBER_PATTERN.findall(chunk):
            allowed.add(m)

    return allowed


def validate_numeric_claims(
    llm_output: str,
    sql_results: list[dict],
    rag_context: list[str],
) -> tuple[bool, str, list[str]]:
    """Verify every GPAX-range number in llm_output against authoritative sources.

    Args:
        llm_output:  Raw text from Typhoon2.
        sql_results: List of eligibility result dicts from check_eligibility().
        rag_context: List of retrieved chunk strings from retrieve_context().

    Returns:
        (valid, cleaned_output, flags)
        - valid:          True if no unsupported claims were found.
        - cleaned_output: llm_output with unsupported GPAX numbers replaced.
        - flags:          List of "stripped: <number>" strings for logging.
    """
    allowed = _allowed_numbers(sql_results, rag_context)
    flags: list[str] = []
    seen: set[str] = set()

    def _check_and_replace(match: re.Match) -> str:
        num = match.group(1)
        # Normalize: "3.5" stored as "3.50" in SQL NUMERIC(3,2)
        normalized = f"{float(num):.2f}"
        if normalized in allowed or num in allowed:
            return match.group(0)
        if normalized not in seen:
            seen.add(normalized)
            flags.append(f"stripped: {num}")
            logger.warning("Numeric claim not in SQL/context — stripped: %s", num)
        return _REPLACEMENT

    cleaned = _GPAX_PATTERN.sub(_check_and_replace, llm_output)
    return len(flags) == 0, cleaned, flags
