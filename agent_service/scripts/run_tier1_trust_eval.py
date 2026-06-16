#!/usr/bin/env python3
"""Run Tier 1 trust gate eval against query-agent pipeline (Phase 9)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

from eval_query_agent import run_query_agent_prompt  # noqa: E402

DEFAULT = SERVICE_ROOT / "app" / "evals" / "tier1_trust_eval.json"


def _route_intent(payload: dict) -> str | None:
    from app.plan_trust_gates import plan_to_query_route
    from app.query_plan import validate_plan

    plan_raw = payload.get("plan")
    if not plan_raw:
        return None
    try:
        plan = validate_plan(plan_raw)
        query = (payload.get("response") or {}).get("query") or ""
        return plan_to_query_route(query, plan).intent
    except Exception:
        return None


async def run_cases(cases: list[dict]) -> list[dict]:
    rows = []
    for case in cases:
        prompt = case["prompt"]
        payload = await run_query_agent_prompt(prompt, save_searches=False)
        resp = payload.get("response") or {}
        final = resp.get("final_recommendation") or ""
        rows.append({
            **case,
            "route_intent": _route_intent(payload),
            "trust_gate": payload.get("trust_gate"),
            "final_snippet": final[:240],
            "mentions_sharon": "sharon" in final.lower() and case.get("expect_gate"),
        })
    return rows


def score(rows: list[dict]) -> dict:
    passed = 0
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    failures = []
    for row in rows:
        cat = row.get("category", "?")
        by_cat[cat]["total"] += 1
        ok = True
        expect_gate = row.get("expect_gate")
        if row.get("expect_intent"):
            ok = ok and row.get("route_intent") == row["expect_intent"]
        if "expect_gate" in row:
            if row.get("expect_gate") is None:
                ok = ok and row.get("trust_gate") is None
            else:
                expect_gate = row["expect_gate"]
                ok = row.get("trust_gate") == expect_gate
                if ok and expect_gate:
                    if row.get("mentions_sharon") and "commute_destination" in expect_gate:
                        ok = False
        elif expect_gate is not None:
            ok = row.get("trust_gate") == expect_gate
        else:
            ok = row.get("trust_gate") is None
            if row.get("expect_intent"):
                ok = ok and row.get("route_intent") == row["expect_intent"]
            if cat == "compare_ok":
                ok = ok and "not in suburbs.json" not in row.get("final_snippet", "").lower()
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
        "failures": failures,
    }


async def main_async(args: argparse.Namespace) -> None:
    data = json.loads(args.eval.read_text(encoding="utf-8"))
    results = await run_cases(data["cases"])
    summary = score(results)
    print(json.dumps(summary, indent=2))
    if args.out:
        args.out.write_text(json.dumps({"summary": summary, "results": results}, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", type=Path, default=DEFAULT)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
