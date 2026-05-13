"""Tests for the Two-Stage Major Recommendation Engine."""

import pytest
from engines.recommendation_engine import recommend_majors

@pytest.mark.asyncio
async def test_recommend_majors_drops_ineligible(seed_tcas, make_user):
    """Test Stage 1: Hard filtering drops majors if GPAX or Subject score is below minimum."""
    # Medical Admission needs GPAX 3.5, TGAT1 60, TPAT2 60, BIO 70, CHEM 70
    # CS Admission needs GPAX 3.0, TGAT1 50, MATH1 40
    scores = {
        "TGAT1": 80.0,
        "TPAT2": 80.0,
        "A_LEVEL_BIOLOGY": 80.0,
        "A_LEVEL_CHEMISTRY": 80.0,
        "A_LEVEL_MATH1": 60.0,
    }
    uid = await make_user(gpax=3.4, scores=scores)
    
    # Even though subject scores are high, GPAX is 3.4 (Medical needs 3.5)
    # Medical should be dropped entirely. CS should pass.
    results = await recommend_majors(user_id=uid, scores=scores)
    
    project_names = [r["project_name"] for r in results]
    assert "Medical Admission" not in project_names
    assert "CS Admission" in project_names

@pytest.mark.asyncio
async def test_recommend_majors_scoring_weights(seed_tcas, make_user):
    """Test Stage 2: Scoring 100-point scale prioritizes interests and high academic fit."""
    scores = {
        "TGAT1": 90.0,
        "TPAT2": 90.0,
        "A_LEVEL_BIOLOGY": 90.0,
        "A_LEVEL_CHEMISTRY": 90.0,
        "A_LEVEL_MATH1": 90.0,
    }
    uid = await make_user(gpax=4.0, scores=scores)
    
    # User meets all requirements.
    # Without interests/university pref, Academic Fit should determine rank.
    results = await recommend_majors(user_id=uid, scores=scores)
    assert len(results) >= 4  # Should return all 4 seeded majors
    
    # Now add interests and university preference to heavily boost a specific major
    results_with_pref = await recommend_majors(
        user_id=uid,
        scores=scores,
        interests=["Computer Science"],
        preferred_universities=["Test University"]
    )
    
    top_match = results_with_pref[0]
    # Should be CS Admission because of the Interest Match (+30) and University (+20)
    assert top_match["project_name"] == "CS Admission"
    assert top_match["fit_score"] > 80.0  # Should be close to 100

@pytest.mark.asyncio
async def test_recommend_majors_partial_scores(seed_tcas, make_user):
    """Test Stage 2: Academic fit scoring calculates proportional subject weights correctly."""
    # CS Admission requires TGAT1 (weight 30) and MATH1 (weight 70)
    # Total max academic points = 50
    # If user gets 50 in TGAT1 (50% of 30 = 15) and 40 in MATH1 (40% of 70 = 28),
    # academic score = (15 + 28) * 0.5 = 21.5
    scores = {
        "TGAT1": 50.0,
        "A_LEVEL_MATH1": 40.0,
    }
    uid = await make_user(gpax=3.0, scores=scores)
    
    results = await recommend_majors(user_id=uid, scores=scores)
    
    # Filter for CS Admission
    cs_result = next((r for r in results if r["project_name"] == "CS Admission"), None)
    assert cs_result is not None
    
    # Verify the math
    # TGAT1 (30 weight): 50/100 * 30 = 15
    # MATH1 (70 weight): 40/100 * 70 = 28
    # Sum = 43
    # Scaled to max 50: 43 * 0.5 = 21.5
    assert cs_result["fit_score"] == 21.5
