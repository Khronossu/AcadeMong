"""JobTopGun scraper — extracts career data via Playwright headless Chromium.

JobTopGun is a JS SPA; httpx alone returns a blank shell. Playwright renders
the page fully before extraction. Saves results to data/career/jobtopgun_raw.json.

CLI: python -m ingestion.scrapers.jobtopgun_scraper
     (requires: playwright install chromium)
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from playwright.async_api import async_playwright

_BASE_URL = "https://www.jobtopgun.com/job-search"
_OUTPUT_PATH = Path(__file__).resolve().parents[3] / "data" / "career" / "jobtopgun_raw.json"

# JobTopGun category slugs → industry group label
_CATEGORIES: dict[str, str] = {
    "information-technology": "งานไอทีและซอฟต์แวร์",
    "engineering":            "งานวิศวกรรม",
    "accounting-finance":     "งานบัญชีและการเงิน",
    "marketing":              "งานการตลาดและโฆษณา",
    "medical":                "งานการแพทย์และสาธารณสุข",
    "education":              "งานการศึกษา",
    "management":             "งานบริหารและจัดการ",
    "design":                 "งานออกแบบและสร้างสรรค์",
}


def _parse_salary(text: str) -> int | None:
    nums = re.findall(r"[\d,]+", text)
    ints = [int(n.replace(",", "")) for n in nums if n.replace(",", "").isdigit()]
    if len(ints) >= 2:
        return (ints[0] + ints[1]) // 2
    if len(ints) == 1:
        return ints[0]
    return None


def _normalize_title(title: str) -> str:
    return title.strip().lower()


async def _scrape_category(page, category_slug: str, industry_group: str, max_pages: int) -> list[dict]:
    jobs: list[dict] = []

    for pg in range(1, max_pages + 1):
        url = f"{_BASE_URL}?category={category_slug}&page={pg}"
        try:
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            await page.wait_for_selector(
                "div[class*='job'], article[class*='job'], li[class*='job']",
                timeout=10_000,
            )
        except Exception:
            break

        cards = await page.query_selector_all(
            "div[class*='job-card'], div[class*='job-item'], article[class*='job'], li[class*='job']"
        )
        if not cards:
            break

        for card in cards:
            title_el = await card.query_selector("h2, h3, a[class*='title'], span[class*='position']")
            if not title_el:
                continue
            title = (await title_el.inner_text()).strip()
            if not title:
                continue

            salary_el = await card.query_selector("[class*='salary'], [class*='wage']")
            salary_text = (await salary_el.inner_text()).strip() if salary_el else ""
            salary = _parse_salary(salary_text)

            jobs.append({
                "title": title,
                "salary": salary,
                "industry_group": industry_group,
                "source": "jobtopgun",
            })

        await asyncio.sleep(1)

    return jobs


async def scrape_jobtopgun(max_pages: int = 3) -> list[dict]:
    """Scrape JobTopGun by category, aggregate by career title.

    Returns list of dicts: {title, industry_group, avg_salary_thb, active_job_openings}
    """
    raw: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="th-TH",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        for slug, group in _CATEGORIES.items():
            jobs = await _scrape_category(page, slug, group, max_pages)
            raw.extend(jobs)

        await browser.close()

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
        if job.get("salary"):
            entry["salary_samples"].append(job["salary"])

    results: list[dict] = []
    for norm_title, data in title_data.items():
        samples = data["salary_samples"]
        avg_salary = int(sum(samples) / len(samples)) if samples else None
        results.append({
            "title": norm_title,
            "industry_group": data["industry_group"],
            "avg_salary_thb": avg_salary,
            "active_job_openings": data["openings"],
            "source": "jobtopgun",
        })

    return results


if __name__ == "__main__":
    async def main() -> None:
        print("Scraping JobTopGun (headless Chromium)...", flush=True)
        careers = await scrape_jobtopgun(max_pages=3)
        _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _OUTPUT_PATH.write_text(
            json.dumps(careers, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Saved {len(careers)} career entries → {_OUTPUT_PATH}", flush=True)

    asyncio.run(main())
