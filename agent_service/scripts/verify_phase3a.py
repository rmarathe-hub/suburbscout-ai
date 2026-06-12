#!/usr/bin/env python3
"""Phase 3A verification — PostgreSQL persistence layer.

Offline (default):
  - Phase 3A unit tests (API, repository helpers, save_search jsonl fallback)
  - Phase 2 PR gate (offline) — ensures agent brain did not regress

With Postgres running (DATABASE_URL in .env):
  - Integration tests against local docker compose Postgres
  - Optional --live-api smoke through POST /api/query (needs Azure)

Usage:
  docker compose up -d
  python scripts/init_db.py
  python scripts/verify_phase3a.py
  python scripts/verify_phase3a.py --live-api   # + one Azure query + DB trace check
  python scripts/verify_phase3a.py --full       # + run_query_agent_verification --phase2-only
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

PHASE3A_UNITTEST_MODULES = (
    "tests.test_api",
    "tests.test_repositories_offline",
    "tests.test_db_connection",
    "tests.test_save_search_postgres",
    "tests.test_api_query_persists",
    "tests.test_session_followup",
    "tests.test_suburb_store",
)


def _fail(msg: str) -> None:
    print(f"  FAIL: {msg}")
    sys.exit(1)


def _pass(msg: str) -> None:
    print(f"  PASS: {msg}")


def _run(cmd: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or SERVICE_ROOT),
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def check_dependencies() -> None:
    print("1. Dependencies")
    try:
        import alembic  # noqa: F401
        import sqlalchemy  # noqa: F401
    except ImportError as exc:
        _fail(f"pip install -r requirements.txt — {exc}")
    _pass("sqlalchemy + alembic importable")


def check_offline_tests() -> None:
    print("\n2. Phase 3A unit tests (integration cases skip without Postgres)")
    t0 = time.perf_counter()
    code, out = _run([sys.executable, "-m", "unittest", *PHASE3A_UNITTEST_MODULES])
    elapsed = int((time.perf_counter() - t0) * 1000)
    if code != 0:
        print(out[-3000:])
        _fail(f"Phase 3A unit tests failed ({elapsed}ms)")
    _pass(f"Phase 3A unit tests ({elapsed}ms, {len(PHASE3A_UNITTEST_MODULES)} modules)")


def check_postgres_status() -> None:
    print("\n3. Postgres connectivity")
    from app.db import db_available, db_configured

    if not db_configured():
        print("  SKIP: DATABASE_URL not set (optional for offline dev)")
        return
    if not db_available():
        _fail("DATABASE_URL is set but Postgres is unreachable — run: docker compose up -d && python scripts/init_db.py")
    _pass("DATABASE_URL configured and Postgres reachable")


def check_suburbs_table() -> None:
    print("\n3b. Suburbs table (Phase 3C)")
    from app.db import db_available, db_configured
    from app.suburb_store import suburbs_table_count

    if not db_configured() or not db_available():
        print("  SKIP: Postgres not available")
        return
    count = suburbs_table_count()
    if count < 200:
        _fail(
            f"suburbs table has {count} rows (expected 200) — run: python scripts/seed_suburbs.py"
        )
    _pass(f"suburbs table seeded ({count} rows)")


def check_phase2_pr_gate() -> None:
    print("\n4. Phase 2 PR gate (offline)")
    t0 = time.perf_counter()
    code, out = _run([sys.executable, "scripts/verify_phase2_pr_gate.py"])
    elapsed = int((time.perf_counter() - t0) * 1000)
    if code != 0:
        print(out[-2000:])
        _fail(f"Phase 2 PR gate failed ({elapsed}ms)")
    _pass(f"Phase 2 PR gate offline ({elapsed}ms)")


def check_live_api_persistence() -> None:
    print("\n5. Live API + Postgres persistence")
    if os.getenv("SKIP_LIVE_AZURE_CHECKS", "").lower() in ("1", "true", "yes"):
        print("  SKIP: SKIP_LIVE_AZURE_CHECKS")
        return

    from app.db import db_available, db_configured
    from app.query_agent import query_agent_available

    if not db_configured() or not db_available():
        print("  SKIP: Postgres not available")
        return
    if not query_agent_available():
        print("  SKIP: query agent not configured for live API test")
        return

    from fastapi.testclient import TestClient

    from app.api import app
    from app.repositories import SearchRepository

    session_id = f"verify-{uuid.uuid4().hex[:8]}"
    client = TestClient(app)
    resp = client.post(
        "/api/query",
        json={
            "prompt": "What is the commute from Maynard?",
            "session_id": session_id,
        },
    )
    if resp.status_code != 200:
        _fail(f"POST /api/query status {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    rid = data.get("request_id")
    if not rid:
        _fail("missing request_id in API response")

    trace = SearchRepository().get_search_trace(rid)
    if trace is None:
        _fail(f"no Postgres trace for request_id={rid}")

    session = SearchRepository().get_session(session_id)
    if session is None:
        _fail(f"no session row for session_id={session_id}")

    _pass(f"live query persisted (request_id={rid}, session_id={session_id})")
    print(json.dumps({"execution_status": data.get("execution_status"), "request_id": rid}, indent=2))


def check_full_phase2_regression() -> None:
    print("\n6. Full Phase 2 regression (--phase2-only)")
    t0 = time.perf_counter()
    code, out = _run(
        [sys.executable, "scripts/run_query_agent_verification.py", "--phase2-only"]
    )
    elapsed = int((time.perf_counter() - t0) * 1000)
    if code != 0:
        print(out[-4000:])
        _fail(f"phase2-only verification failed ({elapsed}ms)")
    _pass(f"phase2-only verification ({elapsed}ms)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Phase 3A PostgreSQL persistence")
    parser.add_argument(
        "--live-api",
        action="store_true",
        help="Run one live Azure query and confirm Postgres trace",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Also run run_query_agent_verification.py --phase2-only (slow)",
    )
    args = parser.parse_args()

    print("=== Phase 3A verification ===\n")
    check_dependencies()
    check_offline_tests()
    check_postgres_status()
    check_suburbs_table()
    check_phase2_pr_gate()
    if args.live_api:
        check_live_api_persistence()
    else:
        print("\n5. Live API + Postgres persistence")
        print("  SKIP: pass --live-api (needs Azure + DATABASE_URL)")
    if args.full:
        check_full_phase2_regression()
    else:
        print("\n6. Full Phase 2 regression")
        print("  SKIP: pass --full for run_query_agent_verification --phase2-only")

    print("\n=== Phase 3A verification: PASSED ===")
    print("Manual smoke: bash scripts/manual_api_phase3_smoke.sh")
    print("Swagger:      http://127.0.0.1:8000/docs")


if __name__ == "__main__":
    main()
