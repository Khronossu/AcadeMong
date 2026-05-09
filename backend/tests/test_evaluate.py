"""Unit tests for engines.eligibility_engine._evaluate.

_evaluate() is a pure function — no I/O, no DB.  Every case here uses
constructed project/requirement dicts so tests run without a database.

Project dict shape mirrors what _fetch_projects_with_requirements returns:
  ap_id, project_name, seats, gpax_min, source_url, accepts_ged,
  round_number, year, major_id, major_name, faculty_name, university_name,
  requirements: [{subject, min_score, weight_percent}, ...]
"""

from __future__ import annotations

import uuid

import pytest

from engines.eligibility_engine import _evaluate


def _proj(gpax_min=None, requirements=None, *, name="Test Project"):
    return {
        "ap_id": str(uuid.uuid4()),
        "project_name": name,
        "seats": 30,
        "gpax_min": gpax_min,
        "source_url": None,
        "accepts_ged": False,
        "round_number": 3,
        "year": 2026,
        "major_id": str(uuid.uuid4()),
        "major_name": "Test Major",
        "faculty_name": "Test Faculty",
        "university_name": "Test University",
        "requirements": requirements or [],
    }


def _req(subject, min_score=None, weight=100.0):
    return {"subject": subject, "min_score": min_score, "weight_percent": weight}


# ── GPAX checks ───────────────────────────────────────────────────────────────

def test_no_gpax_min_always_passes_gpax():
    result = _evaluate(_proj(gpax_min=None), student_gpax=None, student_scores={})
    assert result["gpax_ok"] is True


def test_gpax_above_min_passes():
    result = _evaluate(_proj(gpax_min=3.0), student_gpax=3.5, student_scores={})
    assert result["gpax_ok"] is True


def test_gpax_exactly_at_min_passes():
    result = _evaluate(_proj(gpax_min=3.0), student_gpax=3.0, student_scores={})
    assert result["gpax_ok"] is True


def test_gpax_below_min_fails():
    result = _evaluate(_proj(gpax_min=3.0), student_gpax=2.99, student_scores={})
    assert result["gpax_ok"] is False
    assert result["eligible"] is False


def test_gpax_none_with_min_required_fails():
    result = _evaluate(_proj(gpax_min=3.0), student_gpax=None, student_scores={})
    assert result["gpax_ok"] is False
    assert result["eligible"] is False


# ── Subject score checks ──────────────────────────────────────────────────────

def test_subject_above_min_passes():
    proj = _proj(requirements=[_req("TGAT1", min_score=50.0)])
    result = _evaluate(proj, student_gpax=4.0, student_scores={"TGAT1": 75.0})
    assert result["subject_results"][0]["ok"] is True
    assert result["eligible"] is True


def test_subject_exactly_at_min_passes():
    proj = _proj(requirements=[_req("TGAT1", min_score=50.0)])
    result = _evaluate(proj, student_gpax=4.0, student_scores={"TGAT1": 50.0})
    assert result["subject_results"][0]["ok"] is True
    assert result["eligible"] is True


def test_subject_below_min_fails():
    proj = _proj(requirements=[_req("TGAT1", min_score=50.0)])
    result = _evaluate(proj, student_gpax=4.0, student_scores={"TGAT1": 49.9})
    assert result["subject_results"][0]["ok"] is False
    assert result["eligible"] is False


def test_subject_missing_score_with_min_fails():
    proj = _proj(requirements=[_req("TGAT1", min_score=50.0)])
    result = _evaluate(proj, student_gpax=4.0, student_scores={})
    sr = result["subject_results"][0]
    assert sr["student_score"] is None
    assert sr["ok"] is False
    assert result["eligible"] is False


def test_subject_no_min_always_passes():
    proj = _proj(requirements=[_req("A_LEVEL_MATH1", min_score=None)])
    result = _evaluate(proj, student_gpax=4.0, student_scores={})
    assert result["subject_results"][0]["ok"] is True
    assert result["eligible"] is True


def test_one_failing_subject_makes_ineligible():
    proj = _proj(requirements=[
        _req("TGAT1", min_score=50.0),
        _req("A_LEVEL_MATH1", min_score=40.0),
    ])
    result = _evaluate(proj, student_gpax=4.0, student_scores={"TGAT1": 80.0, "A_LEVEL_MATH1": 30.0})
    assert result["eligible"] is False
    assert result["subject_results"][1]["ok"] is False


# ── Combined eligibility ───────────────────────────────────────────────────────

def test_no_requirements_no_gpax_min_eligible():
    result = _evaluate(_proj(), student_gpax=None, student_scores={})
    assert result["eligible"] is True


def test_gpax_fails_even_if_subjects_pass():
    proj = _proj(gpax_min=3.5, requirements=[_req("TGAT1", min_score=50.0)])
    result = _evaluate(proj, student_gpax=3.0, student_scores={"TGAT1": 90.0})
    assert result["gpax_ok"] is False
    assert result["eligible"] is False


def test_subjects_fail_even_if_gpax_passes():
    proj = _proj(gpax_min=3.0, requirements=[_req("TGAT1", min_score=50.0)])
    result = _evaluate(proj, student_gpax=3.8, student_scores={"TGAT1": 40.0})
    assert result["gpax_ok"] is True
    assert result["eligible"] is False


def test_all_pass_eligible():
    proj = _proj(gpax_min=3.0, requirements=[
        _req("TGAT1", min_score=50.0),
        _req("A_LEVEL_MATH1", min_score=40.0),
    ])
    result = _evaluate(proj, student_gpax=3.5, student_scores={"TGAT1": 55.0, "A_LEVEL_MATH1": 45.0})
    assert result["eligible"] is True
    assert all(s["ok"] for s in result["subject_results"])


# ── Result shape ──────────────────────────────────────────────────────────────

def test_result_contains_expected_fields():
    proj = _proj(gpax_min=3.0, requirements=[_req("TGAT1", min_score=50.0)])
    result = _evaluate(proj, student_gpax=3.5, student_scores={"TGAT1": 60.0})

    expected_keys = {
        "admission_project_id", "project_name", "major", "faculty", "university",
        "round_number", "year", "seats", "gpax_min", "gpax_ok",
        "subject_results", "eligible", "source_url",
    }
    assert expected_keys == result.keys()


def test_subject_result_contains_weight():
    proj = _proj(requirements=[_req("TGAT1", min_score=50.0, weight=30.0)])
    result = _evaluate(proj, student_gpax=None, student_scores={"TGAT1": 60.0})
    assert result["subject_results"][0]["weight_percent"] == 30.0


def test_student_score_reflected_in_result():
    proj = _proj(requirements=[_req("A_LEVEL_BIOLOGY", min_score=50.0)])
    result = _evaluate(proj, student_gpax=None, student_scores={"A_LEVEL_BIOLOGY": 75.0})
    assert result["subject_results"][0]["student_score"] == 75.0
