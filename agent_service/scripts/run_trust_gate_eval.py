#!/usr/bin/env python3
"""Layer 3 — trust-gate eval: blocked before execution, no answer LLM on refusal."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

DEFAULT_EVAL = SERVICE_ROOT / "app" / "evals" / "trust_gate_plan_eval.json"
RESULTS_DIR = SERVICE_ROOT / "app" / "evals" / "results"


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("cases") or []


def _load_plan(case: dict[str, Any]) -> dict[str, Any]:
    if case.get("plan"):
        return case["plan"]
    rel = case.get("plan_file")
    if rel:
        return json.loads((SERVICE_ROOT / rel).read_text(encoding="utf-8"))
    raise ValueError(f"case {case.get('id')} missing plan")


async def _run_gate_only(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.plan_trust_gates import evaluate_plan_trust_gate
    from app.query_plan import validate_plan

    rows: list[dict[str, Any]] = []
    for case in cases:
        prompt = case["prompt"]
        plan = validate_plan(_load_plan(case))
        gate = evaluate_plan_trust_gate(prompt, plan)
        actual_gate = gate.gate_type if gate else None
        expect_gate = case.get("expect_gate")
        passed = actual_gate == expect_gate
        if case.get("expect_blocks") and not (gate and gate.blocks_pipeline):
            passed = False
        rows.append(
            {
                **case,
                "actual_gate": actual_gate,
                "blocks": bool(gate and gate.blocks_pipeline),
                "passed": passed,
                "failure_reason": None
                if passed
                else f"gate expected {expect_gate!r}, got {actual_gate!r}",
            }
        )
    return rows


async def _run_full_agent(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from unittest.mock import patch

    from app.evals.layered_eval_checks import check_answer_llm_skipped
    from app.query_agent import handle_query_v2, query_agent_available
    from app.query_plan import validate_plan

    if not query_agent_available():
        raise SystemExit("Query agent not available.")

    rows: list[dict[str, Any]] = []
    for case in cases:
        prompt = case["prompt"]
        plan = validate_plan(_load_plan(case))
        with patch("app.query_agent.query_agent_available", return_value=True):
            with patch("app.query_agent.plan_query_with_llm", return_value=plan):
                payload = await handle_query_v2(prompt, save_searches=False)

        expect_blocks = case.get("expect_blocks", True)
        expect_status = case.get("expect_execution_status")
        if expect_status is None:
            expect_status = "blocked" if expect_blocks else "ok"
        expect_gate = case.get("expect_gate")
        status_ok = payload.get("execution_status") == expect_status
        gate_ok = payload.get("trust_gate") == expect_gate
        llm_ok, llm_err = check_answer_llm_skipped(payload)
        passed = status_ok and gate_ok and llm_ok
        rows.append(
            {
                **case,
                "execution_status": payload.get("execution_status"),
                "trust_gate": payload.get("trust_gate"),
                "used_answer_llm": payload.get("used_answer_llm"),
                "passed": passed,
                "failure_reason": None
                if passed
                else "; ".join(
                    x
                    for x in [
                        None if status_ok else f"status {payload.get('execution_status')}",
                        None if gate_ok else f"gate {payload.get('trust_gate')}",
                        llm_err,
                    ]
                    if x
                ),
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Trust-gate eval (Layer 3)")
    parser.add_argument("--eval", type=Path, default=DEFAULT_EVAL)
    parser.add_argument(
        "--full-agent",
        action="store_true",
        help="Run handle_query_v2 with mocked planner (checks answer LLM skip)",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    cases = _load_cases(args.eval)
    rows = asyncio.run(
        _run_full_agent(cases) if args.full_agent else _run_gate_only(cases)
    )

    n = len(rows)
    passed = sum(1 for r in rows if r.get("passed"))
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    for r in rows:
        cat = r.get("category", "?")
        by_cat[cat]["total"] += 1
        if r.get("passed"):
            by_cat[cat]["passed"] += 1

    summary = {
        "layer": "trust_gate",
        "total": n,
        "passed": passed,
        "pass_rate": round(passed / n, 3) if n else 0,
        "target_pass_rate": 0.95,
        "met_target": (passed / n >= 0.95) if n else False,
        "by_category": dict(by_cat),
    }

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or RESULTS_DIR / f"trust_gate_eval_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "results": rows}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {out}")
    if not summary["met_target"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
