#!/usr/bin/env python3
"""Run Phase 1.1 quality evals against the deterministic orchestrator."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.evals.runner import DEFAULT_PROMPTS_PATH, evaluate_case, load_eval_cases  # noqa: E402
from app.orchestrator import handle_query  # noqa: E402


async def _run_cases(
    cases: list[dict[str, Any]],
    *,
    save_searches: bool = False,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for case in cases:
        payload = await handle_query(case["prompt"], save_searches=save_searches)
        passed, failures = evaluate_case(case, payload)
        results.append({
            "case": case,
            "passed": passed,
            "failures": failures,
            "route_intent": (payload.get("route") or {}).get("intent"),
        })
    return results


def _print_summary(results: list[dict[str, Any]], *, min_pass_rate: float) -> int:
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    rate = passed / total if total else 0.0

    print(f"\n{'=' * 72}")
    print(f"Overall: {passed}/{total} passed ({rate:.1%})  target>={min_pass_rate:.0%}")
    print(f"{'=' * 72}")

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        by_category[row["case"]["category"]].append(row)

    print("\nBy category:")
    for category in sorted(by_category):
        rows = by_category[category]
        cat_pass = sum(1 for r in rows if r["passed"])
        print(f"  {category:18} {cat_pass:3}/{len(rows):3} ({cat_pass / len(rows):.0%})")

    failures = [r for r in results if not r["passed"]]
    if failures:
        print(f"\nFailed cases ({len(failures)}):")
        for row in failures[:25]:
            case = row["case"]
            print(f"  - [{case['category']}] {case['id']}: {case['prompt'][:70]}")
            for reason in row["failures"][:3]:
                print(f"      • {reason}")
        if len(failures) > 25:
            print(f"  ... and {len(failures) - 25} more")

    return 0 if rate >= min_pass_rate else 1


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run SuburbScout Phase 1.1 quality evals.")
    parser.add_argument(
        "--prompts",
        type=Path,
        default=DEFAULT_PROMPTS_PATH,
        help="Path to eval prompts JSON.",
    )
    parser.add_argument(
        "--category",
        action="append",
        help="Run only cases in this category (repeatable).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Run at most N cases (0 = all).",
    )
    parser.add_argument(
        "--min-pass-rate",
        type=float,
        default=0.85,
        help="Exit non-zero if pass rate is below this threshold.",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        help="Write full eval results JSON to this path.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Enable save_search_tool during eval runs.",
    )
    return parser.parse_args(argv)


async def _main_async(args: argparse.Namespace) -> int:
    payload_path = args.prompts
    with open(payload_path, encoding="utf-8") as f:
        meta = json.load(f)
    cases = load_eval_cases(payload_path)

    if args.category:
        allowed = set(args.category)
        cases = [c for c in cases if c.get("category") in allowed]

    if args.limit and args.limit > 0:
        cases = cases[: args.limit]

    target = float(meta.get("target_pass_rate", args.min_pass_rate))
    min_rate = args.min_pass_rate if args.min_pass_rate != 0.85 else target

    print("=== SuburbScout Phase 1.1 Quality Evals ===")
    print(f"Prompts: {payload_path}")
    print(f"Cases: {len(cases)}")
    cats = Counter(c["category"] for c in cases)
    print(f"Categories: {dict(sorted(cats.items()))}")
    print(f"Target pass rate: {min_rate:.0%}")

    results = await _run_cases(cases, save_searches=args.save)

    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "summary": {
                        "total": len(results),
                        "passed": sum(1 for r in results if r["passed"]),
                    },
                    "results": results,
                },
                f,
                indent=2,
            )
        print(f"\nWrote results to {args.json_out}")

    return _print_summary(results, min_pass_rate=min_rate)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    try:
        code = asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    sys.exit(code)


if __name__ == "__main__":
    main()
