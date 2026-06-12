#!/usr/bin/env python3
"""Part 2 — verify Docker image builds and responds to /health.

Usage (from agent_service/):
  docker build -t suburbscout-api .
  docker run --rm -d -p 8000:8000 --env-file .env --name suburbscout-api-test suburbscout-api
  python scripts/verify_part2_docker.py
  docker stop suburbscout-api-test

Or pass a custom base URL:
  BASE_URL=http://127.0.0.1:8001 python scripts/verify_part2_docker.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def main() -> int:
    print(f"=== Part 2 Docker verify: GET {BASE}/health ===\n")
    try:
        with urllib.request.urlopen(f"{BASE}/health", timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        print(f"  FAIL: cannot reach {BASE}/health — {exc}")
        print("  Start container: docker run --rm -p 8000:8000 --env-file .env suburbscout-api")
        return 1

    print(json.dumps(data, indent=2))

    required = ("status", "query_agent_configured", "suburbs_dataset_loaded", "database")
    missing = [k for k in required if k not in data]
    if missing:
        print(f"\n  FAIL: missing health fields: {missing}")
        return 1
    if data.get("status") != "ok":
        print("\n  FAIL: status is not ok")
        return 1
    if not data.get("suburbs_dataset_loaded"):
        print("\n  FAIL: suburbs.json not loaded in container")
        return 1

    print("\n=== Part 2 Docker verify: PASSED ===")
    if data.get("database") != "ok":
        print("  WARN: database is not ok — check DATABASE_URL in --env-file .env")
    if not data.get("query_agent_configured"):
        print("  WARN: query agent not configured — check Azure OpenAI env vars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
