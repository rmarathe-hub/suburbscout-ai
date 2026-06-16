#!/usr/bin/env python3
"""Run Tier 1.5 eval against query-agent pipeline (Phase 9)."""

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

DEFAULT = SERVICE_ROOT / "app" / "evals" / "tier15_eval.json"


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
        final = (resp.get("final_recommendation") or "").lower()
        rows.append({
            **case,
            "route_intent": _route_intent(payload),
            "trust_gate": payload.get("trust_gate"),
            "final_snippet": final[:200],
            "mentions_framingham_dest": "framingham / natick" in final and "cannot rank" in final,
            "mentions_sharon_wrong": "sharon" in final and case["id"] == "typo_01",
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
        if row.get("expect_intent"):
            accepted = row.get("accept_intents") or [row["expect_intent"]]
            ok = row.get("route_intent") in accepted
        expect_gate = row.get("expect_gate")
        if expect_gate is not None:
            ok = ok and row.get("trust_gate") == expect_gate
        elif "expect_gate" in row:
            ok = ok and row.get("trust_gate") is None
        if row["id"] == "excl_dest_01" and row.get("mentions_framingham_dest"):
            ok = False
        if row.get("mentions_sharon_wrong"):
            ok = False
        if row["id"] == "scope_01" and "included" not in row.get("final_snippet", ""):
            ok = False
        if row["id"] == "typo_01" and row.get("route_intent") == "recommend_structured":
            ok = False
        if ok:
            passed += 1
            by_cat[cat]["passed"] += 1
        else:
            failures.append({k: row[k] for k in row if k in (
                "id", "category", "prompt", "route_intent",
                "trust_gate", "expect_intent", "expect_gate", "final_snippet",
            )})
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
