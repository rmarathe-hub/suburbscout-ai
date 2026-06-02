#!/usr/bin/env python3
"""Run unsupported-field eval (routing + optional full orchestrator)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

DEFAULT = SERVICE_ROOT / "app" / "evals" / "unsupported_field_eval.json"


async def run_routing(cases: list[dict]) -> list[dict]:
    from app.intent_classifier import classify_user_intent

    rows = []
    for case in cases:
        prompt = case["prompt"]
        py = classify_user_intent(prompt)
        rows.append({
            **case,
            "expected_unsupported_field": case.get("unsupported_field", False),
            "python_intent": py.intent,
            "route_intent": py.intent,
            "unsupported_field": bool(py.unsupported_field),
            "requested_field": py.requested_field,
            "requested_field_category": py.requested_field_category,
            "llm_fallback": False,
        })
    return rows


async def run_full(cases: list[dict]) -> list[dict]:
    from run_holdout_150 import run_holdout

    return await run_holdout(cases)


def _score(rows: list[dict], *, full: bool) -> dict:
    passed = 0
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    failures = []
    for row in rows:
        cat = row.get("category", "?")
        by_cat[cat]["total"] += 1
        expect_uf = row.get("expected_unsupported_field", row.get("unsupported_field"))
        actual_uf = row.get("unsupported_field")
        if row.get("category") == "control_supported":
            expect_uf = False
            ok = (
                row.get("route_intent") == row.get("expected_intent", "lookup_single_town")
                and not actual_uf
            )
        elif full:
            ok = row.get("passed") and row.get("route_intent") == "lookup_single_town"
        else:
            ok = (
                row.get("route_intent") == "lookup_single_town"
                and bool(actual_uf) == bool(expect_uf)
            )
        if ok:
            passed += 1
            by_cat[cat]["passed"] += 1
        else:
            failures.append(row)
    return {
        "total": len(rows),
        "passed": passed,
        "pass_rate_pct": round(100 * passed / len(rows), 1) if rows else 0,
        "by_category": dict(by_cat),
        "failures": failures[:20],
    }


async def main_async(args: argparse.Namespace) -> None:
    data = json.loads(args.eval.read_text(encoding="utf-8"))
    cases = data["cases"]
    if args.mode == "full":
        results = await run_full(cases)
        for r in results:
            r["actual_unsupported_field"] = (r.get("route") or {}).get("unsupported_field")
    else:
        results = await run_routing(cases)

    summary = _score(results, full=args.mode == "full")
    print(json.dumps(summary, indent=2))
    if args.out:
        args.out.write_text(json.dumps({"summary": summary, "results": results}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", type=Path, default=DEFAULT)
    parser.add_argument("--mode", choices=("routing", "full"), default="routing")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
