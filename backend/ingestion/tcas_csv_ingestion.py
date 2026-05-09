"""TCAS CSV ingestion script.

Loads an academong-data release tarball directory into PostgreSQL.

Usage:
    python -m ingestion.tcas_csv_ingestion --data-dir /path/to/academong-data-v2026.04.21
    python -m ingestion.tcas_csv_ingestion --data-dir ./data/release --dry-run

The script is idempotent: re-running against the same data is safe.
Reference tables (universities, faculties, majors) are upserted by slug.
Transactional tables (tcas_rounds, admission_projects, subject_requirements)
are upserted by their natural composite key.
historical_cutoffs uses SCD Type 2: changed rows close the old record and
insert a new one; unchanged rows are skipped.
"""

import argparse
import asyncio
import csv
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import UUID

import asyncpg

# ── Controlled vocabulary (mirrors DATA_CONTRACT §7) ─────────────────────────
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

VALID_SCORE_TYPES = VALID_SUBJECTS | {"composite_weighted"}


# ── CSV helpers ───────────────────────────────────────────────────────────────

def _parse_decimal(value: str) -> Optional[float]:
    return float(value) if value else None


def _parse_int(value: str) -> Optional[int]:
    return int(value) if value else None


def _parse_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def _read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ── Ingestion class ───────────────────────────────────────────────────────────

class TcasIngestion:
    def __init__(self, conn: asyncpg.Connection, dry_run: bool = False):
        self.conn = conn
        self.dry_run = dry_run
        # slug → UUID caches built as we go
        self._universities: dict[str, UUID] = {}
        self._faculties: dict[tuple, UUID] = {}   # (univ_slug, faculty_slug)
        self._majors: dict[tuple, UUID] = {}       # (univ_slug, faculty_slug, major_slug)
        self._tcas_rounds: dict[tuple, UUID] = {}  # (major_id, round_number, year)
        self._admission_projects: dict[tuple, UUID] = {}  # (round_id, project_slug)
        self.stats = {k: 0 for k in [
            "universities", "faculties", "majors", "tcas_rounds",
            "admission_projects", "subject_requirements",
            "historical_cutoffs_inserted", "historical_cutoffs_closed", "historical_cutoffs_skipped",
            "errors",
        ]}

    async def _exec(self, query: str, *args):
        if self.dry_run:
            return
        await self.conn.execute(query, *args)

    async def _fetchrow(self, query: str, *args):
        return await self.conn.fetchrow(query, *args)

    async def load_universities(self, rows: list[dict]):
        for row in rows:
            slug = row["university_slug"].strip()
            name = row["name"].strip()
            location = row.get("location", "").strip() or None

            existing = await self._fetchrow(
                "SELECT id FROM universities WHERE name = $1", name
            )
            if existing:
                self._universities[slug] = existing["id"]
                await self._exec(
                    "UPDATE universities SET location = COALESCE($1, location) WHERE id = $2",
                    location, existing["id"],
                )
            else:
                if not self.dry_run:
                    row_id = await self.conn.fetchval(
                        "INSERT INTO universities (name, location) VALUES ($1, $2) RETURNING id",
                        name, location,
                    )
                    self._universities[slug] = row_id
                self.stats["universities"] += 1

        print(f"  universities: {self.stats['universities']} inserted/updated")

    async def load_faculties(self, rows: list[dict]):
        for row in rows:
            univ_slug = row["university_slug"].strip()
            fac_slug = row["faculty_slug"].strip()
            name = row["name"].strip()
            key = (univ_slug, fac_slug)

            univ_id = self._universities.get(univ_slug)
            if not univ_id:
                print(f"  ERROR: unknown university_slug '{univ_slug}' for faculty '{name}'", file=sys.stderr)
                self.stats["errors"] += 1
                continue

            existing = await self._fetchrow(
                "SELECT id FROM faculties WHERE university_id = $1 AND name = $2",
                univ_id, name,
            )
            if existing:
                self._faculties[key] = existing["id"]
            else:
                if not self.dry_run:
                    fac_id = await self.conn.fetchval(
                        "INSERT INTO faculties (university_id, name) VALUES ($1, $2) RETURNING id",
                        univ_id, name,
                    )
                    self._faculties[key] = fac_id
                self.stats["faculties"] += 1

        print(f"  faculties: {self.stats['faculties']} inserted/updated")

    async def load_majors(self, rows: list[dict]):
        for row in rows:
            univ_slug = row["university_slug"].strip()
            fac_slug = row["faculty_slug"].strip()
            major_slug = row["major_slug"].strip()
            name = row["name"].strip()
            field = row.get("field", "").strip() or None
            key = (univ_slug, fac_slug, major_slug)

            fac_id = self._faculties.get((univ_slug, fac_slug))
            if not fac_id:
                print(f"  ERROR: unknown faculty '{univ_slug}/{fac_slug}' for major '{name}'", file=sys.stderr)
                self.stats["errors"] += 1
                continue

            existing = await self._fetchrow(
                "SELECT id FROM majors WHERE faculty_id = $1 AND name = $2",
                fac_id, name,
            )
            if existing:
                self._majors[key] = existing["id"]
                await self._exec(
                    "UPDATE majors SET field = COALESCE($1, field) WHERE id = $2",
                    field, existing["id"],
                )
            else:
                if not self.dry_run:
                    major_id = await self.conn.fetchval(
                        "INSERT INTO majors (faculty_id, name, field) VALUES ($1, $2, $3) RETURNING id",
                        fac_id, name, field,
                    )
                    self._majors[key] = major_id
                self.stats["majors"] += 1

        print(f"  majors: {self.stats['majors']} inserted/updated")

    async def load_tcas_rounds(self, rows: list[dict]):
        for row in rows:
            univ_slug = row["university_slug"].strip()
            fac_slug = row["faculty_slug"].strip()
            major_slug = row["major_slug"].strip()
            round_number = int(row["round_number"])
            year = int(row["year"])

            major_id = self._majors.get((univ_slug, fac_slug, major_slug))
            if not major_id:
                print(f"  ERROR: unknown major '{univ_slug}/{fac_slug}/{major_slug}' for tcas_round", file=sys.stderr)
                self.stats["errors"] += 1
                continue

            key = (major_id, round_number, year)
            existing = await self._fetchrow(
                "SELECT id FROM tcas_rounds WHERE major_id = $1 AND round_number = $2 AND year = $3",
                major_id, round_number, year,
            )
            if existing:
                self._tcas_rounds[key] = existing["id"]
            else:
                if not self.dry_run:
                    r_id = await self.conn.fetchval(
                        "INSERT INTO tcas_rounds (major_id, round_number, year) VALUES ($1, $2, $3) RETURNING id",
                        major_id, round_number, year,
                    )
                    self._tcas_rounds[key] = r_id
                self.stats["tcas_rounds"] += 1

        print(f"  tcas_rounds: {self.stats['tcas_rounds']} inserted/updated")

    async def load_admission_projects(self, rows: list[dict]):
        for row in rows:
            univ_slug = row["university_slug"].strip()
            fac_slug = row["faculty_slug"].strip()
            major_slug = row["major_slug"].strip()
            round_number = int(row["round_number"])
            year = int(row["year"])
            project_slug = row["project_slug"].strip()
            project_name = row["project_name"].strip()
            seats = _parse_int(row.get("seats", ""))
            gpax_min = _parse_decimal(row.get("gpax_min", ""))
            accepts_ged = _parse_bool(row.get("accepts_ged", "false"))
            specific_conditions = row.get("specific_conditions", "").strip() or None
            source_url = row.get("source_url", "").strip() or None

            major_id = self._majors.get((univ_slug, fac_slug, major_slug))
            if not major_id:
                print(f"  ERROR: unknown major for admission_project '{project_slug}'", file=sys.stderr)
                self.stats["errors"] += 1
                continue

            round_id = self._tcas_rounds.get((major_id, round_number, year))
            if not round_id:
                print(f"  ERROR: missing tcas_round for admission_project '{project_slug}' ({year} R{round_number})", file=sys.stderr)
                self.stats["errors"] += 1
                continue

            key = (round_id, project_slug)
            existing = await self._fetchrow(
                "SELECT id FROM admission_projects WHERE tcas_round_id = $1 AND project_name = $2",
                round_id, project_name,
            )
            if existing:
                self._admission_projects[key] = existing["id"]
                await self._exec(
                    """UPDATE admission_projects
                       SET seats = $1, gpax_min = $2, accepts_ged = $3,
                           specific_conditions = $4, source_url = $5
                       WHERE id = $6""",
                    seats, gpax_min, accepts_ged, specific_conditions, source_url, existing["id"],
                )
            else:
                if not self.dry_run:
                    ap_id = await self.conn.fetchval(
                        """INSERT INTO admission_projects
                           (tcas_round_id, project_name, seats, gpax_min, accepts_ged, specific_conditions, source_url)
                           VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id""",
                        round_id, project_name, seats, gpax_min, accepts_ged, specific_conditions, source_url,
                    )
                    self._admission_projects[key] = ap_id
                self.stats["admission_projects"] += 1

        print(f"  admission_projects: {self.stats['admission_projects']} inserted/updated")

    async def load_subject_requirements(self, rows: list[dict]):
        for row in rows:
            univ_slug = row["university_slug"].strip()
            fac_slug = row["faculty_slug"].strip()
            major_slug = row["major_slug"].strip()
            round_number = int(row["round_number"])
            year = int(row["year"])
            project_slug = row["project_slug"].strip()
            subject = row["subject"].strip()
            min_score = _parse_decimal(row.get("min_score", ""))
            weight_percent = _parse_decimal(row.get("weight_percent", ""))

            if subject not in VALID_SUBJECTS:
                print(f"  ERROR: unknown subject '{subject}' (not in controlled vocabulary)", file=sys.stderr)
                self.stats["errors"] += 1
                continue

            major_id = self._majors.get((univ_slug, fac_slug, major_slug))
            round_id = self._tcas_rounds.get((major_id, round_number, year)) if major_id else None
            ap_id = self._admission_projects.get((round_id, project_slug)) if round_id else None

            if not ap_id:
                print(f"  ERROR: unknown admission_project '{project_slug}' for subject_requirement '{subject}'", file=sys.stderr)
                self.stats["errors"] += 1
                continue

            existing = await self._fetchrow(
                "SELECT id FROM subject_requirements WHERE admission_project_id = $1 AND subject = $2",
                ap_id, subject,
            )
            if existing:
                await self._exec(
                    "UPDATE subject_requirements SET min_score = $1, weight_percent = $2 WHERE id = $3",
                    min_score, weight_percent, existing["id"],
                )
            else:
                await self._exec(
                    """INSERT INTO subject_requirements (admission_project_id, subject, min_score, weight_percent)
                       VALUES ($1, $2, $3, $4)""",
                    ap_id, subject, min_score, weight_percent,
                )
                self.stats["subject_requirements"] += 1

        print(f"  subject_requirements: {self.stats['subject_requirements']} inserted/updated")
