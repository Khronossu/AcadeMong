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
