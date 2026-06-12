#!/usr/bin/env python3
"""Seed suburbs table from suburbs.json (Phase 3C).

Usage from agent_service/:
  python scripts/init_db.py          # apply migrations (includes 002_suburbs)
  python scripts/seed_suburbs.py     # load 200 towns into Postgres

Requires DATABASE_URL in .env. suburbs.json must exist (run build_suburbs_dataset.py first).
"""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


def main() -> int:
    from app.config import SUBURBS_JSON_PATH
    from app.db import db_configured
    from app.suburb_store import seed_suburbs_from_json, suburbs_table_count

    if not db_configured():
        print("FAIL: DATABASE_URL is not set in .env", file=sys.stderr)
        return 1
    if not SUBURBS_JSON_PATH.is_file():
        print(
            f"FAIL: missing {SUBURBS_JSON_PATH} — run scripts/build_suburbs_dataset.py",
            file=sys.stderr,
        )
        return 1

    try:
        count = seed_suburbs_from_json()
    except Exception as exc:
        print(f"FAIL: seed failed — {exc}", file=sys.stderr)
        return 1

    total = suburbs_table_count()
    print(f"Seeded {count} suburb rows (suburbs table now has {total} rows).")
    return 0 if total > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
