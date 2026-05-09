"""
Run with:
    docker compose exec fastapi python -m db.verify
    
Exits 0 if every check passes, 1 if anything fails.
Not imported by the app; this is a standalone tool.
"""
import asyncio
import os
import sys
import uuid
from typing import Optional

import asyncpg

from db.postgres import init_pool, close_pool, get_pool, fetch


#Expected schema state
EXPECTED_TABLES: set[str] = {
    'users',
    'user_profiles',
    'user_career_profiles',
    'industry_groups',
    'career_catalog',
    'user_recommended_careers',
    'universities',
    'faculties',
    'majors',
    'tcas_rounds',
    'admission_projects',
    'subject_requirements',
    'user_saved_majors',
    'chat_sessions',
    'chat_messages',
    'user_test_scores',
    'historical_cutoffs',
}

# Map: (child_table, child_column) -> (parent_table, delete_rule)
# delete_rule is one of: "CASCADE", "SET NULL", "RESTRICT", "NO ACTION"
EXPECTED_FKS: dict[tuple[str, str], tuple[str, str]] = {
    ('user_profiles', 'user_id'): ('users', 'CASCADE'),
    ('user_career_profiles', 'user_id'): ('users', 'CASCADE'),
    ('career_catalog', 'industry_group_id'): ('industry_groups', 'SET NULL' ),
    ('user_recommended_careers', 'user_id'): ('users', 'CASCADE'),
    ('user_recommended_careers', 'career_id'): ('career_catalog', 'CASCADE'),
    ('faculties', 'university_id'): ('universities', 'CASCADE'),
    ('majors', 'faculty_id'): ('faculties', 'CASCADE'),
    ('tcas_rounds', 'major_id'): ('majors', 'CASCADE'),
    ('admission_projects', 'tcas_round_id'): ('tcas_rounds', 'CASCADE'),
    ('subject_requirements', 'admission_project_id'): ('admission_projects', 'CASCADE'),
    ('user_saved_majors', 'user_id'): ('users', 'CASCADE'),
    ('user_saved_majors', 'major_id'): ('majors', 'CASCADE'),
    ('chat_sessions', 'user_id'): ('users', 'CASCADE'),
    ('chat_messages', 'session_id'): ('chat_sessions', 'CASCADE'),
    ('user_test_scores', 'user_id'): ('users', 'CASCADE'),
    ('historical_cutoffs', 'admission_project_id'): ('admission_projects', 'CASCADE'),
}

# ── Tiny output helpers ─────────────────────────────────────────────────────
# Uniform check output. Keeps the script readable and CI-parseable.

def ok(label: str) -> None:
    print(f"  [PASS] {label}")

def fail(label: str, detail: str = "") -> None:
    msg = f"  [FAIL] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)


# ── 1. Structural: expected tables all exist ────────────────────────────────

async def check_tables_exist() -> bool:
    print("[STRUCTURAL] tables")
    query = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
    rows = await fetch(query)
    found = {row["table_name"] for row in rows}
    missing = EXPECTED_TABLES - found
    if not missing:
        ok(f'all {len(EXPECTED_TABLES)} tables present')
        return True
    else:
        fail('missing tables',','.join(sorted(missing)))
    return False

# ── 2. Structural: FKs declared with correct delete rules ───────────────────

async def check_fks_declared() -> bool:
    FK_QUERY = """
    SELECT
        tc.table_name AS child_table,
        kcu.column_name AS child_column,
        ccu.table_name AS parent_table,
        rc.delete_rule
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name
    JOIN information_schema.constraint_column_usage ccu
        ON tc.constraint_name = ccu.constraint_name
    JOIN information_schema.referential_constraints rc
        ON tc.constraint_name = rc.constraint_name
    WHERE tc.constraint_type = 'FOREIGN KEY'
        AND tc.table_schema = 'public'
    """
    rows = await fetch(FK_QUERY)
    declared = {
        (row["child_table"], row["child_column"]): (row["parent_table"], row["delete_rule"])
        for row in rows
    }

    all_passed = True
    for key, expected in EXPECTED_FKS.items():
        if key not in declared:
            fail(f'{key} not declared')
            all_passed = False
        elif declared[key] != expected:
            fail(f'{key}', f'got {declared[key]}, expected {expected}')
            all_passed = False
        else:
            ok(f'{key[0]}.{key[1]} -> {expected[0]} {expected[1]}')
    return all_passed


# ── 3. Behavioral: cascades actually fire ───────────────────────────────────

async def check_cascades() -> bool:
    """Insert test rows, delete parents, assert cascades fired as declared.

    CRITICAL: everything happens inside a single transaction that we
    intentionally ROLLBACK at the end. The DB is unchanged when this function
    returns, even if assertions fail.
    """
    print("[BEHAVIORAL] cascades")
    all_passed = True

    # Fresh UUIDs per scenario — no chance of colliding with real data or
    # with each other across scenarios.
    # Scenario 1: user-side cascades
    s1_user_id = uuid.uuid4()
    s1_career_id = uuid.uuid4()      # parent for user_recommended_careers
    s1_uni_id = uuid.uuid4()         # parent chain for user_saved_majors
    s1_fac_id = uuid.uuid4()
    s1_maj_id = uuid.uuid4()
    s1_session_id = uuid.uuid4()     # parent for chat_messages transitive check

    # Scenario 2: industry_group → career_catalog SET NULL
    s2_industry_id = uuid.uuid4()
    s2_career_id = uuid.uuid4()

    # Scenario 3: full university hierarchy
    s3_uni_id = uuid.uuid4()
    s3_fac_id = uuid.uuid4()
    s3_maj_id = uuid.uuid4()
    s3_round_id = uuid.uuid4()
    s3_project_id = uuid.uuid4()
    s3_subject_id = uuid.uuid4()

    # Scenario 4: career_catalog → user_recommended_careers
    s4_user_id = uuid.uuid4()
    s4_career_id = uuid.uuid4()

    # Scenario 5: majors → user_saved_majors
    s5_user_id = uuid.uuid4()
    s5_uni_id = uuid.uuid4()
    s5_fac_id = uuid.uuid4()
    s5_maj_id = uuid.uuid4()

    # Scenario 6: users → user_test_scores
    s6_user_id = uuid.uuid4()

    # Scenario 7: admission_projects → historical_cutoffs + partial unique index
    s7_uni_id = uuid.uuid4()
    s7_fac_id = uuid.uuid4()
    s7_maj_id = uuid.uuid4()
    s7_round_id = uuid.uuid4()
    s7_project_id = uuid.uuid4()

    # Scenario 8: round_type trigger
    s8_uni_id = uuid.uuid4()
    s8_fac_id = uuid.uuid4()
    s8_maj_id = uuid.uuid4()
    s8_round_id = uuid.uuid4()  # round_number=3
    s8_project_id = uuid.uuid4()

    async with get_pool().acquire() as conn:
        # Outer transaction — the thing we'll roll back at the end.
        tx = conn.transaction()
        await tx.start()
        try:
            # =============================================================
            # Scenario 1: DELETE user → cascades to all user-owned tables
            # Direct FKs tested: user_profiles, user_career_profiles,
            #   user_saved_majors, user_recommended_careers, chat_sessions
            # Transitive: chat_messages (via chat_sessions cascade)
            # =============================================================

            # Parent chain for user_saved_majors — need a real major.
            await conn.execute(
                "INSERT INTO universities (id, name) VALUES ($1, $2)",
                s1_uni_id, f"Verify Uni S1 {s1_uni_id}",
            )
            await conn.execute(
                "INSERT INTO faculties (id, university_id, name) VALUES ($1, $2, $3)",
                s1_fac_id, s1_uni_id, "Verify Faculty S1",
            )
            await conn.execute(
                "INSERT INTO majors (id, faculty_id, name) VALUES ($1, $2, $3)",
                s1_maj_id, s1_fac_id, "Verify Major S1",
            )
            # Parent for user_recommended_careers — need a real career.
            await conn.execute(
                "INSERT INTO career_catalog (id, title) VALUES ($1, $2)",
                s1_career_id, f"Verify Career S1 {s1_career_id}",
            )
            # The user and every direct child row we want to cascade-delete.
            await conn.execute(
                "INSERT INTO users (id, email, firebase_uid) VALUES ($1, $2, $3)",
                s1_user_id, f"verify-s1-{s1_user_id}@example.com", f"fb-s1-{s1_user_id}",
            )
            await conn.execute(
                "INSERT INTO user_profiles (user_id) VALUES ($1)", s1_user_id,
            )
            await conn.execute(
                "INSERT INTO user_career_profiles (user_id) VALUES ($1)", s1_user_id,
            )
            await conn.execute(
                "INSERT INTO user_saved_majors (user_id, major_id) VALUES ($1, $2)",
                s1_user_id, s1_maj_id,
            )
            await conn.execute(
                "INSERT INTO user_recommended_careers (user_id, career_id) VALUES ($1, $2)",
                s1_user_id, s1_career_id,
            )
            await conn.execute(
                "INSERT INTO chat_sessions (id, user_id, ai_mode) VALUES ($1, $2, $3)",
                s1_session_id, s1_user_id, "dreamer",
            )
            await conn.execute(
                "INSERT INTO chat_messages (session_id, role, content) VALUES ($1, $2, $3)",
                s1_session_id, "user", "hello from verify",
            )

            # One statement should fire every cascade at once.
            await conn.execute("DELETE FROM users WHERE id = $1", s1_user_id)

            # Walk each cascade declaratively — keeps labels and queries together.
            user_cascade_checks = [
                ("users -> user_profiles CASCADE",
                    "SELECT COUNT(*) FROM user_profiles WHERE user_id = $1", s1_user_id),
                ("users -> user_career_profiles CASCADE",
                    "SELECT COUNT(*) FROM user_career_profiles WHERE user_id = $1", s1_user_id),
                ("users -> user_saved_majors CASCADE",
                    "SELECT COUNT(*) FROM user_saved_majors WHERE user_id = $1", s1_user_id),
                ("users -> user_recommended_careers CASCADE",
                    "SELECT COUNT(*) FROM user_recommended_careers WHERE user_id = $1", s1_user_id),
                ("users -> chat_sessions CASCADE",
                    "SELECT COUNT(*) FROM chat_sessions WHERE user_id = $1", s1_user_id),
                # Transitive: session was cascade-deleted, its messages must go too.
                ("chat_sessions -> chat_messages CASCADE (transitive)",
                    "SELECT COUNT(*) FROM chat_messages WHERE session_id = $1", s1_session_id),
            ]
            for label, query, arg in user_cascade_checks:
                remaining = await conn.fetchval(query, arg)
                if remaining == 0:
                    ok(label)
                else:
                    fail(label, f"{remaining} child rows survived")
                    all_passed = False

            # =============================================================
            # Scenario 2: DELETE industry_group → SET NULL on career_catalog
            # The career row MUST still exist; only its FK column is nulled.
            # =============================================================
            await conn.execute(
                "INSERT INTO industry_groups (id, name) VALUES ($1, $2)",
                s2_industry_id, f"Verify Industry {s2_industry_id}",
            )
            await conn.execute(
                "INSERT INTO career_catalog (id, industry_group_id, title) VALUES ($1, $2, $3)",
                s2_career_id, s2_industry_id, f"Verify Career S2 {s2_career_id}",
            )

            await conn.execute(
                "DELETE FROM industry_groups WHERE id = $1", s2_industry_id,
            )

            # Two-part assertion: row survives AND its FK is NULL.
            row = await conn.fetchrow(
                "SELECT industry_group_id FROM career_catalog WHERE id = $1",
                s2_career_id,
            )
            label = "industry_groups -> career_catalog SET NULL"
            if row is None:
                # Worse than a CASCADE mismatch — the child got deleted, meaning
                # whoever wrote the FK used CASCADE. Different bug, worth calling out.
                fail(label, "career row was deleted (expected SET NULL, got CASCADE)")
                all_passed = False
            elif row["industry_group_id"] is not None:
                fail(label, f"industry_group_id = {row['industry_group_id']!r}, expected NULL")
                all_passed = False
            else:
                ok(label)

            # =============================================================
            # Scenario 3: DELETE university → full TCAS chain cascade
            # universities -> faculties -> majors -> tcas_rounds
            #   -> admission_projects -> subject_requirements
            # Most links here are proven TRANSITIVELY. That's valid because
            # check_fks_declared already confirmed each link is declared as
            # CASCADE with the expected child column — transitive evidence
            # is enough to prove the chain fires end-to-end.
            # =============================================================
            await conn.execute(
                "INSERT INTO universities (id, name) VALUES ($1, $2)",
                s3_uni_id, f"Verify Uni S3 {s3_uni_id}",
            )
            await conn.execute(
                "INSERT INTO faculties (id, university_id, name) VALUES ($1, $2, $3)",
                s3_fac_id, s3_uni_id, "Verify Faculty S3",
            )
            await conn.execute(
                "INSERT INTO majors (id, faculty_id, name) VALUES ($1, $2, $3)",
                s3_maj_id, s3_fac_id, "Verify Major S3",
            )
            await conn.execute(
                "INSERT INTO tcas_rounds (id, major_id, round_number, year) VALUES ($1, $2, $3, $4)",
                s3_round_id, s3_maj_id, 1, 2026,
            )
            await conn.execute(
                "INSERT INTO admission_projects (id, tcas_round_id, project_name) VALUES ($1, $2, $3)",
                s3_project_id, s3_round_id, "Verify Project",
            )
            await conn.execute(
                "INSERT INTO subject_requirements (id, admission_project_id, subject) VALUES ($1, $2, $3)",
                s3_subject_id, s3_project_id, "TGAT",
            )

            await conn.execute("DELETE FROM universities WHERE id = $1", s3_uni_id)

            chain_checks = [
                ("universities -> faculties CASCADE",
                    "SELECT COUNT(*) FROM faculties WHERE id = $1", s3_fac_id),
                ("faculties -> majors CASCADE (transitive)",
                    "SELECT COUNT(*) FROM majors WHERE id = $1", s3_maj_id),
                ("majors -> tcas_rounds CASCADE (transitive)",
                    "SELECT COUNT(*) FROM tcas_rounds WHERE id = $1", s3_round_id),
                ("tcas_rounds -> admission_projects CASCADE (transitive)",
                    "SELECT COUNT(*) FROM admission_projects WHERE id = $1", s3_project_id),
                ("admission_projects -> subject_requirements CASCADE (transitive)",
                    "SELECT COUNT(*) FROM subject_requirements WHERE id = $1", s3_subject_id),
            ]
            for label, query, arg in chain_checks:
                remaining = await conn.fetchval(query, arg)
                if remaining == 0:
                    ok(label)
                else:
                    fail(label, f"{remaining} child rows survived")
                    all_passed = False

            # =============================================================
            # Scenario 4: DELETE career_catalog -> user_recommended_careers
            # Scenario 1 tested the user-side FK; this tests the career-side.
            # =============================================================
            await conn.execute(
                "INSERT INTO users (id, email, firebase_uid) VALUES ($1, $2, $3)",
                s4_user_id, f"verify-s4-{s4_user_id}@example.com", f"fb-s4-{s4_user_id}",
            )
            await conn.execute(
                "INSERT INTO career_catalog (id, title) VALUES ($1, $2)",
                s4_career_id, f"Verify Career S4 {s4_career_id}",
            )
            await conn.execute(
                "INSERT INTO user_recommended_careers (user_id, career_id) VALUES ($1, $2)",
                s4_user_id, s4_career_id,
            )

            await conn.execute("DELETE FROM career_catalog WHERE id = $1", s4_career_id)

            remaining = await conn.fetchval(
                "SELECT COUNT(*) FROM user_recommended_careers WHERE career_id = $1",
                s4_career_id,
            )
            label = "career_catalog -> user_recommended_careers CASCADE"
            if remaining == 0:
                ok(label)
            else:
                fail(label, f"{remaining} child rows survived")
                all_passed = False

            # =============================================================
            # Scenario 5: DELETE major -> user_saved_majors
            # Scenario 1 tested the user-side FK; this tests the major-side.
            # =============================================================
            await conn.execute(
                "INSERT INTO users (id, email, firebase_uid) VALUES ($1, $2, $3)",
                s5_user_id, f"verify-s5-{s5_user_id}@example.com", f"fb-s5-{s5_user_id}",
            )
            await conn.execute(
                "INSERT INTO universities (id, name) VALUES ($1, $2)",
                s5_uni_id, f"Verify Uni S5 {s5_uni_id}",
            )
            await conn.execute(
                "INSERT INTO faculties (id, university_id, name) VALUES ($1, $2, $3)",
                s5_fac_id, s5_uni_id, "Verify Faculty S5",
            )
            await conn.execute(
                "INSERT INTO majors (id, faculty_id, name) VALUES ($1, $2, $3)",
                s5_maj_id, s5_fac_id, "Verify Major S5",
            )
            await conn.execute(
                "INSERT INTO user_saved_majors (user_id, major_id) VALUES ($1, $2)",
                s5_user_id, s5_maj_id,
            )

            await conn.execute("DELETE FROM majors WHERE id = $1", s5_maj_id)

            remaining = await conn.fetchval(
                "SELECT COUNT(*) FROM user_saved_majors WHERE major_id = $1",
                s5_maj_id,
            )
            label = "majors -> user_saved_majors CASCADE"
            if remaining == 0:
                ok(label)
            else:
                fail(label, f"{remaining} child rows survived")
                all_passed = False

            # =============================================================
            # Scenario 6: DELETE user -> user_test_scores CASCADE
            # =============================================================
            await conn.execute(
                "INSERT INTO users (id, email, firebase_uid) VALUES ($1, $2, $3)",
                s6_user_id, f"verify-s6-{s6_user_id}@example.com", f"fb-s6-{s6_user_id}",
            )
            await conn.execute(
                "INSERT INTO user_test_scores (user_id, test_code, score, exam_year) "
                "VALUES ($1, $2, $3, $4)",
                s6_user_id, "TGAT1", 75.25, 2026,
            )
            await conn.execute("DELETE FROM users WHERE id = $1", s6_user_id)
            remaining = await conn.fetchval(
                "SELECT COUNT(*) FROM user_test_scores WHERE user_id = $1", s6_user_id,
            )
            label = "users -> user_test_scores CASCADE"
            if remaining == 0:
                ok(label)
            else:
                fail(label, f"{remaining} child rows survived")
                all_passed = False

            # =============================================================
            # Scenario 7: DELETE admission_project -> historical_cutoffs CASCADE
            # Also exercises the partial unique index: two current rows per
            # (project, year, score_type) must be rejected.
            # =============================================================
            await conn.execute(
                "INSERT INTO universities (id, name) VALUES ($1, $2)",
                s7_uni_id, f"Verify Uni S7 {s7_uni_id}",
            )
            await conn.execute(
                "INSERT INTO faculties (id, university_id, name) VALUES ($1, $2, $3)",
                s7_fac_id, s7_uni_id, "Verify Faculty S7",
            )
            await conn.execute(
                "INSERT INTO majors (id, faculty_id, name) VALUES ($1, $2, $3)",
                s7_maj_id, s7_fac_id, "Verify Major S7",
            )
            await conn.execute(
                "INSERT INTO tcas_rounds (id, major_id, round_number, year) VALUES ($1, $2, $3, $4)",
                s7_round_id, s7_maj_id, 3, 2026,
            )
            await conn.execute(
                "INSERT INTO admission_projects (id, tcas_round_id, project_name) VALUES ($1, $2, $3)",
                s7_project_id, s7_round_id, "Verify Project S7",
            )
            # First current cutoff row for (project, 2025, composite_weighted)
            await conn.execute(
                "INSERT INTO historical_cutoffs (admission_project_id, year, score_type, min_admitted_score) "
                "VALUES ($1, $2, $3, $4)",
                s7_project_id, 2025, "composite_weighted", 72.50,
            )

            # Partial unique index: a second current row for the same key must fail.
            # Wrap in a savepoint — a raised exception inside asyncpg's outer
            # transaction aborts it; the savepoint lets us recover cleanly.
            label_pu = "historical_cutoffs partial unique index (one current per key)"
            violated = False
            try:
                async with conn.transaction():
                    await conn.execute(
                        "INSERT INTO historical_cutoffs (admission_project_id, year, score_type, min_admitted_score) "
                        "VALUES ($1, $2, $3, $4)",
                        s7_project_id, 2025, "composite_weighted", 73.00,
                    )
            except asyncpg.exceptions.UniqueViolationError:
                violated = True
            if violated:
                ok(label_pu)
            else:
                fail(label_pu, "second current row was accepted")
                all_passed = False

            # Supersede the original row (is_current=FALSE) then insert a new current.
            # This must succeed — the partial index only constrains WHERE is_current.
            await conn.execute(
                "UPDATE historical_cutoffs SET is_current = FALSE, effective_to = CURRENT_TIMESTAMP "
                "WHERE admission_project_id = $1 AND year = $2 AND score_type = $3 AND is_current",
                s7_project_id, 2025, "composite_weighted",
            )
            await conn.execute(
                "INSERT INTO historical_cutoffs (admission_project_id, year, score_type, min_admitted_score) "
                "VALUES ($1, $2, $3, $4)",
                s7_project_id, 2025, "composite_weighted", 73.00,
            )
            current_count = await conn.fetchval(
                "SELECT COUNT(*) FROM historical_cutoffs WHERE admission_project_id = $1 "
                "AND year = $2 AND score_type = $3 AND is_current",
                s7_project_id, 2025, "composite_weighted",
            )
            total_count = await conn.fetchval(
                "SELECT COUNT(*) FROM historical_cutoffs WHERE admission_project_id = $1 "
                "AND year = $2 AND score_type = $3",
                s7_project_id, 2025, "composite_weighted",
            )
            label_scd = "historical_cutoffs SCD Type 2 supersede flow"
            if current_count == 1 and total_count == 2:
                ok(label_scd)
            else:
                fail(label_scd, f"expected 1 current / 2 total, got {current_count} / {total_count}")
                all_passed = False

            # Cascade on delete of parent admission_project.
            await conn.execute("DELETE FROM admission_projects WHERE id = $1", s7_project_id)
            remaining = await conn.fetchval(
                "SELECT COUNT(*) FROM historical_cutoffs WHERE admission_project_id = $1",
                s7_project_id,
            )
            label = "admission_projects -> historical_cutoffs CASCADE"
            if remaining == 0:
                ok(label)
            else:
                fail(label, f"{remaining} child rows survived")
                all_passed = False

            # =============================================================
            # Scenario 8: round_type consistency trigger
            # - permissive: NULL round_type allowed
            # - strict: round_type='admission' on round_number=3 passes
            # - strict: round_type='portfolio' on round_number=3 raises
            # =============================================================
            await conn.execute(
                "INSERT INTO universities (id, name) VALUES ($1, $2)",
                s8_uni_id, f"Verify Uni S8 {s8_uni_id}",
            )
            await conn.execute(
                "INSERT INTO faculties (id, university_id, name) VALUES ($1, $2, $3)",
                s8_fac_id, s8_uni_id, "Verify Faculty S8",
            )
            await conn.execute(
                "INSERT INTO majors (id, faculty_id, name) VALUES ($1, $2, $3)",
                s8_maj_id, s8_fac_id, "Verify Major S8",
            )
            await conn.execute(
                "INSERT INTO tcas_rounds (id, major_id, round_number, year) VALUES ($1, $2, $3, $4)",
                s8_round_id, s8_maj_id, 3, 2026,
            )

            # 8a: NULL round_type allowed (permissive).
            label_8a = "round_type trigger: NULL allowed (permissive)"
            try:
                await conn.execute(
                    "INSERT INTO admission_projects (id, tcas_round_id, project_name) "
                    "VALUES ($1, $2, $3)",
                    s8_project_id, s8_round_id, "Verify Project S8 (null type)",
                )
                ok(label_8a)
            except Exception as e:
                fail(label_8a, f"NULL rejected: {e}")
                all_passed = False

            # 8b: matching round_type accepted.
            label_8b = "round_type trigger: matching type (admission on R3) accepted"
            try:
                await conn.execute(
                    "UPDATE admission_projects SET round_type = 'admission' WHERE id = $1",
                    s8_project_id,
                )
                ok(label_8b)
            except Exception as e:
                fail(label_8b, f"matching type rejected: {e}")
                all_passed = False

            # 8c: mismatching round_type rejected. Savepoint — trigger raises.
            label_8c = "round_type trigger: mismatching type (portfolio on R3) rejected"
            raised = False
            try:
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE admission_projects SET round_type = 'portfolio' WHERE id = $1",
                        s8_project_id,
                    )
            except asyncpg.exceptions.RaiseError:
                raised = True
            if raised:
                ok(label_8c)
            else:
                fail(label_8c, "mismatch was accepted")
                all_passed = False

            # 8d: invalid enum value rejected. Savepoint — trigger raises.
            label_8d = "round_type trigger: invalid value rejected"
            raised = False
            try:
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE admission_projects SET round_type = 'bogus' WHERE id = $1",
                        s8_project_id,
                    )
            except asyncpg.exceptions.RaiseError:
                raised = True
            if raised:
                ok(label_8d)
            else:
                fail(label_8d, "invalid value was accepted")
                all_passed = False

        finally:
            # Always roll back — pass or fail, DB goes back to exactly the
            # state it was in before this function ran. No cleanup code needed.
            await tx.rollback()

    return all_passed


# ── Orchestrator ────────────────────────────────────────────────────────────

async def run_checks() -> int:
    """Run all checks in order. Return shell exit code (0 pass, 1 fail)."""
    await init_pool()
    try:
        results = [
            await check_tables_exist(),
            await check_fks_declared(),
            await check_cascades(),
        ]
    finally:
        # Even if a check raises, close the pool cleanly.
        await close_pool()

    print()
    if all(results):
        print("All checks passed.")
        return 0
    else:
        print("One or more checks FAILED.")
        return 1


# ── Entry point ─────────────────────────────────────────────────────────────
# Using `python -m db.verify` from inside /app in the container.
# The guard prevents import-time execution; see the lecture we just did.

if __name__ == "__main__":
    sys.exit(asyncio.run(run_checks()))
