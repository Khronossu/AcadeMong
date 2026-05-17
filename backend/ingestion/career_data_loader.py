"""Career data loader — normalizes scraped JSON, loads into PostgreSQL + Qdrant.

Pipeline:
  1. Read jobthai_raw.json + jobtopgun_raw.json from data/career/
  2. Deduplicate by normalized title (jobthai takes precedence for salary data)
  3. Upsert industry_groups rows
  4. Upsert career_catalog rows (ON CONFLICT (title) DO UPDATE — idempotent)
  5. Embed (title + overview) via nomic-embed-text → upsert into Qdrant "careers" collection

CLI: python -m ingestion.career_data_loader
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from db.qdrant_client import CAREERS_COLLECTION, get_qdrant_client
from models.ollama_client import embed

load_dotenv()

_DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "career"
_EMBEDDING_MODEL = "nomic-embed-text"
_DENSE_DIM = 768

_OVERVIEW_TEMPLATES: dict[str, str] = {
    "งานไอทีและซอฟต์แวร์": "งานด้านเทคโนโลยีสารสนเทศ การพัฒนาซอฟต์แวร์ และระบบคอมพิวเตอร์",
    "งานวิศวกรรม": "งานวิศวกรรมและการออกแบบระบบในสาขาต่างๆ",
    "งานบัญชีและการเงิน": "งานบัญชี การเงิน และการวิเคราะห์ทางการเงิน",
    "งานการตลาดและโฆษณา": "งานด้านการตลาด โฆษณา และการสร้างแบรนด์",
    "งานการแพทย์และสาธารณสุข": "งานด้านการแพทย์ พยาบาล และสาธารณสุข",
    "งานการศึกษา": "งานด้านการสอนและการศึกษา",
    "งานบริหารและจัดการ": "งานด้านการบริหารจัดการองค์กรและโครงการ",
    "งานออกแบบและสร้างสรรค์": "งานออกแบบกราฟิก UI/UX และงานสร้างสรรค์",
}


def _career_point_id(title: str) -> int:
    raw = title.encode()
    return int(hashlib.sha256(raw).hexdigest()[:16], 16)


def normalize_careers(raw_jobs: list[dict]) -> list[dict]:
    """Deduplicate by normalized title; jobthai salary data takes precedence."""
    seen: dict[str, dict] = {}
    for job in raw_jobs:
        key = job["title"].strip().lower()
        if key not in seen:
            seen[key] = {
                "title": job["title"].strip(),
                "industry_group": job.get("industry_group", ""),
                "avg_salary_thb": job.get("avg_salary_thb"),
                "active_job_openings": job.get("active_job_openings", 0),
            }
        else:
            existing = seen[key]
            existing["active_job_openings"] = (
                existing["active_job_openings"] + job.get("active_job_openings", 0)
            )
            if existing["avg_salary_thb"] is None and job.get("avg_salary_thb"):
                existing["avg_salary_thb"] = job["avg_salary_thb"]
    return list(seen.values())


async def upsert_industry_groups(careers: list[dict]) -> dict[str, str]:
    """Insert unique industry group names; return name→id map."""
    from db.postgres import fetch, execute

    groups = {c["industry_group"] for c in careers if c["industry_group"]}
    group_map: dict[str, str] = {}
    for name in sorted(groups):
        await execute(
            "INSERT INTO industry_groups (name) VALUES ($1) ON CONFLICT (name) DO NOTHING",
            name,
        )
        row = await fetch("SELECT id FROM industry_groups WHERE name = $1", name)
        if row:
            group_map[name] = str(row[0]["id"])
    return group_map


async def upsert_career_catalog(
    careers: list[dict],
    group_map: dict[str, str],
) -> list[dict]:
    """Insert/update career_catalog rows. Returns rows with DB-assigned IDs."""
    from db.postgres import fetch

    rows: list[dict] = []
    for career in careers:
        group_id = group_map.get(career["industry_group"])
        overview = _OVERVIEW_TEMPLATES.get(career["industry_group"], career["title"])
        row = await fetch(
            """
            INSERT INTO career_catalog
              (industry_group_id, title, overview_description,
               avg_salary_thb, active_job_openings)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (title) DO UPDATE SET
              avg_salary_thb      = EXCLUDED.avg_salary_thb,
              active_job_openings = EXCLUDED.active_job_openings,
              last_scraped_at     = NOW()
            RETURNING id, title, overview_description, avg_salary_thb,
                      industry_group_id
            """,
            group_id,
            career["title"],
            overview,
            career.get("avg_salary_thb"),
            career.get("active_job_openings", 0),
        )
        if row:
            rows.append(dict(row[0]))
    return rows


def _init_careers_collection(client: QdrantClient) -> None:
    existing = {c.name for c in client.get_collections().collections}
    if CAREERS_COLLECTION in existing:
        return
    client.create_collection(
        collection_name=CAREERS_COLLECTION,
        vectors_config=VectorParams(size=_DENSE_DIM, distance=Distance.COSINE),
    )


async def embed_and_index_careers(career_rows: list[dict]) -> int:
    """Embed each career's title + overview, upsert into Qdrant careers collection."""
    client = get_qdrant_client()
    _init_careers_collection(client)

    points: list[PointStruct] = []
    for row in career_rows:
        text = f"{row['title']} {row.get('overview_description', '')}"
        vector = await embed(_EMBEDDING_MODEL, text)
        points.append(
            PointStruct(
                id=_career_point_id(row["title"]),
                vector=vector,
                payload={
                    "career_id": str(row["id"]),
                    "title": row["title"],
                    "industry_group_id": str(row.get("industry_group_id", "")),
                    "avg_salary_thb": row.get("avg_salary_thb"),
                },
            )
        )

    if points:
        client.upsert(collection_name=CAREERS_COLLECTION, points=points)
    return len(points)


async def run() -> None:
    from db.postgres import init_pool, close_pool

    await init_pool()

    raw: list[dict] = []
    for fname in ("jobthai_raw.json", "jobtopgun_raw.json"):
        path = _DATA_DIR / fname
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            raw.extend(data)
            print(f"Loaded {len(data)} entries from {fname}", flush=True)
        else:
            print(f"Warning: {fname} not found — skipping", flush=True)

    if not raw:
        print("No career data found. Run the scrapers first.", flush=True)
        return

    careers = normalize_careers(raw)
    print(f"Normalized to {len(careers)} unique career titles", flush=True)

    group_map = await upsert_industry_groups(careers)
    print(f"Upserted {len(group_map)} industry groups", flush=True)

    career_rows = await upsert_career_catalog(careers, group_map)
    print(f"Upserted {len(career_rows)} career_catalog rows", flush=True)

    indexed = await embed_and_index_careers(career_rows)
    print(f"Indexed {indexed} career vectors in Qdrant '{CAREERS_COLLECTION}'", flush=True)

    await close_pool()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run())
