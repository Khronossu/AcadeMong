"""Input gate — Layer 2 guardrails (CLAUDE.md §17).

Three independent checks, each callable from any router handler:

  validate_topic(message)    Advisory — logs off-topic, never blocks.
  detect_injection(message)  Blocking — returns True on injection pattern.
  check_role(user, role)     Blocking — raises HTTP 403 if role insufficient.

Design principles:
- No LLM call. All checks are deterministic regex/keyword scans so they
  add < 1ms and cannot themselves be prompt-injected.
- Unicode-normalized before matching to resist homoglyph attacks.
- Permissive by default: false negatives are safer than blocking legitimate
  Thai student queries that happen to share off-topic vocabulary.
"""

from __future__ import annotations

import logging
import re
import unicodedata

from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Injection detection (CLAUDE.md §17 Layer 2)
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: list[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    r"ignore\s+previous",
    r"you\s+are\s+now",
    r"system\s*:",
    r"</\s*system\s*>",
    r"\[INST\]",
    r"\[/INST\]",
    r"ลืมคำสั่ง",
    r"คุณคือ(?:\s+ตอนนี้)?(?:\s+AI|\s+บอท|\s+ระบบ)",
    r"ทำแทน(?:\s+คำสั่ง)?",
    r"เปลี่ยน(?:\s+บทบาท|\s+ตัวตน)",
    r"act\s+as\s+(?:a\s+)?(?:different|new|another)",
    r"pretend\s+(?:you\s+are|to\s+be)",
    r"DAN\b",           # "Do Anything Now" jailbreak
    r"jailbreak",
]]


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def detect_injection(message: str) -> bool:
    """Return True if message contains a prompt-injection pattern.

    Call this before dispatching to the orchestrator. If True, return HTTP 400.
    """
    normalized = _normalize(message)
    return any(p.search(normalized) for p in _INJECTION_PATTERNS)


# ---------------------------------------------------------------------------
# Topic validation (CLAUDE.md §17 Layer 2) — advisory, never blocks
# ---------------------------------------------------------------------------

_EDUCATION_KEYWORDS: frozenset[str] = frozenset([
    # Thai
    "มหาวิทยาลัย", "คณะ", "สาขา", "gpax", "เกรด", "tcas", "รอบ",
    "สมัคร", "admission", "ทุน", "scholarship", "ค่าเทอม",
    "วิชา", "วิชาสามัญ", "tgat", "tpat", "a-level",
    "อาชีพ", "career", "งาน", "เงินเดือน", "salary",
    "ความสนใจ", "จุดแข็ง", "เป้าหมาย",
    "เตรียม", "portfolio", "สัมภาษณ์",
    "ชุลาลงกรณ์", "มหิดล", "เกษตรศาสตร์", "ธรรมศาสตร์", "ศรีนครินทรวิโรฒ",
    # English
    "university", "faculty", "major", "gpa", "grade",
    "round", "apply", "application", "tuition",
    "subject", "exam", "score",
    "career", "job", "salary", "interest", "strength", "goal",
    "prepare", "interview",
])

_OFFTOPIC_PATTERNS: list[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    r"\brecipe\b",
    r"\bcook(ing)?\b",
    r"\bhomework\b",
    r"\bmath\s+homework\b",
    r"write\s+(my\s+)?essay",
    r"solve\s+(this\s+)?equation",
    r"translate\s+this",
]]


def validate_topic(message: str) -> bool:
    """Return True if message appears on-topic (education/TCAS/career).

    This is advisory — callers should log a warning but NOT block on False.
    Returns True by default to avoid false positives on ambiguous Thai text.
    """
    normalized = _normalize(message).lower()
    has_education_keyword = any(kw.lower() in normalized for kw in _EDUCATION_KEYWORDS)
    has_offtopic = any(p.search(normalized) for p in _OFFTOPIC_PATTERNS)

    if has_education_keyword:
        return True
    if has_offtopic:
        logger.warning("Off-topic message detected (advisory): %.80s", message)
        return False
    return True  # permissive default


# ---------------------------------------------------------------------------
# Role-based access control (CLAUDE.md §8)
# ---------------------------------------------------------------------------

_ROLE_HIERARCHY: dict[str, int] = {
    "student": 0,
    "admin": 1,
}


def check_role(user: dict, required_role: str) -> None:
    """Raise HTTP 403 if user's role does not meet required_role.

    Hierarchy: admin > student.
    user dict must contain a 'role' key (cached from PostgreSQL on login).
    """
    user_role = user.get("role", "student")
    user_level = _ROLE_HIERARCHY.get(user_role, 0)
    required_level = _ROLE_HIERARCHY.get(required_role, 0)
    if user_level < required_level:
        raise HTTPException(
            status_code=403,
            detail=f"Requires role '{required_role}'; your role is '{user_role}'.",
        )
