"""Run Alembic migrations (Phase 3A).

Usage from agent_service/:
  python scripts/init_db.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    ini = SERVICE_ROOT / "alembic.ini"
    if not ini.is_file():
        print("alembic.ini missing", file=sys.stderr)
        return 1
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=SERVICE_ROOT,
        check=False,
    )
    if result.returncode == 0:
        print("Database migrations applied (alembic upgrade head).")
        print("Next: python scripts/seed_suburbs.py  # Phase 3C suburb reference data")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
