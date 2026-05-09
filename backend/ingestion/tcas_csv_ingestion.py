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
