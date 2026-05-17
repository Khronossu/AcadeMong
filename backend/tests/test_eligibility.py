"""Integration tests for check_eligibility() against a live PostgreSQL instance.

Requires the Docker Compose stack to be running with at least postgres available.
The seed_tcas fixture inserts a minimal 2026 project set with 4 projects:

  CS Admission    — GPAX >= 3.0, TGAT1 >= 50, A_LEVEL_MATH1 >= 40
  Medical         — GPAX >= 3.5, TGAT1 >= 60, TPAT2 >= 60, BIO >= 70, CHEM >= 70
  Biology         — No GPAX min, A_LEVEL_BIOLOGY >= 50, A_LEVEL_CHEMISTRY >= 50
  Pharmacy        — GPAX >= 3.0, A_LEVEL_CHEMISTRY >= 60, A_LEVEL_BIOLOGY >= 50

Each test profile exercises a distinct eligibility scenario.
"""

from __future__ import annotations

import pytest

from engines.eligibility_engine import check_eligibility


def _project_ids(results):
    return {r["project_name"] for r in results}


def _eligible_names(results):
    return {r["project_name"] for r in results if r["eligible"]}


def _ineligible_names(results):
    return {r["project_name"] for r in results if not r["eligible"]}


# ── Profile 1: Excellent student ──────────────────────────────────────────────

async def test_profile_excellent_eligible_for_all(seed_tcas, make_user):
    """GPAX 3.95, top scores in everything → all 4 projects eligible."""
    uid = await make_user(gpax=3.95, scores={
        "TGAT1": 95.0, "TPAT2": 95.0,
        "A_LEVEL_MATH1": 90.0,
        "A_LEVEL_BIOLOGY": 90.0,
        "A_LEVEL_CHEMISTRY": 90.0,
    })
    results = await check_eligibility(uid, year=2026)
    assert len(results) == 4
    assert _eligible_names(results) == {
        "CS Admission", "Medical Admission", "Biology Admission", "Pharmacy Admission"
    }


# ── Profile 2: Good engineering student ───────────────────────────────────────

async def test_profile_engineering_eligible_cs_only(seed_tcas, make_user):
    """GPAX 3.5, strong math/TGAT but no bio/chem → CS only."""
    uid = await make_user(gpax=3.5, scores={
        "TGAT1": 80.0,
        "A_LEVEL_MATH1": 75.0,
    })
    results = await check_eligibility(uid, year=2026)
    assert "CS Admission" in _eligible_names(results)
    assert "Medical Admission" not in _eligible_names(results)
    assert "Biology Admission" not in _eligible_names(results)


# ── Profile 3: Average GPAX ───────────────────────────────────────────────────

async def test_profile_average_gpax_3_0_passes_cs_threshold(seed_tcas, make_user):
    """GPAX exactly 3.0 clears CS and Pharmacy thresholds; too low for Medicine."""
    uid = await make_user(gpax=3.0, scores={
        "TGAT1": 55.0, "A_LEVEL_MATH1": 45.0,
        "A_LEVEL_BIOLOGY": 55.0, "A_LEVEL_CHEMISTRY": 65.0,
    })
    results = await check_eligibility(uid, year=2026)
    assert "CS Admission" in _eligible_names(results)
    assert "Pharmacy Admission" in _eligible_names(results)
    assert "Medical Admission" not in _eligible_names(results)


# ── Profile 4: Low GPAX with high scores ─────────────────────────────────────

async def test_profile_low_gpax_fails_projects_with_gpax_min(seed_tcas, make_user):
    """GPAX 2.5 — fails CS (3.0) and Medicine (3.5) and Pharmacy (3.0) thresholds.
    Biology has no GPAX min, so passes if scores are there."""
    uid = await make_user(gpax=2.5, scores={
        "TGAT1": 90.0, "TPAT2": 90.0,
        "A_LEVEL_MATH1": 90.0,
        "A_LEVEL_BIOLOGY": 90.0,
        "A_LEVEL_CHEMISTRY": 90.0,
    })
    results = await check_eligibility(uid, year=2026)
    eligible = _eligible_names(results)
    assert "Biology Admission" in eligible
    assert "CS Admission" not in eligible
    assert "Medical Admission" not in eligible
    assert "Pharmacy Admission" not in eligible


# ── Profile 5: All scores and GPAX exactly at minimum ────────────────────────

async def test_profile_borderline_all_at_minimum_eligible(seed_tcas, make_user):
    """All values exactly at their minimums → should be eligible for CS and Biology."""
    uid = await make_user(gpax=3.0, scores={
        "TGAT1": 50.0,
        "A_LEVEL_MATH1": 40.0,
        "A_LEVEL_BIOLOGY": 50.0,
        "A_LEVEL_CHEMISTRY": 50.0,
    })
    results = await check_eligibility(uid, year=2026)
    assert "CS Admission" in _eligible_names(results)
    assert "Biology Admission" in _eligible_names(results)


# ── Profile 6: One score just below minimum ───────────────────────────────────

async def test_profile_one_subject_just_below_min_ineligible(seed_tcas, make_user):
    """CS requires A_LEVEL_MATH1 >= 40.  Score is 39.9 → CS ineligible."""
    uid = await make_user(gpax=3.5, scores={
        "TGAT1": 60.0,
        "A_LEVEL_MATH1": 39.9,
    })
    results = await check_eligibility(uid, year=2026)
    assert "CS Admission" not in _eligible_names(results)


# ── Profile 7: No test scores at all ─────────────────────────────────────────

async def test_profile_no_test_scores_fails_subject_requirements(seed_tcas, make_user):
    """GPAX 3.8 but no scores → every project with subject requirements is
    ineligible.  Biology has subject mins so also fails."""
    uid = await make_user(gpax=3.8, scores={})
    results = await check_eligibility(uid, year=2026)
    assert len(_eligible_names(results)) == 0


# ── Profile 8: Science student — good bio/chem, no math ──────────────────────

async def test_profile_science_student_eligible_bio_and_pharmacy(seed_tcas, make_user):
    """Bio/chem but no TGAT1 or math → only Biology and Pharmacy eligible."""
    uid = await make_user(gpax=3.2, scores={
        "A_LEVEL_BIOLOGY": 80.0,
        "A_LEVEL_CHEMISTRY": 75.0,
    })
    results = await check_eligibility(uid, year=2026)
    eligible = _eligible_names(results)
    assert "Biology Admission" in eligible
    assert "Pharmacy Admission" in eligible
    assert "CS Admission" not in eligible
    assert "Medical Admission" not in eligible


# ── Profile 9: No GPAX (never filled profile) ────────────────────────────────

async def test_profile_no_gpax_fails_all_projects_with_gpax_min(seed_tcas, make_user):
    """User has great scores but no GPAX on file.  Anything with a GPAX min is
    automatically ineligible; Biology (no min) depends on scores."""
    uid = await make_user(gpax=None, scores={
        "TGAT1": 90.0, "TPAT2": 90.0,
        "A_LEVEL_MATH1": 85.0,
        "A_LEVEL_BIOLOGY": 90.0,
        "A_LEVEL_CHEMISTRY": 90.0,
    })
    results = await check_eligibility(uid, year=2026)
    eligible = _eligible_names(results)
    assert "Biology Admission" in eligible
    assert "CS Admission" not in eligible
    assert "Pharmacy Admission" not in eligible


# ── Profile 10: Medical track ─────────────────────────────────────────────────

async def test_profile_medical_track_eligible_for_medicine(seed_tcas, make_user):
    """High GPAX + all four medicine requirements met → Medicine eligible."""
    uid = await make_user(gpax=3.8, scores={
        "TGAT1": 75.0,
        "TPAT2": 70.0,
        "A_LEVEL_BIOLOGY": 80.0,
        "A_LEVEL_CHEMISTRY": 80.0,
    })
    results = await check_eligibility(uid, year=2026)
    assert "Medical Admission" in _eligible_names(results)


# ── Profile 11: Pharmacy specialist — chem+bio, no math ──────────────────────

async def test_profile_pharmacy_only_eligible(seed_tcas, make_user):
    """Specifically fits Pharmacy (chem 65 + bio 55) but TGAT1 missing → CS fails."""
    uid = await make_user(gpax=3.1, scores={
        "A_LEVEL_CHEMISTRY": 65.0,
        "A_LEVEL_BIOLOGY": 55.0,
    })
    results = await check_eligibility(uid, year=2026)
    eligible = _eligible_names(results)
    assert "Pharmacy Admission" in eligible
    assert "CS Admission" not in eligible
    assert "Medical Admission" not in eligible


# ── Profile 12: All scores and GPAX one step below every minimum ──────────────

async def test_profile_all_one_below_minimum_ineligible(seed_tcas, make_user):
    """GPAX 2.99, all scores 1 point below floor → zero eligible projects."""
    uid = await make_user(gpax=2.99, scores={
        "TGAT1": 49.0,
        "TPAT2": 59.0,
        "A_LEVEL_MATH1": 39.0,
        "A_LEVEL_BIOLOGY": 49.0,
        "A_LEVEL_CHEMISTRY": 59.0,
    })
    results = await check_eligibility(uid, year=2026)
    assert len(_eligible_names(results)) == 0


# ── Ordering ──────────────────────────────────────────────────────────────────

async def test_eligible_projects_sorted_first(seed_tcas, make_user):
    """Results list must have eligible=True rows before eligible=False rows."""
    uid = await make_user(gpax=3.5, scores={
        "TGAT1": 80.0,
        "A_LEVEL_MATH1": 70.0,
    })
    results = await check_eligibility(uid, year=2026)
    saw_ineligible = False
    for r in results:
        if not r["eligible"]:
            saw_ineligible = True
        if saw_ineligible:
            assert not r["eligible"], "Eligible project appeared after ineligible one"
