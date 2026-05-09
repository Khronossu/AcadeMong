"""Eligibility engine — SQL-only, no LLM involved.

Takes a student's GPAX and test scores, returns the admission_projects they
qualify for by walking the hierarchy:
  tcas_rounds → admission_projects → subject_requirements

Why SQL-only? CLAUDE.md §14: "LLMs hallucinate thresholds. Eligibility is
always SQL, never LLM." Every numeric claim this engine returns comes directly
from a database row, not from a model.

Result shape per matched project:
{
    "admission_project_id": UUID,
    "project_name": str,
    "major": str,
    "faculty": str,
    "university": str,
    "round_number": int,
    "year": int,
    "seats": int | None,
    "gpax_min": float | None,
    "gpax_ok": bool,
    "subject_results": [
        {"subject": str, "min_score": float | None, "student_score": float | None, "ok": bool}
    ],
    "eligible": bool,  # True only if gpax_ok AND all subjects with min_score pass
    "source_url": str | None,
}
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from db.postgres import fetch, fetchrow
