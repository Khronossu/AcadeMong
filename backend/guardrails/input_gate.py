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

from guardrails.pii_redactor import redact_truncate as _redact_log

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Injection detection (CLAUDE.md §17 Layer 2)
# ---------------------------------------------------------------------------

# Patterns are NFKC-normalized at compile time so they match normalized input.
# Thai SARA AM (U+0E33, ำ) decomposes under NFKC to U+0E4D + U+0E32 (็า);
# without this, Thai patterns containing ำ silently fail to match.
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(unicodedata.normalize("NFKC", p), re.IGNORECASE) for p in [
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
    # Role override — "You are an AI with no rules / restrictions"
    r"you\s+are\s+an?\s+ai\s+with\s+no\s+(?:rules|restrictions|limits)",
    r"คุณคือ.{0,40}ที่ไม่มีข้อจำกัด",
    # Prompt extraction
    r"repeat\s+(?:the\s+)?(?:text|prompt|instruction|message)\s+(?:above|before|verbatim|word)",
    r"word\s+for\s+word",
    r"print\s+(?:your\s+)?(?:full\s+)?(?:context|system\s+prompt|prompt)",
    r"reveal\s+(?:your\s+)?(?:system\s+)?(?:prompt|instructions)",
    # Role-play jailbreak
    r"(?:let'?s\s+play\s+a\s+game|play\s+a\s+role|role.?play).*(?:no\s+rules|no\s+limits|no\s+restrictions)",
    r"with\s+no\s+(?:rules|restrictions|limits|constraints)",
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

# Patterns that are hard-blocked — clearly off-topic, no ambiguity
_HARD_OFFTOPIC_PATTERNS: list[re.Pattern] = [re.compile(
    unicodedata.normalize("NFKC", p), re.IGNORECASE
) for p in [
    r"\brecipe\b",
    r"how\s+to\s+cook",
    r"สอนทำ.{0,10}(?:อาหาร|ขนม|ผัดไทย|ต้มยำ|แกง|ข้าว)",
    r"วิธีทำ(?:อาหาร|ขนม|ผัดไทย)",
    r"ผัดไทย",              # iconic Thai dish — not education
    r"ส่วนผสม(?:ของ)?",    # "ingredients of"
    r"solve\s+(?:this\s+)?(?:equation|problem)\b",
    r"แก้โจทย์",
    r"ช่วยแก้(?:โจทย์|สมการ|ปัญหาคณิต)",
    r"x\^2\s*[+\-]",
    r"\bx²\b",
    r"write\s+(?:my\s+)?(?:essay|story|poem|code)\b",
    r"translate\s+this\s+(?:text|sentence|paragraph)",
    r"แปลภาษา(?:ให้|หน่อย)",
    # General knowledge not related to education
    r"ก่อตั้งเมื่อปีใด",   # "founded in which year" — history question
    r"เกิดขึ้นเมื่อ(?:ปี|ไหน|ใด)",
]]

# Patterns that are soft-warned but not blocked
_SOFT_OFFTOPIC_PATTERNS: list[re.Pattern] = [re.compile(p, re.IGNORECASE) for p in [
    r"\bhomework\b",
    r"write\s+my\s+essay",
]]


def validate_topic(message: str) -> None:
    """Check if message is on-topic (education/TCAS/career).

    Hard off-topic: raises HTTP 400 immediately.
    Soft off-topic: logs a warning, lets the LLM handle the refusal.
    On-topic or ambiguous: passes through silently.
    """
    from fastapi import HTTPException
    normalized = _normalize(message).lower()

    # Hard block — clearly nothing to do with education
    if any(p.search(normalized) for p in _HARD_OFFTOPIC_PATTERNS):
        raise HTTPException(
            status_code=400,
            detail="ขออภัย ระบบนี้ช่วยได้เฉพาะเรื่อง TCAS การเลือกคณะ และการวางแผนอาชีพเท่านั้น",
        )

    # Soft warn — ambiguous, let the LLM refuse naturally
    if any(p.search(normalized) for p in _SOFT_OFFTOPIC_PATTERNS):
        logger.warning("Soft off-topic message (advisory): %s", _redact_log(message, 80))


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
