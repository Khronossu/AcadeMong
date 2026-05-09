"""Profile router — CRUD for user_profiles and user_test_scores.

Endpoints:
    GET  /api/profile/me          — fetch profile + test scores
    PUT  /api/profile/me          — upsert profile + replace test scores
"""

from __future__ import annotations

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
                  current_school, gpax
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
            test_scores=[TestScoreOut(**dict(s)) for s in scores],
        )

    return ProfileResponse(
        **{k: v for k, v in dict(profile).items() if k != "gpax"},
        gpax=float(profile["gpax"]) if profile["gpax"] is not None else None,
        test_scores=[TestScoreOut(**dict(s)) for s in scores],
    )
