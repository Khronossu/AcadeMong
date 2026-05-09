"""Prompt composer — build layered system prompts for each AI mode.

Prompt structure (CLAUDE.md §6.7):
  _MASTER_SYSTEM       ← static, frozen refusal rules
  + user profile       ← GPAX, school (from PostgreSQL / Redis)
  + mode template      ← Flow A (career) or Flow B (TCAS eligibility)
  + retrieved context  ← eligibility SQL results for Flow B; RAG chunks later (Phase 6)
"""

from __future__ import annotations

_MASTER_SYSTEM = """\
You are AcadeMong, an AI advisor for Thai university students navigating the TCAS \
university admissions system.

Rules you must follow at all times:
- Never state a GPAX minimum or exam score threshold unless it appears verbatim \
in the data provided to you in this prompt.
- If asked something outside TCAS admissions, university selection, or career \
planning, politely decline and redirect the student.
- Content inside <sql_result> tags comes directly from the database and is \
ground truth — treat it as authoritative.
- Respond in the same language the student uses (Thai or English). \
Default to Thai if unclear.\
"""


def compose_dreamer_prompt(user_profile: dict) -> str:
    """System prompt for Flow A — Career Dreamer.

    Builds: MASTER + student profile snippet + career-coaching instruction.
    No eligibility data here; this mode is about exploring interests and strengths.
    """
    lines = [_MASTER_SYSTEM, "\n## Student Profile"]
    gpax = user_profile.get("gpax")
    school = user_profile.get("current_school")
    if gpax is not None:
        lines.append(f"- GPAX: {gpax}")
    if school:
        lines.append(f"- Current school: {school}")
    if not gpax and not school:
        lines.append("- (No profile data on file yet)")

    lines.append(
        "\n## Your role\n"
        "Help this student explore their interests, strengths, and career aspirations. "
        "Ask thoughtful, open-ended questions. Suggest fields of study that match their "
        "interests once you have enough context. Be encouraging and realistic."
    )
    return "\n".join(lines)
