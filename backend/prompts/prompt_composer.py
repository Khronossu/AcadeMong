"""Prompt composer — build layered system prompts for each AI mode."""

from __future__ import annotations

from prompts.master_prompt import _MASTER_SYSTEM
from prompts.intent_templates import TEMPLATES

_ROLE_LABELS: dict[str, str] = {
    "student": "นักเรียน",
    "admin": "ผู้ดูแลระบบ",
}

# ---------------------------------------------------------------------------
# Sub-intent detection (Flow B only)
# ---------------------------------------------------------------------------

_COMPARISON_KW = frozenset(["เปรียบ", "compare", " vs ", "ต่าง", "ดีกว่า", "เทียบ", "versus"])
_PREPARATION_KW = frozenset(["เตรียม", "prepare", "portfolio", "สัมภาษณ์", "ทำอย่างไร", "ขั้นตอน", "สอบ"])
_RECOMMENDATION_KW = frozenset(["แนะนำ", "ควรเรียน", "คณะไหนดี", "เหมาะกับ", "recommend"])

def _detect_sub_intent(message: str) -> str:
    """Return 'comparison', 'preparation', 'recommendation', or 'eligibility' based on keyword scan."""
    lower = message.lower()
    if any(kw in lower for kw in _COMPARISON_KW):
        return "comparison"
    if any(kw in lower for kw in _PREPARATION_KW):
        return "preparation"
    if any(kw in lower for kw in _RECOMMENDATION_KW):
        return "recommendation"
    # Default to eligibility for Flow B (TCAS queries)
    return "eligibility"


# ---------------------------------------------------------------------------
# Behavior-based tone adapter
# ---------------------------------------------------------------------------

_COMPARISON_COUNT_THRESHOLD = 2
_PREP_COUNT_THRESHOLD = 2
_SHORT_RATIO_THRESHOLD = 0.6
_LOW_GPAX_THRESHOLD = 2.5


def _build_tone_adapter(signals: dict, profile: dict, mode: str) -> str:
    """Return a Thai-language tone instruction based on behavioral signals and profile."""
    gpax = profile.get("gpax")
    total = signals.get("total_count", 0)

    if mode == "tcas" and gpax is not None and float(gpax) < _LOW_GPAX_THRESHOLD:
        return (
            "## คำแนะนำด้านน้ำเสียง\n"
            "GPAX ของนักเรียนค่อนข้างต่ำสำหรับบางคณะที่มีการแข่งขันสูง "
            "ให้แนะนำทางเลือกที่สมจริงและเหมาะสมกับคุณสมบัติปัจจุบัน "
            "โดยไม่ปิดกั้นความฝัน แต่ให้ข้อมูลอย่างตรงไปตรงมา"
        )

    if signals.get("comparison_count", 0) >= _COMPARISON_COUNT_THRESHOLD:
        return (
            "## คำแนะนำด้านน้ำเสียง\n"
            "นักเรียนถามเปรียบเทียบหลายครั้ง ให้ตอบในรูปแบบตาราง markdown ที่ชัดเจน "
            "เพื่อให้เปรียบเทียบได้ง่าย"
        )

    if signals.get("prep_count", 0) >= _PREP_COUNT_THRESHOLD:
        return (
            "## คำแนะนำด้านน้ำเสียง\n"
            "นักเรียนถามเรื่องการเตรียมตัวหลายครั้ง ให้ตอบแบบ step-by-step "
            "ใช้น้ำเสียงโค้ชชิ่งที่ให้กำลังใจและเป็นรูปธรรม"
        )

    if total > 0 and signals.get("short_count", 0) / total > _SHORT_RATIO_THRESHOLD:
        return (
            "## คำแนะนำด้านน้ำเสียง\n"
            "นักเรียนมักถามสั้นๆ ให้ตอบสั้น กระชับ ตรงประเด็น ไม่ต้องอธิบายยาว"
        )

    return ""


# ---------------------------------------------------------------------------
# Public compose functions
# ---------------------------------------------------------------------------

def compose_dreamer_prompt(
    user_profile: dict,
    career_suggestions: list[dict] | None = None,
    signals: dict | None = None,
    user_role: str = "student",
) -> str:
    """System prompt for Flow A — Career Dreamer."""
    lines = [_MASTER_SYSTEM]

    role_label = _ROLE_LABELS.get(user_role, "นักเรียน")
    lines.append(f"\n[ผู้ใช้: {role_label}]")

    lines.append("\n## Student Profile")
    gpax = user_profile.get("gpax")
    school = user_profile.get("current_school")
    if gpax is not None:
        lines.append(f"- GPAX: {gpax}")
    if school:
        lines.append(f"- Current school: {school}")
    if not gpax and not school:
        lines.append("- (No profile data on file yet)")

    if career_suggestions:
        lines.append("\n<career_suggestions>")
        lines.append("อาชีพที่เหมาะสมกับโปรไฟล์ของนักเรียน (จัดอันดับตามความเข้ากัน):")
        for i, c in enumerate(career_suggestions, 1):
            salary = f" | เงินเดือนเฉลี่ย {c['avg_salary_thb']:,} บาท" if c.get("avg_salary_thb") else ""
            lines.append(f"  {i}. {c['title']} (คะแนน {c['score']:.2f}){salary}")
        lines.append("</career_suggestions>")

    # In Flow A, we primarily use the 'career' intent template
    lines.append("\n" + TEMPLATES["career"])

    if signals:
        adapter = _build_tone_adapter(signals, user_profile, "dreamer")
        if adapter:
            lines.append(f"\n{adapter}")

    return "\n".join(lines)


def compose_tcas_prompt(
    user_profile: dict,
    eligibility_results: list[dict],
    rag_context: list[str] | None = None,
    message: str = "",
    signals: dict | None = None,
    user_role: str = "student",
) -> str:
    """System prompt for Flow B — TCAS advisor."""
    lines = [_MASTER_SYSTEM]

    role_label = _ROLE_LABELS.get(user_role, "นักเรียน")
    lines.append(f"\n[ผู้ใช้: {role_label}]")

    lines.append("\n## Student Profile")
    gpax = user_profile.get("gpax")
    if gpax is not None:
        lines.append(f"- GPAX: {gpax}")
    else:
        lines.append("- GPAX: not on file")

    eligible = [r for r in eligibility_results if r["eligible"]]
    ineligible = [r for r in eligibility_results if not r["eligible"]]

    lines.append("\n<sql_result>")
    lines.append(f"Total projects evaluated: {len(eligibility_results)}")
    lines.append(f"Eligible: {len(eligible)}  |  Ineligible: {len(ineligible)}")

    if eligible:
        lines.append("\nELIGIBLE PROJECTS (student meets all requirements):")
        for r in eligible[:10]:
            gpax_label = f"GPAX≥{r['gpax_min']}" if r["gpax_min"] else "no GPAX min"
            lines.append(
                f"  ✓ {r['project_name']} — {r['university']} / {r['faculty']} / {r['major']} ({gpax_label})"
            )
        if len(eligible) > 10:
            lines.append(f"  ... and {len(eligible) - 10} more eligible projects")

    if ineligible:
        lines.append("\nINELIGIBLE PROJECTS (requirements not met):")
        for r in ineligible[:5]:
            lines.append(
                f"  ✗ {r['project_name']} — {r['university']} / {r['faculty']} / {r['major']}"
            )
        if len(ineligible) > 5:
            lines.append(f"  ... and {len(ineligible) - 5} more ineligible projects")

    lines.append("</sql_result>")

    if rag_context:
        lines.append('\n<context source="rag">')
        for chunk in rag_context:
            lines.append(chunk)
        lines.append("</context>")

    # Sub-intent template injection
    # For Flow B, we use the message to detect sub_intent
    sub_intent = _detect_sub_intent(message) if message else "general"
    lines.append("\n" + TEMPLATES[sub_intent])

    if signals:
        adapter = _build_tone_adapter(signals, user_profile, "tcas")
        if adapter:
            lines.append(f"\n{adapter}")

    return "\n".join(lines)
