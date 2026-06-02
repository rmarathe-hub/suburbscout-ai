"""Evaluate query-agent responses (Phase 7)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.evals.runner import evaluate_case

EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_QUERY_AGENT_EVAL = EVALS_DIR / "query_agent_eval.json"


def load_query_agent_eval_cases(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or DEFAULT_QUERY_AGENT_EVAL
    with open(target, encoding="utf-8") as f:
        payload = json.load(f)
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        raise ValueError(f"Invalid query agent eval file: {target}")
    return cases


def evaluate_query_agent_case(case: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """Score one query-agent turn."""
    failures: list[str] = []
    response = payload.get("response") or {}

    if case.get("expect_execution_status"):
        actual = payload.get("execution_status")
        if actual != case["expect_execution_status"]:
            failures.append(
                f"execution_status expected {case['expect_execution_status']!r}, got {actual!r}"
            )

    if case.get("expect_trust_gate"):
        if payload.get("trust_gate") != case["expect_trust_gate"]:
            failures.append(
                f"trust_gate expected {case['expect_trust_gate']!r}, got {payload.get('trust_gate')!r}"
            )

    if case.get("expect_trust_gate_null") and payload.get("trust_gate"):
        failures.append(f"expected no trust_gate, got {payload.get('trust_gate')!r}")

    if case.get("expect_used_answer_llm") is True and not payload.get("used_answer_llm"):
        failures.append("expected used_answer_llm=true")

    if case.get("expect_used_answer_llm") is False and payload.get("used_answer_llm"):
        failures.append("expected used_answer_llm=false")

    plan = payload.get("plan")
    if expected_ops := case.get("expect_plan_ops"):
        if not plan or not isinstance(plan, dict):
            failures.append("expected plan in payload")
        else:
            actual_ops = [op.get("op") for op in plan.get("ops") or []]
            for op_name in expected_ops:
                if op_name not in actual_ops:
                    failures.append(f"expected plan op {op_name!r}, got {actual_ops}")

    adapted = {
        "response": response,
        "route": {"intent": response.get("route_intent") or "query_agent"},
    }
    _, base_failures = evaluate_case(case, adapted)
    failures.extend(base_failures)

    return (len(failures) == 0, failures)
