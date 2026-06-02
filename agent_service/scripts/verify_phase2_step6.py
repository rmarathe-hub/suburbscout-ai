#!/usr/bin/env python3
"""Phase 2 Step 6 — FastAPI gateway verification."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


def _fail(msg: str) -> None:
    print(f"  FAIL: {msg}")
    sys.exit(1)


def _pass(msg: str) -> None:
    print(f"  PASS: {msg}")


def check_imports() -> None:
    print("1. FastAPI dependencies")
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as exc:
        _fail(f"pip install -r requirements.txt — {exc}")
    _pass("fastapi + uvicorn importable")


def check_offline_routes() -> None:
    print("\n2. Offline API routes (TestClient)")
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "tests.test_api", "-v"],
        cwd=str(SERVICE_ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        _fail("tests.test_api failed")
    _pass("tests.test_api")


def check_live_query(*, prompt: str) -> None:
    print("\n3. Live POST /api/query")
    if os.getenv("SKIP_LIVE_AZURE_CHECKS", "").lower() in ("1", "true", "yes"):
        _pass("live query SKIP (SKIP_LIVE_AZURE_CHECKS)")
        return

    from fastapi.testclient import TestClient

    from app.api import app
    from app.query_agent import query_agent_available

    if not query_agent_available():
        _fail("query agent not configured for live API test")

    client = TestClient(app)
    t0 = time.perf_counter()
    resp = client.post("/api/query", json={"prompt": prompt})
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    if resp.status_code != 200:
        _fail(f"status {resp.status_code}: {resp.text[:400]}")
    data = resp.json()
    if data.get("execution_status") not in ("ok", "partial", "blocked", "out_of_scope"):
        _fail(f"unexpected execution_status: {data.get('execution_status')}")
    if not data.get("answer"):
        _fail("empty answer")
    if "maynard" not in data.get("answer", "").lower():
        _fail(f"expected Maynard in answer, got: {data.get('answer', '')[:200]}")
    _pass(f"live query OK ({elapsed_ms}ms, status={data.get('execution_status')})")
    print(json.dumps({k: data[k] for k in ("execution_status", "request_id", "latency_ms") if k in data}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run one live Azure query through POST /api/query",
    )
    parser.add_argument(
        "--prompt",
        default="What is the commute from Maynard?",
    )
    args = parser.parse_args()

    print("=== Phase 2 Step 6: FastAPI gateway ===\n")
    check_imports()
    check_offline_routes()
    if args.live:
        check_live_query(prompt=args.prompt)
    else:
        print("\n3. Live POST /api/query")
        print("  SKIP: pass --live to run one Azure query")

    print("\n=== Phase 2 Step 6 verification: PASSED ===")
    print("Run server: python scripts/run_api.py")
    print("Docs:       http://127.0.0.1:8000/docs")


if __name__ == "__main__":
    main()
