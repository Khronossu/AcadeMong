"""Test fixtures for the eligibility engine test suite.

All fixtures are function-scoped so each test gets a fresh asyncpg pool
bound to its own event loop.  This avoids the "Future attached to a
different loop" error that arises when a session-scoped pool (created on
the session loop) is used from a test function's own event loop.

Function-scoped:
  db_pool     — init/close the module-level asyncpg pool for one test.
  seed_tcas   — inserts a minimal 2026 project hierarchy and cleans up
                after the test via university CASCADE DELETE.
  make_user   — factory that creates a user + profile row (and optional
                test scores) and deletes the user (cascade) after the test.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from dotenv import load_dotenv

from db.postgres import init_pool, close_pool, fetch, fetchrow, execute

# Load credentials from repo root .env, then apply backend/.env.test overrides
# (override=True so .env.test wins). .env.test sets POSTGRES_HOST=localhost
# because Docker maps postgres:5432 → localhost:5432 on the host machine.
# Inside Docker, set POSTGRES_HOST=postgres in the environment before running pytest.
_repo_root = Path(__file__).parent.parent.parent
load_dotenv(_repo_root / ".env")
load_dotenv(Path(__file__).parent.parent / ".env.test", override=True)


# ── DB pool ───────────────────────────────────────────────────────────────────

@pytest.fixture
async def db_pool():
    """Create the asyncpg pool for this test, close it on teardown."""
    await init_pool()
    yield
    await close_pool()


# ── Shared TCAS seed ──────────────────────────────────────────────────────────

@pytest.fixture
async def seed_tcas(db_pool):
    """Insert a minimal Round-3 project hierarchy for 2026.

    Projects seeded:
      CS Admission    — GPAX >= 3.0, TGAT1 >= 50, A_LEVEL_MATH1 >= 40
      Medical         — GPAX >= 3.5, TGAT1 >= 60, TPAT2 >= 60, BIO >= 70, CHEM >= 70
      Biology         — No GPAX min, A_LEVEL_BIOLOGY >= 50, A_LEVEL_CHEMISTRY >= 50
      Pharmacy        — GPAX >= 3.0, A_LEVEL_CHEMISTRY >= 60, A_LEVEL_BIOLOGY >= 50

    Teardown: DELETE FROM universities WHERE id = $1 (CASCADE removes everything).
    """
    u_id = (await fetchrow(
        """INSERT INTO universities (name, location) VALUES ($1, $2)
           ON CONFLICT (name) DO UPDATE SET location = EXCLUDED.location
           RETURNING id""",
        "Test University", "Bangkok",
    ))["id"]

    f_eng_id = (await fetchrow(
        "INSERT INTO faculties (university_id, name) VALUES ($1,$2) RETURNING id",
        u_id, "Engineering",
    ))["id"]
    f_med_id = (await fetchrow(
        "INSERT INTO faculties (university_id, name) VALUES ($1,$2) RETURNING id",
        u_id, "Medicine",
    ))["id"]
    f_sci_id = (await fetchrow(
        "INSERT INTO faculties (university_id, name) VALUES ($1,$2) RETURNING id",
        u_id, "Science",
    ))["id"]
    f_pharm_id = (await fetchrow(
        "INSERT INTO faculties (university_id, name) VALUES ($1,$2) RETURNING id",
        u_id, "Pharmacy",
    ))["id"]

    m_cs_id = (await fetchrow(
        "INSERT INTO majors (faculty_id, name, field) VALUES ($1,$2,$3) RETURNING id",
        f_eng_id, "Computer Science", "Engineering",
    ))["id"]
    m_med_id = (await fetchrow(
        "INSERT INTO majors (faculty_id, name, field) VALUES ($1,$2,$3) RETURNING id",
        f_med_id, "Medicine", "Health Science",
    ))["id"]
    m_bio_id = (await fetchrow(
        "INSERT INTO majors (faculty_id, name, field) VALUES ($1,$2,$3) RETURNING id",
        f_sci_id, "Biology", "Science",
    ))["id"]
    m_pharm_id = (await fetchrow(
        "INSERT INTO majors (faculty_id, name, field) VALUES ($1,$2,$3) RETURNING id",
        f_pharm_id, "Pharmacy", "Health Science",
    ))["id"]

    async def mk_round(major_id):
        return (await fetchrow(
            "INSERT INTO tcas_rounds (major_id, round_number, year) VALUES ($1,3,2026) RETURNING id",
            major_id,
        ))["id"]

    r_cs_id    = await mk_round(m_cs_id)
    r_med_id   = await mk_round(m_med_id)
    r_bio_id   = await mk_round(m_bio_id)
    r_pharm_id = await mk_round(m_pharm_id)

    async def mk_project(round_id, name, gpax_min, seats):
        return (await fetchrow(
            """INSERT INTO admission_projects
                 (tcas_round_id, project_name, seats, gpax_min)
               VALUES ($1,$2,$3,$4) RETURNING id""",
            round_id, name, seats,
            Decimal(str(gpax_min)) if gpax_min is not None else None,
        ))["id"]

    ap_cs_id    = await mk_project(r_cs_id,    "CS Admission",      3.0, 30)
    ap_med_id   = await mk_project(r_med_id,   "Medical Admission", 3.5, 20)
    ap_bio_id   = await mk_project(r_bio_id,   "Biology Admission", None, 25)
    ap_pharm_id = await mk_project(r_pharm_id, "Pharmacy Admission", 3.0, 15)

    async def mk_req(ap_id, subject, min_score, weight):
        await execute(
            """INSERT INTO subject_requirements
                 (admission_project_id, subject, min_score, weight_percent)
               VALUES ($1,$2,$3,$4)""",
            ap_id, subject, min_score, weight,
        )

    await mk_req(ap_cs_id,    "TGAT1",             50.0, 30.0)
    await mk_req(ap_cs_id,    "A_LEVEL_MATH1",     40.0, 70.0)
    await mk_req(ap_med_id,   "TGAT1",             60.0, 20.0)
    await mk_req(ap_med_id,   "TPAT2",             60.0, 20.0)
    await mk_req(ap_med_id,   "A_LEVEL_BIOLOGY",   70.0, 30.0)
    await mk_req(ap_med_id,   "A_LEVEL_CHEMISTRY", 70.0, 30.0)
    await mk_req(ap_bio_id,   "A_LEVEL_BIOLOGY",   50.0, 50.0)
    await mk_req(ap_bio_id,   "A_LEVEL_CHEMISTRY", 50.0, 50.0)
    await mk_req(ap_pharm_id, "A_LEVEL_CHEMISTRY", 60.0, 60.0)
    await mk_req(ap_pharm_id, "A_LEVEL_BIOLOGY",   50.0, 40.0)

    yield dict(
        university_id=u_id,
        ap_cs_id=ap_cs_id, ap_med_id=ap_med_id,
        ap_bio_id=ap_bio_id, ap_pharm_id=ap_pharm_id,
    )

    await execute("DELETE FROM universities WHERE id = $1", u_id)


# ── Per-test user factory ─────────────────────────────────────────────────────

@pytest.fixture
async def make_user(db_pool):
    """Async factory: make_user(gpax, scores) → user_id UUID.

    gpax:   float | None
    scores: dict[subject_str, score_float]  (exam_year defaults to 2026)

    Cleans up (CASCADE from users) after each test.
    """
    created: list[uuid.UUID] = []

    async def _factory(gpax=None, scores=None):
        uid = uuid.uuid4()
        await execute(
            "INSERT INTO users (id, email, firebase_uid) VALUES ($1,$2,$3)",
            uid, f"{uid.hex[:8]}@test.local", f"test_{uid.hex}",
        )
        await execute(
            "INSERT INTO user_profiles (user_id, gpax) VALUES ($1,$2)",
            uid,
            Decimal(str(gpax)) if gpax is not None else None,
        )
        for subject, score in (scores or {}).items():
            await execute(
                """INSERT INTO user_test_scores (user_id, subject, score, exam_year)
                   VALUES ($1,$2,$3,2026)""",
                uid, subject, score,
            )
        created.append(uid)
        return uid

    yield _factory

    for uid in created:
        await execute("DELETE FROM users WHERE id = $1", uid)
