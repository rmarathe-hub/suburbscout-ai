#!/usr/bin/env python3
"""Run Phase 2 eval against the live query-agent pipeline (Phase 9)."""

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

from eval_query_agent import comparison_row_count, plan_primary_op, run_query_agent_prompt  # noqa: E402

DEFAULT = SERVICE_ROOT / "app" / "evals" / "phase2_eval.json"


def _plan_route_intent(payload: dict) -> str | None:
    from app.plan_trust_gates import plan_to_query_route
    from app.query_plan import validate_plan

    plan_raw = payload.get("plan")
    if not plan_raw:
        return None
    try:
        plan = validate_plan(plan_raw)
        return plan_to_query_route(payload.get("response", {}).get("query") or "", plan).intent
    except Exception:
        return None


async def run_cases(cases: list[dict]) -> list[dict]:
    from app.plan_trust_gates import evaluate_plan_trust_gate
    from app.query_plan import validate_plan

    rows = []
    for case in cases:
        prompt = case["prompt"]
        payload = await run_query_agent_prompt(prompt, save_searches=False)
        resp = payload.get("response") or {}
        plan_raw = payload.get("plan")
        plan = validate_plan(plan_raw) if plan_raw else None
        gate = evaluate_plan_trust_gate(prompt, plan) if plan else None
        rows.append({
            **case,
            "plan_op": plan_primary_op(plan_raw),
            "route_intent": _plan_route_intent(payload),
            "trust_gate": gate.gate_type if gate else payload.get("trust_gate"),
            "table_rows": comparison_row_count(payload),
            "final_snippet": (resp.get("final_recommendation") or "")[:300],
            "has_multi_lookup": bool((resp.get("lookup") or {}).get("multi")),
            "execution_status": payload.get("execution_status"),
        })
    return rows


def score(rows: list[dict]) -> dict:
    passed = 0
    failures = []
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    for row in rows:
        cat = row.get("category", "?")
        by_cat[cat]["total"] += 1
        ok = True
        if row.get("expect_intent"):
            ok = row.get("route_intent") == row["expect_intent"]
        if row.get("expect_gate"):
            ok = ok and row.get("trust_gate") == row["expect_gate"]
        if row["id"] == "ml_01":
            ok = ok and "maynard" in row["final_snippet"].lower() and "newton" in row["final_snippet"].lower()
        if row.get("min_rows"):
            ok = ok and row.get("table_rows", 0) >= row["min_rows"]
        if row.get("min_specs"):
            lookup = (row.get("has_multi_lookup") and row.get("table_rows", 0) >= 0)
            ok = ok and lookup
        if ok:
            passed += 1
            by_cat[cat]["passed"] += 1
        else:
            failures.append({
                "id": row["id"],
                "prompt": row["prompt"],
                "route_intent": row.get("route_intent"),
                "expect_intent": row.get("expect_intent"),
                "trust_gate": row.get("trust_gate"),
                "table_rows": row.get("table_rows"),
                "final_snippet": row.get("final_snippet"),
            })
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
    print(json.dumps(score(results), indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval", type=Path, default=DEFAULT)
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
