"""Profile router — CRUD for user_profiles and user_test_scores.

Endpoints:
    GET  /api/profile/me          — fetch profile + test scores
    PUT  /api/profile/me          — upsert profile + replace test scores
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from auth.firebase_admin import get_current_user
from db.postgres import execute, fetch, fetchrow

router = APIRouter()

# ── Controlled vocabulary (mirrors DATA_CONTRACT §7.1) ───────────────────────
VALID_SUBJECTS = {
    "TGAT1", "TGAT2", "TGAT3", "TGAT",
    "TPAT1", "TPAT2", "TPAT3", "TPAT4", "TPAT5",
    "A_LEVEL_MATH1", "A_LEVEL_MATH2",
    "A_LEVEL_PHYSICS", "A_LEVEL_CHEMISTRY", "A_LEVEL_BIOLOGY", "A_LEVEL_GENERAL_SCIENCE",
    "A_LEVEL_THAI", "A_LEVEL_ENGLISH", "A_LEVEL_SOCIAL_STUDIES",
    "A_LEVEL_FRENCH", "A_LEVEL_GERMAN", "A_LEVEL_JAPANESE",
    "A_LEVEL_CHINESE", "A_LEVEL_ARABIC", "A_LEVEL_PALI",
    "A_LEVEL_KOREAN", "A_LEVEL_SPANISH",
    "GPAX",
}


# ── Pydantic models ───────────────────────────────────────────────────────────

class TestScoreIn(BaseModel):
    subject: str
    score: float = Field(ge=0, le=100)
    exam_year: int = Field(ge=2020, le=2100)

    @field_validator("subject")
    @classmethod
    def subject_must_be_valid(cls, v: str) -> str:
        if v not in VALID_SUBJECTS:
            raise ValueError(f"Unknown subject '{v}'. Must be one of the controlled vocabulary.")
        return v


class ProfileUpdateRequest(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    avatar_url: Optional[str] = None
    address: Optional[str] = None
    sub_district: Optional[str] = None
    district: Optional[str] = None
    province: Optional[str] = None
    postal_code: Optional[str] = None
    current_school: Optional[str] = None
    gpax: Optional[float] = Field(None, ge=0.0, le=4.0)
    interests: Optional[list[str]] = None
    target_universities: Optional[list[str]] = None
    test_scores: Optional[list[TestScoreIn]] = None


class TestScoreOut(BaseModel):
    subject: str
    score: float
    exam_year: int


class ProfileResponse(BaseModel):
    user_id: UUID
    first_name: Optional[str]
    last_name: Optional[str]
    date_of_birth: Optional[date]
    avatar_url: Optional[str]
    address: Optional[str]
    sub_district: Optional[str]
    district: Optional[str]
    province: Optional[str]
    postal_code: Optional[str]
    current_school: Optional[str]
    gpax: Optional[float]
    interests: Optional[list[str]] = None
    target_universities: Optional[list[str]] = None
    test_scores: list[TestScoreOut]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=ProfileResponse,
    summary="Get current user's profile and test scores",
)
async def get_profile(user: dict = Depends(get_current_user)):
    user_id: UUID = user["id"]

    profile = await fetchrow(
        """SELECT user_id, first_name, last_name, date_of_birth, avatar_url,
                  address, sub_district, district, province, postal_code,
                  current_school, gpax, interests, target_universities
           FROM user_profiles WHERE user_id = $1""",
        user_id,
    )

    scores = await fetch(
        "SELECT subject, score, exam_year FROM user_test_scores WHERE user_id = $1 ORDER BY subject, exam_year DESC",
        user_id,
    )

    if not profile:
        return ProfileResponse(
            user_id=user_id,
            first_name=None, last_name=None, date_of_birth=None,
            avatar_url=None, address=None, sub_district=None,
            district=None, province=None, postal_code=None,
            current_school=None, gpax=None,
            interests=None, target_universities=None,
            test_scores=[TestScoreOut(**dict(s)) for s in scores],
        )

    p = dict(profile)
    return ProfileResponse(
        **{k: v for k, v in p.items() if k not in ("gpax",)},
        gpax=float(p["gpax"]) if p["gpax"] is not None else None,
        test_scores=[TestScoreOut(**dict(s)) for s in scores],
    )


@router.put(
    "/me",
    response_model=ProfileResponse,
    summary="Upsert profile and replace test scores",
)
async def update_profile(
    req: ProfileUpdateRequest,
    user: dict = Depends(get_current_user),
):
    user_id: UUID = user["id"]

    existing = await fetchrow(
        "SELECT id FROM user_profiles WHERE user_id = $1", user_id
    )
    interests_json = json.dumps(req.interests) if req.interests is not None else None
    target_univ_json = json.dumps(req.target_universities) if req.target_universities is not None else None

    if existing:
        await execute(
            """UPDATE user_profiles
               SET first_name = COALESCE($1, first_name),
                   last_name = COALESCE($2, last_name),
                   date_of_birth = COALESCE($3, date_of_birth),
                   avatar_url = COALESCE($4, avatar_url),
                   address = COALESCE($5, address),
                   sub_district = COALESCE($6, sub_district),
                   district = COALESCE($7, district),
                   province = COALESCE($8, province),
                   postal_code = COALESCE($9, postal_code),
                   current_school = COALESCE($10, current_school),
                   gpax = COALESCE($11, gpax),
                   interests = COALESCE($12::jsonb, interests),
                   target_universities = COALESCE($13::jsonb, target_universities),
                   updated_at = CURRENT_TIMESTAMP
               WHERE user_id = $14""",
            req.first_name, req.last_name, req.date_of_birth,
            req.avatar_url, req.address, req.sub_district,
            req.district, req.province, req.postal_code,
            req.current_school,
            Decimal(str(req.gpax)) if req.gpax is not None else None,
            interests_json, target_univ_json,
            user_id,
        )
    else:
        await execute(
            """INSERT INTO user_profiles
               (user_id, first_name, last_name, date_of_birth, avatar_url,
                address, sub_district, district, province, postal_code,
                current_school, gpax, interests, target_universities)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb, $14::jsonb)""",
            user_id,
            req.first_name, req.last_name, req.date_of_birth,
            req.avatar_url, req.address, req.sub_district,
            req.district, req.province, req.postal_code,
            req.current_school,
            Decimal(str(req.gpax)) if req.gpax is not None else None,
            interests_json, target_univ_json,
        )

    if req.test_scores is not None:
        # Upsert each score — keep the most recent per (user, subject, exam_year)
        for ts in req.test_scores:
            await execute(
                """INSERT INTO user_test_scores (user_id, subject, score, exam_year)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (user_id, subject, exam_year)
                   DO UPDATE SET score = EXCLUDED.score, updated_at = CURRENT_TIMESTAMP""",
                user_id, ts.subject, ts.score, ts.exam_year,
            )

    return await get_profile(user=user)


# ── Saved majors ──────────────────────────────────────────────────────────────

class SaveMajorRequest(BaseModel):
    major_id: UUID
    notes: Optional[str] = None


@router.get("/saved-majors", summary="List saved majors")
async def list_saved_majors(user: dict = Depends(get_current_user)):
    rows = await fetch(
        """SELECT sm.major_id, sm.notes, sm.saved_at,
                  m.name AS major_name,
                  f.name AS faculty_name,
                  u.name AS university_name
           FROM user_saved_majors sm
           JOIN majors m ON m.id = sm.major_id
           JOIN faculties f ON f.id = m.faculty_id
           JOIN universities u ON u.id = f.university_id
           WHERE sm.user_id = $1
           ORDER BY sm.saved_at DESC""",
        user["id"],
    )
    return {"saved_majors": [dict(r) for r in rows]}


@router.post("/saved-majors", summary="Save a major", status_code=201)
async def save_major(req: SaveMajorRequest, user: dict = Depends(get_current_user)):
    await execute(
        """INSERT INTO user_saved_majors (user_id, major_id, notes)
           VALUES ($1, $2, $3)
           ON CONFLICT (user_id, major_id) DO UPDATE SET notes = EXCLUDED.notes""",
        user["id"], req.major_id, req.notes,
    )
    return {"ok": True}


@router.delete("/saved-majors/{major_id}", summary="Remove a saved major")
async def remove_saved_major(major_id: UUID, user: dict = Depends(get_current_user)):
    await execute(
        "DELETE FROM user_saved_majors WHERE user_id = $1 AND major_id = $2",
        user["id"], major_id,
    )
    return {"ok": True}


# ── Career recommendations ────────────────────────────────────────────────────

@router.get("/career-recommendations", summary="Get AI career recommendations")
async def get_career_recommendations(user: dict = Depends(get_current_user)):
    rows = await fetch(
        """SELECT cc.title, cc.overview_description, cc.avg_salary_thb,
                  cc.top_skills, ig.name AS industry_group,
                  urc.match_score, urc.ai_reasoning, urc.created_at
           FROM user_recommended_careers urc
           JOIN career_catalog cc ON cc.id = urc.career_id
           LEFT JOIN industry_groups ig ON ig.id = cc.industry_group_id
           WHERE urc.user_id = $1
           ORDER BY urc.match_score DESC
           LIMIT 10""",
        user["id"],
    )
    return {"recommendations": [dict(r) for r in rows]}
