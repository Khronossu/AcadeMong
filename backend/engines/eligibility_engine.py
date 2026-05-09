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


def _evaluate(proj: dict, student_gpax: Optional[float], student_scores: dict[str, float]) -> dict:
    gpax_min = float(proj["gpax_min"]) if proj["gpax_min"] is not None else None
    gpax_ok = True
    if gpax_min is not None:
        gpax_ok = student_gpax is not None and student_gpax >= gpax_min

    subject_results = []
    subjects_pass = True
    for req in proj["requirements"]:
        subj = req["subject"]
        min_score = float(req["min_score"]) if req["min_score"] is not None else None
        student_score = student_scores.get(subj)
        if min_score is not None:
            ok = student_score is not None and student_score >= min_score
            if not ok:
                subjects_pass = False
        else:
            ok = True  # no minimum — the subject is weighted but has no floor
        subject_results.append({
            "subject": subj,
            "min_score": min_score,
            "student_score": student_score,
            "weight_percent": float(req["weight_percent"]) if req["weight_percent"] is not None else None,
            "ok": ok,
        })

    return {
        "admission_project_id": str(proj["ap_id"]),
        "project_name": proj["project_name"],
        "major": proj["major_name"],
        "faculty": proj["faculty_name"],
        "university": proj["university_name"],
        "round_number": proj["round_number"],
        "year": proj["year"],
        "seats": proj["seats"],
        "gpax_min": gpax_min,
        "gpax_ok": gpax_ok,
        "subject_results": subject_results,
        "eligible": gpax_ok and subjects_pass,
        "source_url": proj["source_url"],
    }


async def check_eligibility(
    user_id: UUID,
    year: Optional[int] = None,
) -> list[dict]:
    """Return eligibility results for every Round 3 project for a given user.

    Reads the user's GPAX from user_profiles and their test scores from
    user_test_scores. If year is omitted, uses the most recent year in the DB.

    Args:
        user_id: The user's internal UUID.
        year: TCAS cycle year to evaluate (e.g. 2026). Defaults to latest.

    Returns:
        List of result dicts, one per admission_project, sorted by
        (eligible DESC, university, faculty, major).
    """
    profile = await fetchrow(
        "SELECT gpax FROM user_profiles WHERE user_id = $1", user_id
    )
    student_gpax = float(profile["gpax"]) if profile and profile["gpax"] is not None else None

    score_rows = await fetch(
        """SELECT subject, score, exam_year
           FROM user_test_scores
           WHERE user_id = $1
           ORDER BY exam_year DESC""",
        user_id,
    )
    # Keep the most recent score per subject
    student_scores: dict[str, float] = {}
    for row in score_rows:
        subj = row["subject"]
        if subj not in student_scores:
            student_scores[subj] = float(row["score"])

    target_year = year or await _latest_year()
    if target_year is None:
        return []

    projects = await _fetch_projects_with_requirements(target_year)
    results = []
    for proj in projects:
        result = _evaluate(proj, student_gpax, student_scores)
        results.append(result)

    results.sort(key=lambda r: (not r["eligible"], r["university"], r["faculty"], r["major"]))
    return results
