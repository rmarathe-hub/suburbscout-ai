#!/usr/bin/env python3
"""Phase 1.1 Step 8 verification: quality eval suite."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


async def main() -> None:
    print("=== Phase 1.1 Step 8: quality eval suite ===\n")

    from app.evals.runner import DEFAULT_PROMPTS_PATH, evaluate_case, load_eval_cases
    from app.orchestrator import handle_query

    print("1. Eval prompts file")
    if not DEFAULT_PROMPTS_PATH.exists():
        raise AssertionError(f"Missing {DEFAULT_PROMPTS_PATH}")
    with open(DEFAULT_PROMPTS_PATH, encoding="utf-8") as f:
        meta = json.load(f)
    cases = load_eval_cases(DEFAULT_PROMPTS_PATH)
    print(f"  PASS: loaded {len(cases)} cases from {DEFAULT_PROMPTS_PATH.name}")

    if len(cases) < 75:
        raise AssertionError(f"expected at least 75 cases, got {len(cases)}")

    categories = {c["category"] for c in cases}
    required = {
        "lookup",
        "compare",
        "budget",
        "commute",
        "coastal",
        "semantic",
        "unknown_town",
        "data_limit",
    }
    missing = required - categories
    if missing:
        raise AssertionError(f"missing categories: {sorted(missing)}")
    print(f"  PASS: categories present ({len(categories)} total)")

    print("\n2. Spot-check evaluator + orchestrator (5 cases)")
    spot_ids = [
        "lookup_gardner_commute",
        "compare_acton_framingham",
        "budget_900k_schools",
        "semantic_coastal_feel",
        "lookup_charlton_commute",
    ]
    by_id = {c["id"]: c for c in cases}
    for case_id in spot_ids:
        case = by_id.get(case_id)
        if case is None:
            raise AssertionError(f"missing spot case {case_id}")
        result = await handle_query(case["prompt"], save_searches=False)
        passed, failures = evaluate_case(case, result)
        if not passed:
            raise AssertionError(f"{case_id} failed: {failures}")
        print(f"  PASS: {case_id}")

    print("\n3. Full eval run (property checks)")
    results = []
    for case in cases:
        payload = await handle_query(case["prompt"], save_searches=False)
        passed, failures = evaluate_case(case, payload)
        results.append((case, passed, failures))

    passed_count = sum(1 for _, ok, _ in results if ok)
    rate = passed_count / len(results)
    target = float(meta.get("target_pass_rate", 0.85))
    print(f"  {passed_count}/{len(results)} passed ({rate:.1%}) target>={target:.0%}")

    if rate < target:
        failed = [(c["id"], f) for c, ok, f in results if not ok]
        for case_id, failures in failed[:10]:
            print(f"    FAIL {case_id}: {failures[:2]}")
        raise AssertionError(f"pass rate {rate:.1%} below target {target:.0%}")

    print("\nStep 8 verification: PASSED")
    print("Next: Step 9 — verify_phase1_1_complete.py + README updates")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print(f"  FAIL: {exc}")
        sys.exit(1)
