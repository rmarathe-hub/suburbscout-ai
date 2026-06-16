#!/usr/bin/env python3
"""Phase 8.5 Slice A verification — dynamic commute destination (Phase 9 plan-first)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

ACCEPTANCE = [
    (
        "maynard_cambridge_lookup",
        "What is the commute from Maynard to Cambridge?",
        {
            "plan": {
                "ops": [
                    {
                        "op": "commute_pair",
                        "origin_town": "Maynard",
                        "destination_town": "Cambridge",
                    }
                ]
            },
            "expect_ok": True,
        },
    ),
    (
        "acton_burlington_lookup",
        "What is the commute from Acton to Burlington?",
        {
            "plan": {
                "ops": [
                    {
                        "op": "commute_pair",
                        "origin_town": "Acton",
                        "destination_town": "Burlington",
                    }
                ]
            },
            "expect_ok": True,
        },
    ),
    (
        "cambridge_rank",
        "Find safe towns under 900k within 35 minutes of Cambridge.",
        {
            "plan": {
                "commute_intent": {
                    "commute_destination_town": "Cambridge",
                    "commute_context": "destination_town",
                    "max_commute_minutes": 35,
                },
                "ops": [
                    {
                        "op": "rank",
                        "preferences": {
                            "budget_max": 900000,
                            "safety_priority": "high",
                            "max_commute_minutes": 35,
                            "commute_destination_town": "Cambridge",
                        },
                        "limit": 10,
                    }
                ],
            },
            "expect_ok": True,
            "max_commute_dest": 35,
            "destination": "Cambridge",
        },
    ),
    (
        "waltham_rank",
        "Find towns with good schools within 30 minutes of Waltham.",
        {
            "plan": {
                "commute_intent": {
                    "commute_destination_town": "Waltham",
                    "commute_context": "destination_town",
                    "max_commute_minutes": 30,
                },
                "ops": [
                    {
                        "op": "rank",
                        "preferences": {
                            "school_priority": "high",
                            "max_commute_minutes": 30,
                            "commute_destination_town": "Waltham",
                        },
                        "limit": 10,
                    }
                ],
            },
            "expect_ok": True,
            "max_commute_dest": 30,
            "destination": "Waltham",
        },
    ),
    (
        "boston_default",
        "Find suburbs close to Boston with good schools.",
        {
            "plan": {
                "commute_intent": {"commute_context": "default_boston"},
                "ops": [
                    {
                        "op": "rank",
                        "preferences": {"school_priority": "high"},
                        "limit": 10,
                    }
                ],
            },
            "expect_ok": True,
            "default_dest": True,
        },
    ),
    (
        "hartford_refusal",
        "Commute from Maynard to Hartford.",
        {
            "plan": {
                "commute_intent": {
                    "commute_destination_town": "Hartford",
                    "commute_context": "unsupported",
                },
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "Maynard", "field": "commute"}],
                    }
                ],
            },
            "expect_blocked": True,
        },
    ),
]


async def _run_case(case_id: str, prompt: str, rules: dict) -> tuple[bool, str]:
    from app.commute_intent import resolve_commute_intent
    from app.plan_executor import execute_plan_async
    from app.plan_normalizer import normalize_planned_query
    from app.plan_trust_gates import evaluate_plan_trust_gate
    from app.query_plan import validate_plan

    plan = normalize_planned_query(prompt, validate_plan(rules["plan"]))

    if rules.get("default_dest"):
        resolved = resolve_commute_intent(prompt, plan.commute_intent, plan=plan)
        if not resolved.is_default:
            return False, f"expected default Boston destination, got {resolved.label}"
        execution = await execute_plan_async(plan, validate=False)
        if rules.get("expect_ok") and execution.status.value not in {"ok", "no_rows"}:
            return False, f"rank status={execution.status.value}"
        return True, "default Boston destination"

    if rules.get("expect_blocked"):
        gate = evaluate_plan_trust_gate(prompt, plan)
        if gate and gate.blocks_pipeline:
            return True, gate.gate_type
        return False, "expected trust gate block"

    gate = evaluate_plan_trust_gate(prompt, plan)
    if gate and gate.blocks_pipeline:
        return False, f"unexpected gate {gate.gate_type}"

    execution = await execute_plan_async(plan, validate=False)
    if rules.get("expect_ok") and execution.status.value not in {"ok", "partial", "no_rows"}:
        return False, f"status={execution.status.value}"

    if rules.get("max_commute_dest"):
        for op in execution.ops_results:
            if op.op != "rank":
                continue
            for row in op.data.get("top_matches") or []:
                minutes = (row.get("data") or {}).get("drive_minutes_to_destination")
                if minutes is not None and float(minutes) > rules["max_commute_dest"]:
                    return False, f"{row.get('name')} exceeds commute cap ({minutes})"
    return True, execution.status.value


async def main() -> None:
    print("=== Phase 8.5 Slice A verification ===\n")
    passed = 0
    for case_id, prompt, rules in ACCEPTANCE:
        ok, detail = await _run_case(case_id, prompt, rules)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {case_id}: {detail}")
        if ok:
            passed += 1
    print(f"\n{passed}/{len(ACCEPTANCE)} passed")
    if passed != len(ACCEPTANCE):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
