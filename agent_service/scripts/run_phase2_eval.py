#!/usr/bin/env python3
"""Run Phase 2 eval."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

DEFAULT = SERVICE_ROOT / "app" / "evals" / "phase2_eval.json"


async def run_cases(cases: list[dict]) -> list[dict]:
    from app.orchestrator import handle_query
    from app.intent_classifier import classify_user_intent
    from app.trust_gates import evaluate_trust_gate
    from app.hybrid_intent_router import classify_query_hybrid

    rows = []
    for case in cases:
        prompt = case["prompt"]
        py = classify_user_intent(prompt)
        route = await classify_query_hybrid(prompt)
        gate = evaluate_trust_gate(prompt, route)
        payload = await handle_query(prompt, save_searches=False)
        resp = payload["response"]
        comp = resp.get("comparison") or {}
        table = comp.get("comparison_table") or []
        rows.append({
            **case,
            "python_intent": py.intent,
            "route_intent": route.intent,
            "trust_gate": gate.gate_type if gate else payload.get("trust_gate"),
            "table_rows": len(table),
            "final_snippet": (resp.get("final_recommendation") or "")[:300],
            "has_multi_lookup": bool((resp.get("lookup") or {}).get("multi")),
        })
    return rows


def score(rows: list[dict]) -> dict:
    from app.query_patterns import detect_multi_town_lookup_specs

    passed = 0
    failures = []
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    for row in rows:
        cat = row.get("category", "?")
        by_cat[cat]["total"] += 1
        ok = True
        if row.get("expect_intent"):
            ok = row["python_intent"] == row["expect_intent"]
        if row.get("expect_gate"):
            ok = ok and row.get("trust_gate") == row["expect_gate"]
        if row["id"] == "ml_01":
            ok = ok and "maynard" in row["final_snippet"].lower() and "newton" in row["final_snippet"].lower()
        if row.get("min_rows"):
            ok = ok and row.get("table_rows", 0) >= row["min_rows"]
        if row.get("min_specs"):
            specs = detect_multi_town_lookup_specs(row["prompt"])
            ok = ok and len(specs) >= row["min_specs"]
            if row["id"] == "ml_06":
                towns = {s.town.lower() for s in specs}
                ok = ok and {"westborough", "gardner", "concord", "newton", "everett"}.issubset(towns)
        if ok:
            passed += 1
            by_cat[cat]["passed"] += 1
        else:
            failures.append({
                "id": row["id"],
                "prompt": row["prompt"],
                "python_intent": row["python_intent"],
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
