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


async def _latest_year() -> Optional[int]:
    row = await fetchrow("SELECT MAX(year) AS y FROM tcas_rounds")
    return row["y"] if row else None


async def _fetch_projects_with_requirements(
    year: int,
    major_id: Optional[UUID] = None,
) -> list[dict]:
    """Fetch all Round 3 admission projects for a given year, with their
    subject_requirements joined in. Returns a list of dicts, one per project,
    with a nested 'requirements' list."""

    major_filter = "AND m.id = $2" if major_id else ""
    params = [year, major_id] if major_id else [year]

    projects = await fetch(
        f"""SELECT
                ap.id             AS ap_id,
                ap.project_name,
                ap.seats,
                ap.gpax_min,
                ap.source_url,
                ap.accepts_ged,
                tr.round_number,
                tr.year,
                m.id              AS major_id,
                m.name            AS major_name,
                f.name            AS faculty_name,
                u.name            AS university_name
            FROM admission_projects ap
            JOIN tcas_rounds tr       ON tr.id = ap.tcas_round_id
            JOIN majors m             ON m.id  = tr.major_id
            JOIN faculties f          ON f.id  = m.faculty_id
            JOIN universities u       ON u.id  = f.university_id
            WHERE tr.year = $1
              AND tr.round_number = 3
              {major_filter}
            ORDER BY u.name, f.name, m.name""",
        *params,
    )

    if not projects:
        return []

    ap_ids = [r["ap_id"] for r in projects]
    reqs = await fetch(
        """SELECT admission_project_id, subject, min_score, weight_percent
           FROM subject_requirements
           WHERE admission_project_id = ANY($1::uuid[])""",
        ap_ids,
    )
    req_map: dict = {}
    for req in reqs:
        req_map.setdefault(req["admission_project_id"], []).append(req)

    result = []
    for p in projects:
        result.append({
            **dict(p),
            "requirements": req_map.get(p["ap_id"], []),
        })
    return result
