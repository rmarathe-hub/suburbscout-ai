#!/usr/bin/env python3
"""Phase 1.2 Step 2: 150-prompt strict validation gate (>=85% required)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
PASS_THRESHOLD = 0.85


def main() -> None:
    print("=== Phase 1.2 Step 2: 150-prompt strict validation ===\n")

    proc = subprocess.run(
        [sys.executable, str(SERVICE_ROOT / "scripts" / "run_150_quality_check.py")],
        cwd=SERVICE_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)

    results_dir = SERVICE_ROOT / "app" / "evals" / "results"
    latest = sorted(results_dir.glob("quality_check_150_*.json"))[-1]
    payload = json.loads(latest.read_text())
    results = payload["results"]
    passed = sum(1 for r in results if r.get("strict_valid") is True)
    rate = passed / len(results)

    print(f"Latest report: {latest.name}")
    print(f"Strict pass rate: {passed}/{len(results)} ({rate:.1%})")
    print(f"Gate: >= {PASS_THRESHOLD:.0%}")

    if rate < PASS_THRESHOLD:
        failed = [r for r in results if r.get("strict_valid") is False]
        print("\nFailed prompts:")
        for row in failed[:10]:
            print(f"  - {row['id']}: {row['prompt'][:70]}")
        raise SystemExit(1)

    print("\nStep 2 verification: PASSED")


if __name__ == "__main__":
    main()
