"""Test fixtures for the eligibility engine test suite.

Session-scoped:
  db_pool     — initialises and tears down the asyncpg connection pool once per
                test run.  Requires a running Postgres instance (the same Docker
                Compose one used in development).

  seed_tcas   — inserts one university / faculty / major / round-3 project
                row set that all integration tests share.  Cleaned up after the
                session.

Function-scoped:
  make_user   — factory that inserts a user + user_profiles row and returns the
                user_id UUID.  Deletes the user (cascade) after each test.
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from typing import AsyncGenerator

import asyncpg
import pytest

from db.postgres import init_pool, close_pool, fetch, fetchrow, execute


# ── DB pool ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session", autouse=True)
async def db_pool():
    await init_pool()
    yield
    await close_pool()


# ── Shared TCAS seed ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
async def seed_tcas(db_pool):
    """Insert a minimal Round-3 project hierarchy for 2026.

    Returns a dict of IDs so individual tests can reference specific rows.
    """
    u_id = (await fetchrow(
        """INSERT INTO universities (name, location) VALUES ($1, $2)
           ON CONFLICT (name) DO UPDATE SET location = EXCLUDED.location
           RETURNING id""",
        "Test University", "Bangkok",
    ))["id"]

    # Engineering faculty
    f_eng_id = (await fetchrow(
        """INSERT INTO faculties (university_id, name) VALUES ($1, $2)
           RETURNING id""",
        u_id, "Engineering",
    ))["id"]

    # Medicine faculty
    f_med_id = (await fetchrow(
        """INSERT INTO faculties (university_id, name) VALUES ($1, $2)
           RETURNING id""",
        u_id, "Medicine",
    ))["id"]

    # Majors
    m_cs_id = (await fetchrow(
        "INSERT INTO majors (faculty_id, name, field) VALUES ($1,$2,$3) RETURNING id",
        f_eng_id, "Computer Science", "Engineering",
    ))["id"]

    m_med_id = (await fetchrow(
        "INSERT INTO majors (faculty_id, name, field) VALUES ($1,$2,$3) RETURNING id",
        f_med_id, "Medicine", "Health Science",
    ))["id"]

    # Science major — no GPAX min, needs bio/chem but not math
    f_sci_id = (await fetchrow(
        "INSERT INTO faculties (university_id, name) VALUES ($1,$2) RETURNING id",
        u_id, "Science",
    ))["id"]
    m_bio_id = (await fetchrow(
        "INSERT INTO majors (faculty_id, name, field) VALUES ($1,$2,$3) RETURNING id",
        f_sci_id, "Biology", "Science",
    ))["id"]

    # Pharmacy major — needs chem + bio, no math
    f_pharm_id = (await fetchrow(
        "INSERT INTO faculties (university_id, name) VALUES ($1,$2) RETURNING id",
        u_id, "Pharmacy",
    ))["id"]
    m_pharm_id = (await fetchrow(
        "INSERT INTO majors (faculty_id, name, field) VALUES ($1,$2,$3) RETURNING id",
        f_pharm_id, "Pharmacy", "Health Science",
    ))["id"]

    # TCAS Rounds (year=2026, round 3)
    async def mk_round(major_id):
        return (await fetchrow(
            "INSERT INTO tcas_rounds (major_id, round_number, year) VALUES ($1,3,2026) RETURNING id",
            major_id,
        ))["id"]

    r_cs_id = await mk_round(m_cs_id)
    r_med_id = await mk_round(m_med_id)
    r_bio_id = await mk_round(m_bio_id)
    r_pharm_id = await mk_round(m_pharm_id)

    # Admission projects
    async def mk_project(round_id, name, gpax_min, seats):
        return (await fetchrow(
            """INSERT INTO admission_projects
                 (tcas_round_id, project_name, seats, gpax_min)
               VALUES ($1,$2,$3,$4) RETURNING id""",
            round_id, name,
            seats,
            Decimal(str(gpax_min)) if gpax_min is not None else None,
        ))["id"]

    ap_cs_id   = await mk_project(r_cs_id,   "CS Admission",       3.0, 30)
    ap_med_id  = await mk_project(r_med_id,  "Medical Admission",  3.5, 20)
    ap_bio_id  = await mk_project(r_bio_id,  "Biology Admission",  None, 25)
    ap_pharm_id = await mk_project(r_pharm_id, "Pharmacy Admission", 3.0, 15)

    # Subject requirements
    async def mk_req(ap_id, subject, min_score, weight):
        await execute(
            """INSERT INTO subject_requirements
                 (admission_project_id, subject, min_score, weight_percent)
               VALUES ($1,$2,$3,$4)""",
            ap_id, subject,
            min_score, weight,
        )

    # CS: TGAT1 >= 50, A_LEVEL_MATH1 >= 40 (weighted, no floor)
    await mk_req(ap_cs_id,    "TGAT1",          50.0, 30.0)
    await mk_req(ap_cs_id,    "A_LEVEL_MATH1",  40.0, 70.0)

    # Medicine: TGAT1 >= 60, TPAT2 >= 60, A_LEVEL_BIOLOGY >= 70, A_LEVEL_CHEMISTRY >= 70
    await mk_req(ap_med_id,   "TGAT1",              60.0, 20.0)
    await mk_req(ap_med_id,   "TPAT2",              60.0, 20.0)
    await mk_req(ap_med_id,   "A_LEVEL_BIOLOGY",    70.0, 30.0)
    await mk_req(ap_med_id,   "A_LEVEL_CHEMISTRY",  70.0, 30.0)

    # Biology: A_LEVEL_BIOLOGY >= 50, A_LEVEL_CHEMISTRY >= 50 (no GPAX min)
    await mk_req(ap_bio_id,   "A_LEVEL_BIOLOGY",    50.0, 50.0)
    await mk_req(ap_bio_id,   "A_LEVEL_CHEMISTRY",  50.0, 50.0)

    # Pharmacy: A_LEVEL_CHEMISTRY >= 60, A_LEVEL_BIOLOGY >= 50
    await mk_req(ap_pharm_id, "A_LEVEL_CHEMISTRY",  60.0, 60.0)
    await mk_req(ap_pharm_id, "A_LEVEL_BIOLOGY",    50.0, 40.0)

    ids = dict(
        university_id=u_id,
        faculty_eng_id=f_eng_id,
        faculty_med_id=f_med_id,
        faculty_sci_id=f_sci_id,
        faculty_pharm_id=f_pharm_id,
        major_cs_id=m_cs_id,
        major_med_id=m_med_id,
        major_bio_id=m_bio_id,
        major_pharm_id=m_pharm_id,
        round_cs_id=r_cs_id,
        round_med_id=r_med_id,
        round_bio_id=r_bio_id,
        round_pharm_id=r_pharm_id,
        ap_cs_id=ap_cs_id,
        ap_med_id=ap_med_id,
        ap_bio_id=ap_bio_id,
        ap_pharm_id=ap_pharm_id,
    )

    yield ids

    # Teardown — cascade from university removes everything beneath it
    await execute("DELETE FROM universities WHERE id = $1", u_id)


# ── Per-test user factory ─────────────────────────────────────────────────────

@pytest.fixture
async def make_user(db_pool):
    """Return an async factory: make_user(gpax, scores).

    gpax:   float | None
    scores: dict[subject_str, score_float]

    Returns the user_id UUID. Cleans up (cascade) after each test.
    """
    created: list[uuid.UUID] = []

    async def _factory(gpax=None, scores=None):
        uid = uuid.uuid4()
        fake_fuid = f"test_{uid.hex}"
        fake_email = f"{uid.hex[:8]}@test.local"

        await execute(
            """INSERT INTO users (id, email, firebase_uid)
               VALUES ($1, $2, $3)""",
            uid, fake_email, fake_fuid,
        )
        await execute(
            """INSERT INTO user_profiles (user_id, gpax)
               VALUES ($1, $2)""",
            uid,
            Decimal(str(gpax)) if gpax is not None else None,
        )
        if scores:
            for subject, score in scores.items():
                await execute(
                    """INSERT INTO user_test_scores (user_id, subject, score, exam_year)
                       VALUES ($1, $2, $3, 2026)""",
                    uid, subject, score,
                )
        created.append(uid)
        return uid

    yield _factory

    for uid in created:
        await execute("DELETE FROM users WHERE id = $1", uid)
