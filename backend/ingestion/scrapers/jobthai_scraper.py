"""JobThai scraper — extracts career data via httpx + BeautifulSoup.

Scrapes job listings by category, aggregates by normalized career title,
and saves the result to data/career/jobthai_raw.json.

CLI: python -m ingestion.scrapers.jobthai_scraper
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

_BASE_URL = "https://www.jobthai.com/th/jobs"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "th-TH,th;q=0.9,en;q=0.8",
}

# JobThai category codes → industry group label
_CATEGORIES: dict[str, str] = {
    "1":  "งานไอทีและซอฟต์แวร์",
    "2":  "งานวิศวกรรม",
    "3":  "งานบัญชีและการเงิน",
    "4":  "งานการตลาดและโฆษณา",
    "5":  "งานการแพทย์และสาธารณสุข",
    "6":  "งานการศึกษา",
    "7":  "งานบริหารและจัดการ",
    "8":  "งานออกแบบและสร้างสรรค์",
}

_OUTPUT_PATH = Path(__file__).resolve().parents[3] / "data" / "career" / "jobthai_raw.json"


def _parse_salary(salary_text: str) -> tuple[int | None, int | None]:
    """Extract (min, max) THB from a salary string like '30,000 - 50,000 บาท'."""
    nums = re.findall(r"[\d,]+", salary_text)
    ints = [int(n.replace(",", "")) for n in nums if n.replace(",", "").isdigit()]
    if len(ints) >= 2:
        return ints[0], ints[1]
    if len(ints) == 1:
        return ints[0], ints[0]
    return None, None


def _normalize_title(title: str) -> str:
    return title.strip().lower()


async def _scrape_page(client: httpx.AsyncClient, category: str, page: int) -> list[dict]:
    params = {"jobtype": category, "page": page}
    try:
        resp = await client.get(_BASE_URL, params=params, headers=_HEADERS, timeout=20)
        resp.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    jobs: list[dict] = []

    for card in soup.select("div.job-list-item, div[class*='job-card'], article[class*='job']"):
        title_el = card.select_one("h2, h3, a[class*='title'], span[class*='title']")
        if not title_el:
            continue
        title = title_el.get_text(strip=True)
        if not title:
            continue

        salary_el = card.select_one("[class*='salary'], [class*='wage']")
        salary_text = salary_el.get_text(strip=True) if salary_el else ""
        sal_min, sal_max = _parse_salary(salary_text)

        jobs.append({
            "title": title,
            "salary_min": sal_min,
            "salary_max": sal_max,
            "salary_text": salary_text,
        })

    return jobs


async def scrape_jobthai(max_pages: int = 5) -> list[dict]:
    """Scrape JobThai by category, aggregate by career title.

    Returns list of dicts: {title, industry_group, avg_salary_thb, active_job_openings}
    """
    raw: list[dict] = []

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for cat_id, industry_group in _CATEGORIES.items():
            for page in range(1, max_pages + 1):
                jobs = await _scrape_page(client, cat_id, page)
                if not jobs:
                    break
                for job in jobs:
                    job["industry_group"] = industry_group
                raw.extend(jobs)
                await asyncio.sleep(0.5)

    # Aggregate by normalized title
    title_data: dict[str, dict] = defaultdict(lambda: {
        "salary_samples": [],
        "openings": 0,
        "industry_group": "",
    })
    for job in raw:
        key = _normalize_title(job["title"])
        entry = title_data[key]
        entry["industry_group"] = entry["industry_group"] or job.get("industry_group", "")
        entry["openings"] += 1
        if job["salary_min"] and job["salary_max"]:
            mid = (job["salary_min"] + job["salary_max"]) // 2
            entry["salary_samples"].append(mid)

    results: list[dict] = []
    for norm_title, data in title_data.items():
        samples = data["salary_samples"]
        avg_salary = int(sum(samples) / len(samples)) if samples else None
        results.append({
            "title": norm_title,
            "industry_group": data["industry_group"],
            "avg_salary_thb": avg_salary,
            "active_job_openings": data["openings"],
            "source": "jobthai",
        })

    return results


if __name__ == "__main__":
    async def main() -> None:
        print("Scraping JobThai...", flush=True)
        careers = await scrape_jobthai(max_pages=3)
        _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _OUTPUT_PATH.write_text(
            json.dumps(careers, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Saved {len(careers)} career entries → {_OUTPUT_PATH}", flush=True)

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
