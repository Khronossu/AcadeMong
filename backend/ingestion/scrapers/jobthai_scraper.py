"""JobThai scraper — extracts career data via Playwright (headless Chromium).

JobThai is a JS SPA; static HTML contains no job listings. The scraper
intercepts XHR/fetch network requests to capture the underlying API response
directly, which is far more reliable than parsing rendered HTML.

Saves results to data/career/jobthai_raw.json.

CLI: python -m ingestion.scrapers.jobthai_scraper
     (requires: playwright install chromium)
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

from playwright.async_api import Route, async_playwright

_BASE_URL = "https://www.jobthai.com/th/jobs"
_OUTPUT_PATH = Path(__file__).resolve().parents[3] / "data" / "career" / "jobthai_raw.json"

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


def _normalize_title(title: str) -> str:
    return title.strip().lower()


async def _scrape_category_via_api(
    page,
    category_id: str,
    industry_group: str,
    max_pages: int,
) -> list[dict]:
    """Navigate to a category page, capture XHR responses, extract job data."""
    captured: list[dict] = []

    async def handle_response(response):
        url = response.url
        if "api.jobthai.com" in url and response.status == 200:
            try:
                body = await response.json()
                # JobThai API returns jobs in various shapes; try common keys
                jobs_data = (
                    body.get("jobs")
                    or body.get("data")
                    or body.get("result")
                    or (body if isinstance(body, list) else [])
                )
                if isinstance(jobs_data, list):
                    for job in jobs_data:
                        title = (
                            job.get("position_name")
                            or job.get("job_title")
                            or job.get("title")
                            or job.get("name")
                            or ""
                        )
                        if not title:
                            continue
                        salary_min = job.get("salary_min") or job.get("min_salary")
                        salary_max = job.get("salary_max") or job.get("max_salary")
                        avg = None
                        if salary_min and salary_max:
                            avg = (int(salary_min) + int(salary_max)) // 2
                        elif salary_min:
                            avg = int(salary_min)
                        elif salary_max:
                            avg = int(salary_max)
                        captured.append({
                            "title": title.strip(),
                            "avg_salary": avg,
                            "industry_group": industry_group,
                        })
            except Exception:
                pass

    page.on("response", handle_response)

    for pg in range(1, max_pages + 1):
        url = f"{_BASE_URL}?jobtype={category_id}&page={pg}"
        try:
            await page.goto(url, wait_until="networkidle", timeout=25_000)
            await asyncio.sleep(1)
        except Exception:
            break

        if not captured and pg == 1:
            # Fallback: try parsing visible text job titles from page
            try:
                els = await page.query_selector_all(
                    "h2, h3, [class*='position'], [class*='title'], [class*='job-name']"
                )
                for el in els:
                    text = (await el.inner_text()).strip()
                    if text and 3 < len(text) < 100:
                        captured.append({
                            "title": text,
                            "avg_salary": None,
                            "industry_group": industry_group,
                        })
            except Exception:
                pass

    page.remove_listener("response", handle_response)
    return captured


async def scrape_jobthai(max_pages: int = 3) -> list[dict]:
    """Scrape JobThai by category, aggregate by career title."""
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

        for cat_id, group in _CATEGORIES.items():
            jobs = await _scrape_category_via_api(page, cat_id, group, max_pages)
            raw.extend(jobs)
            print(f"  Category {cat_id} ({group}): {len(jobs)} raw entries", flush=True)

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
        if job.get("avg_salary"):
            entry["salary_samples"].append(job["avg_salary"])

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
        print("Scraping JobThai (Playwright + XHR intercept)...", flush=True)
        careers = await scrape_jobthai(max_pages=2)
        _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        _OUTPUT_PATH.write_text(
            json.dumps(careers, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Saved {len(careers)} career entries → {_OUTPUT_PATH}", flush=True)

    asyncio.run(main())
