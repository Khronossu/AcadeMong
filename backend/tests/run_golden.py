"""Golden query set runner — Phase 11 gate.

Usage:
    # Pass a Firebase idToken via env var (get from browser DevTools → Network → Authorization header)
    FIREBASE_TOKEN=<token> python -m tests.run_golden

    # Or point at a different API base
    API_BASE=http://localhost:8000 FIREBASE_TOKEN=<token> python -m tests.run_golden

    # Run only a specific category
    FIREBASE_TOKEN=<token> python -m tests.run_golden --category injection

Exit codes:
    0  — all tests passed (or pass rate >= PASS_THRESHOLD)
    1  — pass rate below threshold (blocks CI)

Pass threshold: 95% (configurable via PASS_THRESHOLD env var).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import httpx

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
FIREBASE_TOKEN = os.getenv("FIREBASE_TOKEN", "")
PASS_THRESHOLD = float(os.getenv("PASS_THRESHOLD", "0.95"))
GOLDEN_FILE = Path(__file__).parent / "golden_queries.json"

# ANSI colours
GREEN = "\033[92m"
RED   = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD  = "\033[1m"


def _load_queries(category: Optional[str] = None) -> list[dict]:
    queries = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    if category:
        queries = [q for q in queries if q["category"] == category]
    return queries


def _check(result: dict, expect: dict) -> tuple[bool, str]:
    """Returns (passed, reason_if_failed)."""
    # HTTP status check
    expected_status = expect.get("http_status", 200)
    if result["http_status"] != expected_status:
        return False, f"expected HTTP {expected_status}, got {result['http_status']}"

    if result["http_status"] != 200:
        return True, ""  # non-200 expected — status match is sufficient

    body = result.get("response", "")

    # Must contain at least one of these strings
    must_contain_any = expect.get("response_contains_any", [])
    if must_contain_any:
        if not any(kw.lower() in body.lower() for kw in must_contain_any):
            return False, f"response missing all of: {must_contain_any[:3]}..."

    # Must NOT contain any of these strings
    must_not_contain = expect.get("response_not_contains", [])
    for kw in must_not_contain:
        if kw.lower() in body.lower():
            return False, f"response contains forbidden string: '{kw}'"

    return True, ""


async def _send_message(
    client: httpx.AsyncClient,
    session_id: str,
    content: str,
) -> dict:
    """Send a chat message and return {http_status, response}."""
    try:
        resp = await client.post(
            f"{API_BASE}/api/chat/{session_id}/message",
            json={"content": content},
            timeout=180,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {"http_status": 200, "response": data.get("content", "")}
        return {"http_status": resp.status_code, "response": resp.text}
    except Exception as e:
        return {"http_status": -1, "response": str(e)}


async def _create_session(client: httpx.AsyncClient, mode: str) -> Optional[str]:
    try:
        resp = await client.post(
            f"{API_BASE}/api/chat/session",
            json={"ai_mode": mode},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()["session_id"]
    except Exception:
        pass
    return None


async def run(category: Optional[str] = None) -> tuple[int, int]:
    if not FIREBASE_TOKEN:
        print(f"{RED}ERROR: FIREBASE_TOKEN env var not set.{RESET}")
        print("Get your token from the browser:")
        print("  1. Open http://localhost:3000 and sign in")
        print("  2. Open DevTools → Network → any /api/ request → Headers → Authorization")
        print("  3. Copy the token (after 'Bearer ')")
        print("  4. Run: FIREBASE_TOKEN=<token> python -m tests.run_golden")
        sys.exit(1)

    queries = _load_queries(category)
    if not queries:
        print(f"{YELLOW}No queries found{' for category: ' + category if category else ''}{RESET}")
        return 0, 0

    headers = {
        "Authorization": f"Bearer {FIREBASE_TOKEN}",
        "Content-Type": "application/json",
    }

    passed = 0
    failed = 0
    results = []

    async with httpx.AsyncClient(headers=headers) as client:
        # Pre-create one session per mode to avoid overhead
        sessions: dict[str, str] = {}

        print(f"\n{BOLD}AcadeMong Golden Query Runner — {len(queries)} tests{RESET}")
        print(f"API: {API_BASE}")
        print("─" * 60)

        for i, query in enumerate(queries, 1):
            mode = query["mode"]
            qid = query["id"]
            desc = query["description"]
            content = query["input"]
            expect = query["expect"]

            # Create a fresh session for injection tests (they 400 before session use)
            # Reuse sessions for other categories to speed up the run
            if mode not in sessions or query["category"] == "injection":
                sid = await _create_session(client, mode)
                if not sid:
                    print(f"  {RED}SKIP{RESET} [{qid}] could not create session")
                    failed += 1
                    continue
                if query["category"] != "injection":
                    sessions[mode] = sid
            else:
                sid = sessions[mode]

            t0 = time.monotonic()
            result = await _send_message(client, sid, content)
            latency = round((time.monotonic() - t0) * 1000)

            ok, reason = _check(result, expect)

            status_str = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
            print(f"  {status_str} [{qid}] {desc} ({latency}ms)")

            if not ok:
                print(f"         Reason : {reason}")
                print(f"         Input  : {content[:80]}{'...' if len(content) > 80 else ''}")
                resp_preview = result.get("response", "")[:120]
                print(f"         Response: {resp_preview}{'...' if len(result.get('response','')) > 120 else ''}")

            results.append({
                "id": qid,
                "category": query["category"],
                "passed": ok,
                "latency_ms": latency,
                "reason": reason,
            })

            if ok:
                passed += 1
            else:
                failed += 1

    # Summary
    total = passed + failed
    rate = passed / total if total else 0
    color = GREEN if rate >= PASS_THRESHOLD else RED

    print("\n" + "─" * 60)
    print(f"{BOLD}Results by category:{RESET}")
    cats: dict[str, dict] = {}
    for r in results:
        c = r["category"]
        if c not in cats:
            cats[c] = {"pass": 0, "fail": 0}
        if r["passed"]:
            cats[c]["pass"] += 1
        else:
            cats[c]["fail"] += 1
    for cat, counts in cats.items():
        t = counts["pass"] + counts["fail"]
        pct = counts["pass"] / t * 100
        c = GREEN if pct == 100 else (YELLOW if pct >= 50 else RED)
        print(f"  {c}{cat:<20}{RESET} {counts['pass']}/{t} ({pct:.0f}%)")

    print("─" * 60)
    print(f"{color}{BOLD}Total: {passed}/{total} passed ({rate*100:.1f}%) — threshold {PASS_THRESHOLD*100:.0f}%{RESET}")

    if rate < PASS_THRESHOLD:
        print(f"{RED}GATE FAILED — fix failing tests before Phase 12.{RESET}")
    else:
        print(f"{GREEN}GATE PASSED — ready for Phase 12 deploy.{RESET}")

    return passed, total


def main():
    parser = argparse.ArgumentParser(description="Run AcadeMong golden query set")
    parser.add_argument("--category", help="Run only this category (e.g. injection, eligibility)")
    args = parser.parse_args()

    passed, total = asyncio.run(run(args.category))
    rate = passed / total if total else 0
    sys.exit(0 if rate >= PASS_THRESHOLD else 1)


if __name__ == "__main__":
    main()
