#!/usr/bin/env python3
"""Run Tier 1.5 eval (routing + trust gates + key probes)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

DEFAULT = SERVICE_ROOT / "app" / "evals" / "tier15_eval.json"


async def run_cases(cases: list[dict]) -> list[dict]:
    from app.hybrid_intent_router import classify_query_hybrid
    from app.intent_classifier import classify_user_intent
    from app.orchestrator import handle_query
    from app.trust_gates import evaluate_trust_gate

    rows = []
    for case in cases:
        prompt = case["prompt"]
        py = classify_user_intent(prompt)
        route = await classify_query_hybrid(prompt)
        gate = evaluate_trust_gate(prompt, route)
        payload = await handle_query(prompt, save_searches=False)
        resp = payload["response"]
        final = (resp.get("final_recommendation") or "").lower()
        rows.append({
            **case,
            "python_intent": py.intent,
            "route_intent": route.intent,
            "trust_gate": gate.gate_type if gate else payload.get("trust_gate"),
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
            ok = row.get("python_intent") in accepted
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
                "id", "category", "prompt", "python_intent", "route_intent",
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
