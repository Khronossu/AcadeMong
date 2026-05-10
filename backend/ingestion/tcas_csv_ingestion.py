"""TCAS CSV ingestion script.

Loads an academong-data release directory into PostgreSQL.

Usage:
    python -m ingestion.tcas_csv_ingestion --data-dir /path/to/academong-data-v2026-05-09
    python -m ingestion.tcas_csv_ingestion --data-dir ./data/tcas_csvs --dry-run

The script is idempotent: re-running against the same data is safe.
"""

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

import asyncpg

# ── Vocabulary maps ───────────────────────────────────────────────────────────

ROUND_TYPE_MAP = {
    "portfolio": 1,
    "quota":     2,
    "admission": 3,
    "direct":    4,
}

# Maps raw subject codes from the data release → system vocabulary (ProfileForm subjects).
# Codes not in this map are silently skipped during subject_requirements ingestion.
SUBJECT_MAP: dict[str, str] = {
    # A-Level numeric codes
    "A_LV_61": "A_LEVEL_MATH1",
    "A_LV_62": "A_LEVEL_MATH2",
    "A_LV_63": "A_LEVEL_GENERAL_SCIENCE",
    "A_LV_64": "A_LEVEL_PHYSICS",
    "A_LV_65": "A_LEVEL_CHEMISTRY",
    "A_LV_66": "A_LEVEL_BIOLOGY",
    "A_LV_70": "A_LEVEL_THAI",
    "A_LV_81": "A_LEVEL_SOCIAL_STUDIES",
    "A_LV_82": "A_LEVEL_ENGLISH",
    # Foreign language A-Level (not in profile form — omitted)
    # TGAT / TPAT — pass through; sub-tests collapse to parent
    "TGAT":   "TGAT",
    "TGAT1":  "TGAT1",
    "TGAT2":  "TGAT2",
    "TGAT3":  "TGAT3",
    "TPAT1":  "TPAT1",
    "TPAT2":  "TPAT2",
    "TPAT21": "TPAT2",
    "TPAT22": "TPAT2",
    "TPAT3":  "TPAT3",
    "TPAT4":  "TPAT4",
    "TPAT5":  "TPAT5",
}

VALID_SUBJECTS = set(SUBJECT_MAP.values())


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _str(row: dict, key: str) -> str:
    return (row.get(key) or "").strip()


def _int(row: dict, key: str) -> Optional[int]:
    v = _str(row, key)
    try:
        return int(v) if v else None
    except ValueError:
        return None


def _float(row: dict, key: str) -> Optional[float]:
    v = _str(row, key)
    try:
        return float(v) if v else None
    except ValueError:
        return None


def _bool_flag(row: dict, key: str) -> bool:
    """Interpret "1" = True, "2"/"" = False (MYTCAS convention)."""
    return _str(row, key) == "1"


# ── Ingestion class ───────────────────────────────────────────────────────────

class TcasIngestion:
    def __init__(self, conn: asyncpg.Connection, dry_run: bool = False):
        self.conn = conn
        self.dry_run = dry_run
        # Lookup caches built during each pass
        self._universities: dict[str, UUID] = {}              # university_slug → id
        self._faculties: dict[tuple, UUID] = {}               # (univ_slug, faculty_id_str) → id
        self._majors: dict[str, UUID] = {}                    # program_id → id
        self._tcas_rounds: dict[tuple, UUID] = {}             # (major_uuid, round_number, year) → id
        self._admission_projects: dict[tuple, UUID] = {}      # (program_id, project_id) → id
        # program_id → list of (year, ap_uuid) for historical cutoffs lookup
        self._program_ap_by_year: dict[str, list[tuple]] = {}
        self.stats = {k: 0 for k in [
            "universities", "faculties", "majors", "tcas_rounds",
            "admission_projects", "subject_requirements_inserted", "subject_requirements_skipped",
            "historical_cutoffs_inserted", "historical_cutoffs_closed", "historical_cutoffs_skipped",
            "errors",
        ]}

    async def _exec(self, query: str, *args):
        if not self.dry_run:
            await self.conn.execute(query, *args)

    async def _fetchval(self, query: str, *args):
        if self.dry_run:
            return None
        return await self.conn.fetchval(query, *args)

    async def _fetchrow(self, query: str, *args):
        return await self.conn.fetchrow(query, *args)

    # ── Pass 1: universities ──────────────────────────────────────────────────

    async def load_universities(self, rows: list[dict]):
        for row in rows:
            slug = _str(row, "university_slug")
            name = _str(row, "university_name_th")
            if not slug or not name:
                continue

            existing = await self._fetchrow(
                "SELECT id FROM universities WHERE name = $1", name
            )
            if existing:
                self._universities[slug] = existing["id"]
            else:
                uid = await self._fetchval(
                    "INSERT INTO universities (name) VALUES ($1) RETURNING id", name
                )
                if uid:
                    self._universities[slug] = uid
                self.stats["universities"] += 1

        print(f"  universities: {self.stats['universities']} inserted, "
              f"{len(self._universities)} total cached")

    # ── Pass 2: faculties ─────────────────────────────────────────────────────

    async def load_faculties(self, rows: list[dict]):
        for row in rows:
            univ_slug = _str(row, "university_slug")
            fac_id_str = _str(row, "faculty_id")
            name = _str(row, "faculty_name_th")
            if not univ_slug or not fac_id_str or not name:
                continue

            univ_id = self._universities.get(univ_slug)
            if not univ_id:
                print(f"  ERROR: unknown university_slug '{univ_slug}' for faculty '{name}'",
                      file=sys.stderr)
                self.stats["errors"] += 1
                continue

            key = (univ_slug, fac_id_str)
            existing = await self._fetchrow(
                "SELECT id FROM faculties WHERE university_id = $1 AND name = $2",
                univ_id, name,
            )
            if existing:
                self._faculties[key] = existing["id"]
            else:
                fid = await self._fetchval(
                    "INSERT INTO faculties (university_id, name) VALUES ($1, $2) RETURNING id",
                    univ_id, name,
                )
                if fid:
                    self._faculties[key] = fid
                self.stats["faculties"] += 1

        print(f"  faculties: {self.stats['faculties']} inserted, "
              f"{len(self._faculties)} total cached")

    # ── Pass 3: majors ────────────────────────────────────────────────────────

    async def load_majors(self, rows: list[dict]):
        for row in rows:
            program_id = _str(row, "program_id")
            univ_slug  = _str(row, "university_slug")
            fac_id_str = _str(row, "faculty_id")
            name       = _str(row, "program_name_th")
            field      = _str(row, "field_name_th") or None
            if not program_id or not name:
                continue

            fac_uuid = self._faculties.get((univ_slug, fac_id_str))
            if not fac_uuid:
                print(f"  ERROR: unknown faculty ({univ_slug}, {fac_id_str}) for major '{name}'",
                      file=sys.stderr)
                self.stats["errors"] += 1
                continue

            existing = await self._fetchrow(
                "SELECT id FROM majors WHERE faculty_id = $1 AND name = $2",
                fac_uuid, name,
            )
            if existing:
                self._majors[program_id] = existing["id"]
                await self._exec(
                    "UPDATE majors SET field = COALESCE($1, field) WHERE id = $2",
                    field, existing["id"],
                )
            else:
                mid = await self._fetchval(
                    "INSERT INTO majors (faculty_id, name, field) VALUES ($1, $2, $3) RETURNING id",
                    fac_uuid, name, field,
                )
                if mid:
                    self._majors[program_id] = mid
                self.stats["majors"] += 1

        print(f"  majors: {self.stats['majors']} inserted, "
              f"{len(self._majors)} total cached")

    # ── Pass 4: admission_projects (creates tcas_rounds inline) ──────────────

    async def load_admission_projects(self, rows: list[dict]):
        for row in rows:
            program_id   = _str(row, "program_id")
            project_id   = _str(row, "project_id")
            project_name = _str(row, "project_name_th") or f"({_str(row, 'round_type')} {_str(row, 'year')})"
            round_type   = _str(row, "round_type")
            year         = _int(row, "year")
            seats        = _int(row, "receive_student_number")
            gpax_min     = _float(row, "min_gpax")
            source_url   = _str(row, "link") or None

            if not program_id or not project_id or not year or not round_type:
                continue

            round_number = ROUND_TYPE_MAP.get(round_type)
            if round_number is None:
                print(f"  WARN: unknown round_type '{round_type}' for project '{project_id}' — skipping",
                      file=sys.stderr)
                self.stats["errors"] += 1
                continue

            major_uuid = self._majors.get(program_id)
            if not major_uuid:
                self.stats["errors"] += 1
                continue

            # Upsert tcas_round for this (major, round_number, year)
            round_key = (major_uuid, round_number, year)
            round_uuid = self._tcas_rounds.get(round_key)
            if not round_uuid:
                existing_round = await self._fetchrow(
                    "SELECT id FROM tcas_rounds WHERE major_id = $1 AND round_number = $2 AND year = $3",
                    major_uuid, round_number, year,
                )
                if existing_round:
                    round_uuid = existing_round["id"]
                else:
                    round_uuid = await self._fetchval(
                        "INSERT INTO tcas_rounds (major_id, round_number, year) VALUES ($1, $2, $3) RETURNING id",
                        major_uuid, round_number, year,
                    )
                    self.stats["tcas_rounds"] += 1
                if round_uuid:
                    self._tcas_rounds[round_key] = round_uuid

            if not round_uuid:
                continue

            # Build round_metadata from flags
            round_metadata = {
                "only_formal":        _bool_flag(row, "only_formal"),
                "only_international": _bool_flag(row, "only_international"),
                "only_vocational":    _bool_flag(row, "only_vocational"),
            }

            ap_key = (program_id, project_id)
            existing_ap = await self._fetchrow(
                "SELECT id FROM admission_projects WHERE tcas_round_id = $1 AND project_name = $2",
                round_uuid, project_name,
            )
            if existing_ap:
                ap_uuid = existing_ap["id"]
                await self._exec(
                    """UPDATE admission_projects
                       SET seats = $1, gpax_min = $2, source_url = $3,
                           round_type = $4, round_metadata = $5
                       WHERE id = $6""",
                    seats, gpax_min, source_url,
                    round_type, json.dumps(round_metadata), ap_uuid,
                )
            else:
                ap_uuid = await self._fetchval(
                    """INSERT INTO admission_projects
                       (tcas_round_id, project_name, seats, gpax_min, source_url,
                        round_type, round_metadata)
                       VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                    round_uuid, project_name, seats, gpax_min, source_url,
                    round_type, json.dumps(round_metadata),
                )
                self.stats["admission_projects"] += 1

            if ap_uuid:
                self._admission_projects[ap_key] = ap_uuid
                # Track for historical cutoff lookup: program_id → [(year, ap_uuid)]
                self._program_ap_by_year.setdefault(program_id, []).append((year, ap_uuid))

        print(f"  tcas_rounds: {self.stats['tcas_rounds']} inserted")
        print(f"  admission_projects: {self.stats['admission_projects']} inserted")

    # ── Pass 5: subject_requirements ─────────────────────────────────────────

    async def load_subject_requirements(self, rows: list[dict]):
        for row in rows:
            program_id    = _str(row, "program_id")
            project_id    = _str(row, "project_id")
            raw_subject   = _str(row, "subject")
            weight        = _float(row, "weight_percent")

            mapped = SUBJECT_MAP.get(raw_subject)
            if not mapped:
                self.stats["subject_requirements_skipped"] += 1
                continue

            ap_uuid = self._admission_projects.get((program_id, project_id))
            if not ap_uuid:
                self.stats["errors"] += 1
                continue

            existing = await self._fetchrow(
                "SELECT id FROM subject_requirements WHERE admission_project_id = $1 AND subject = $2",
                ap_uuid, mapped,
            )
            if existing:
                await self._exec(
                    "UPDATE subject_requirements SET weight_percent = $1 WHERE id = $2",
                    weight, existing["id"],
                )
            else:
                await self._exec(
                    """INSERT INTO subject_requirements (admission_project_id, subject, weight_percent)
                       VALUES ($1, $2, $3)""",
                    ap_uuid, mapped, weight,
                )
                self.stats["subject_requirements_inserted"] += 1

        print(f"  subject_requirements: {self.stats['subject_requirements_inserted']} inserted, "
              f"{self.stats['subject_requirements_skipped']} skipped (unmapped subject code)")

    # ── Pass 6: historical_cutoffs ────────────────────────────────────────────

    async def load_historical_cutoffs(self, rows: list[dict]):
        """SCD Type 2 — links to the first admission_project found for (program_id, year)."""
        now = datetime.now(timezone.utc)

        for row in rows:
            program_id = _str(row, "program_id")
            year       = _int(row, "tcas_year")
            min_score  = _float(row, "min_score")
            max_score  = _float(row, "max_score")
            applicants = _int(row, "applicants")
            accepted   = _int(row, "accepted")
            seats      = _int(row, "seats")

            if not program_id or not year:
                continue

            # Find the first admission_project for this program+year
            ap_entries = [
                ap_uuid for (y, ap_uuid) in self._program_ap_by_year.get(program_id, [])
                if y == year
            ]
            if not ap_entries:
                self.stats["historical_cutoffs_skipped"] += 1
                continue

            ap_uuid = ap_entries[0]
            score_type = "composite_weighted"

            current = await self._fetchrow(
                """SELECT id, min_admitted_score, max_admitted_score, applicants_count, accepted_count
                   FROM historical_cutoffs
                   WHERE admission_project_id = $1 AND year = $2 AND score_type = $3
                     AND effective_to IS NULL""",
                ap_uuid, year, score_type,
            )

            if current:
                changed = (
                    current["min_admitted_score"] != min_score
                    or current["max_admitted_score"] != max_score
                    or current["applicants_count"] != applicants
                    or current["accepted_count"] != accepted
                )
                if not changed:
                    self.stats["historical_cutoffs_skipped"] += 1
                    continue
                await self._exec(
                    "UPDATE historical_cutoffs SET effective_to = $1 WHERE id = $2",
                    now, current["id"],
                )
                self.stats["historical_cutoffs_closed"] += 1

            await self._exec(
                """INSERT INTO historical_cutoffs
                   (admission_project_id, year, score_type,
                    min_admitted_score, max_admitted_score,
                    applicants_count, accepted_count,
                    source_url, effective_from)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)""",
                ap_uuid, year, score_type,
                min_score, max_score,
                applicants, accepted,
                "", now,
            )
            self.stats["historical_cutoffs_inserted"] += 1

        print(f"  historical_cutoffs: {self.stats['historical_cutoffs_inserted']} inserted, "
              f"{self.stats['historical_cutoffs_closed']} versions closed, "
              f"{self.stats['historical_cutoffs_skipped']} skipped")


# ── Entry point ───────────────────────────────────────────────────────────────

async def run(data_dir: Path, dry_run: bool):
    if not data_dir.exists():
        print(f"ERROR: data directory not found: {data_dir}", file=sys.stderr)
        sys.exit(1)

    required = [
        "universities.csv", "faculties.csv", "majors.csv",
        "admission_projects.csv", "subject_requirements.csv",
    ]
    missing = [f for f in required if not (data_dir / f).exists()]
    if missing:
        print(f"ERROR: missing required CSV files in {data_dir}: {missing}", file=sys.stderr)
        sys.exit(1)

    conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        database=os.getenv("POSTGRES_DB", "tcas_advisor"),
        user=os.getenv("POSTGRES_USER", "admin"),
        password=os.getenv("POSTGRES_PASSWORD", "password"),
    )

    try:
        ing = TcasIngestion(conn, dry_run=dry_run)

        print("Pass 1 — universities...")
        await ing.load_universities(_read_csv(data_dir / "universities.csv"))

        print("Pass 2 — faculties...")
        await ing.load_faculties(_read_csv(data_dir / "faculties.csv"))

        print("Pass 3 — majors...")
        await ing.load_majors(_read_csv(data_dir / "majors.csv"))

        print("Pass 4 — admission_projects (creates tcas_rounds inline)...")
        await ing.load_admission_projects(_read_csv(data_dir / "admission_projects.csv"))

        print("Pass 5 — subject_requirements...")
        await ing.load_subject_requirements(_read_csv(data_dir / "subject_requirements.csv"))

        cutoffs_path = data_dir / "historical_cutoffs.csv"
        if cutoffs_path.exists():
            print("Pass 6 — historical_cutoffs...")
            await ing.load_historical_cutoffs(_read_csv(cutoffs_path))
        else:
            print("Pass 6 — historical_cutoffs.csv not found, skipping")

        total_errors = ing.stats["errors"]
        print(f"\n{'Dry run complete' if dry_run else 'Done'}. "
              f"Errors: {total_errors}")
        if total_errors:
            print(f"WARNING: {total_errors} rows skipped due to errors — check stderr",
                  file=sys.stderr)
            sys.exit(1)

    finally:
        await conn.close()


def main():
    parser = argparse.ArgumentParser(description="Load TCAS release data into PostgreSQL")
    parser.add_argument(
        "--data-dir", required=True,
        help="Path to extracted academong-data release directory (contains universities.csv etc.)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without writing to DB")
    args = parser.parse_args()
    asyncio.run(run(Path(args.data_dir), dry_run=args.dry_run))


if __name__ == "__main__":
    main()
