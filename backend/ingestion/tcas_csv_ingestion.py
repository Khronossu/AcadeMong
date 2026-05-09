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
