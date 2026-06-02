#!/usr/bin/env python3
"""Run golden plan executor regression (Phase 3)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT / "tests"))

from golden_plan_assertions import (  # noqa: E402
    assert_golden_case,
    load_manifest,
    run_golden_case,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run golden plan executor tests.")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args()

    skip_semantic = os.getenv("SKIP_SEMANTIC_GOLDEN", "").lower() in ("1", "true", "yes")
    manifest = load_manifest()
    rows = []
    passed = 0
    skipped = 0

    for case in manifest.get("cases") or []:
        if case.get("requires_live_embeddings") and skip_semantic:
            skipped += 1
            rows.append({**case, "skipped": True, "ok": True})
            continue
        result = run_golden_case(case)
        failures = assert_golden_case(case, result)
        ok = not failures
        if ok:
            passed += 1
        rows.append({
            "id": case["id"],
            "source": case.get("source"),
            "ok": ok,
            "failures": failures,
            "status": result.status.value if result else "validation_rejected",
        })

    total = len(rows) - skipped
    report = {
        "passed": passed,
        "total": total,
        "skipped": skipped,
        "failures": [r for r in rows if not r.get("ok") and not r.get("skipped")],
    }

    if args.json:
        print(json.dumps({"rows": rows, "summary": report}, indent=2))
    else:
        print(f"Golden plans: {passed}/{total} passed ({skipped} skipped)")
        for row in rows:
            if row.get("skipped"):
                print(f"  SKIP {row['id']}")
            elif row.get("ok"):
                print(f"  PASS {row['id']}")
            else:
                print(f"  FAIL {row['id']}: {row.get('failures')}")

    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
