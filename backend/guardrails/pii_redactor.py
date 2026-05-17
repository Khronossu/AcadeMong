"""PII redaction utility — shared across middleware and application-level logging.

Patterns covered:
  - Thai national ID  : 13-digit number
  - Thai mobile phone : 0[689]xxxxxxxx
  - Email address     : standard RFC-ish pattern
  - Thai landline     : 0x-xxxx-xxxx / 02xxxxxxx

Apply _redact() to any string before it touches a log sink.
"""

from __future__ import annotations

import re

_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(\d{1}[-\s]?\d{4}[-\s]?\d{5}[-\s]?\d{2}[-\s]?\d{1})\b"), "[THAI_ID]"),
    (re.compile(r"\b\d{13}\b"), "[THAI_ID]"),
    (re.compile(r"\b0[689]\d{8}\b"), "[PHONE]"),
    (re.compile(r"\b0[2-9]\d{7}\b"), "[PHONE]"),
    (re.compile(r"\+66\s?\d[\d\s\-]{8,10}"), "[PHONE]"),
    (re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"), "[EMAIL]"),
]


def redact(text: str) -> str:
    """Return text with PII patterns replaced by placeholder tokens."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_truncate(text: str, max_len: int = 120) -> str:
    """Redact PII then truncate to max_len characters — for log lines."""
    return redact(text)[:max_len]
