"""Shared checks for trust-gate and E2E query-agent eval layers."""

from __future__ import annotations

import re
from typing import Any

from app.commute_destination import detect_commute_destination, is_non_boston_destination_query
from app.llm_answer import collect_allowed_facts, validate_answer_against_context
from app.plan_executor import ExecutionResult, ExecutionStatus
from app.query_plan import QueryPlan, validate_plan


REFUSAL_STATUSES = frozenset(
    {"blocked", "out_of_scope", "not_found", "no_rows", "invalid_plan"}
)

NO_ANSWER_LLM_STATUSES = REFUSAL_STATUSES

NON_BLOCKING_TRUST_GATES = frozenset(
    {"semantic_lifestyle_note", "unsupported_rank_partial"}
)


def execution_from_payload(payload: dict[str, Any]) -> ExecutionResult | None:
    """Rebuild minimal ExecutionResult for answer validation when only payload stored."""
    status = payload.get("execution_status")
    if not status:
        return None
    try:
        st = ExecutionStatus(status)
    except ValueError:
        return None
    plan_data = payload.get("plan")
    plan = validate_plan(plan_data) if plan_data else None
    return ExecutionResult(
        status=st,
        message_code=payload.get("message_code"),
        plan=plan,
        answer_context=payload.get("answer_context") or {},
    )


def check_answer_llm_skipped(payload: dict[str, Any]) -> tuple[bool, str | None]:
    status = payload.get("execution_status")
    if status in NO_ANSWER_LLM_STATUSES and payload.get("used_answer_llm"):
        return False, f"answer LLM ran on status {status}"
    trust_gate = payload.get("trust_gate")
    if trust_gate and payload.get("used_answer_llm"):
        blocks = payload.get("trust_gate_blocks")
        if blocks is None:
            blocks = trust_gate not in NON_BLOCKING_TRUST_GATES
        if blocks:
            return False, "answer LLM ran when trust gate blocked"
    return True, None


def check_hallucinated_facts(
    payload: dict[str, Any],
    *,
    execution: ExecutionResult | None = None,
) -> tuple[bool, list[str]]:
    """Return (ok, errors). ok=True means no hallucinated unsupported facts detected."""
    if not payload.get("used_answer_llm"):
        return True, []

    response = payload.get("response") or {}
    answer = str(response.get("final_recommendation") or "")
    exec_result = execution or execution_from_payload(payload)
    if not exec_result:
        return True, []

    validation = validate_answer_against_context(answer, exec_result)
    if not validation.valid:
        return False, list(validation.errors)

    # Unsupported attribute claims in answer when execution was refusal
    if exec_result.status in (
        ExecutionStatus.OUT_OF_SCOPE,
        ExecutionStatus.NOT_FOUND,
        ExecutionStatus.NO_ROWS,
    ):
        if re.search(r"\$\s*[\d,]+", answer):
            return False, ["refusal answer contains dollar amounts"]
    return True, []


def check_wrong_commute_destination_rank(
    prompt: str,
    payload: dict[str, Any],
) -> tuple[bool, str | None]:
    """
    Fail if user asked for non-Boston commute ranking but response presents
    Boston commute ranking as if it answered their destination.
    """
    if not is_non_boston_destination_query(prompt):
        return True, None

    status = payload.get("execution_status")
    gate = payload.get("trust_gate") or ""
    if status == "blocked" and "commute_destination" in str(gate):
        return True, None
    if status in ("out_of_scope", "blocked"):
        return True, None

    response = payload.get("response") or {}
    answer = str(response.get("final_recommendation") or "").lower()
    dest = detect_commute_destination(prompt)
    if dest.is_default:
        return True, None

    # Ranked top matches without disclaimer when non-Boston dest requested
    top = response.get("top_matches") or []
    if top and status == "ok":
        if dest.label.lower() not in answer and "south station" not in answer:
            if "boston" not in answer and "only" not in answer:
                return (
                    False,
                    f"ranked towns without Boston commute limitation for {dest.label}",
                )
    return True, None


def check_semantic_rank_limited(
    plan: QueryPlan | None,
    payload: dict[str, Any],
) -> tuple[bool, str | None]:
    """When plan is semantic_search → rank, rank should use semantic candidates."""
    if not plan:
        return True, None
    ops = [type(o).__name__ for o in plan.ops]
    from app.query_plan import RankOp, SemanticSearchOp

    has_sem = any(isinstance(o, SemanticSearchOp) for o in plan.ops)
    rank_ops = [o for o in plan.ops if isinstance(o, RankOp)]
    if has_sem and rank_ops:
        if not rank_ops[0].use_semantic_candidates:
            return False, "rank after semantic_search missing use_semantic_candidates"
    return True, None


def evaluate_e2e_case(case: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, list[str]]:
    """Score one E2E case against expect block and global safety checks."""
    from app.evals.planner_eval_scoring import score_plan_against_expect

    failures: list[str] = []
    expect = case.get("expect") or {}
    prompt = case["prompt"]

    status = payload.get("execution_status")
    if allowed := expect.get("execution_status_in"):
        if status not in allowed:
            failures.append(f"status {status!r} not in {allowed}")

    if expect.get("expect_used_answer_llm") is False and payload.get("used_answer_llm"):
        failures.append("answer LLM should be skipped")

    if expect.get("expect_trust_gate"):
        if payload.get("trust_gate") != expect["expect_trust_gate"]:
            failures.append(f"trust_gate expected {expect['expect_trust_gate']!r}")

    plan_data = payload.get("plan")
    if plan_data and (ops_need := expect.get("plan_ops_contains")):
        actual_ops = [o.get("op") for o in plan_data.get("ops") or []]
        for op in ops_need:
            if op not in actual_ops:
                failures.append(f"plan missing op {op!r}")

    if plan_data and (max_ops := expect.get("plan_ops_max")) is not None:
        actual_ops = [o.get("op") for o in plan_data.get("ops") or []]
        if len(actual_ops) > max_ops:
            failures.append(f"plan has {len(actual_ops)} ops, max {max_ops}")

    if plan_data and expect.get("require_semantic_rank_limited"):
        plan = validate_plan(plan_data)
        ok_sem, sem_err = check_semantic_rank_limited(plan, payload)
        if not ok_sem:
            failures.append(sem_err or "semantic_rank_not_limited")

    if plan_data and expect.get("rank_requires_coastal"):
        for op in plan_data.get("ops") or []:
            if op.get("op") == "rank":
                prefs = op.get("preferences") or {}
                if not prefs.get("requires_coastal"):
                    failures.append("rank missing requires_coastal=true")

    if plan_data and (ops_any := expect.get("plan_ops_contains_any")):
        actual_ops = [o.get("op") for o in plan_data.get("ops") or []]
        if not any(o in actual_ops for o in ops_any):
            failures.append(f"plan ops {actual_ops} missing any of {ops_any}")

    if expect.get("forbid_hallucinated_facts"):
        ok, errs = check_hallucinated_facts(payload)
        if not ok:
            failures.extend(errs)

    if expect.get("forbid_wrong_commute_rank"):
        ok, msg = check_wrong_commute_destination_rank(prompt, payload)
        if not ok:
            failures.append(msg or "wrong commute destination ranking")

    llm_ok, llm_err = check_answer_llm_skipped(payload)
    if not llm_ok:
        failures.append(llm_err or "answer LLM policy violation")

    if plan_expect := expect.get("plan_expect"):
        if plan_data:
            plan = validate_plan(plan_data)
            score = score_plan_against_expect(plan, plan_expect)
            if not score["passed"]:
                failures.extend(score["failure_reasons"])

    if plan_data and not expect.get("require_semantic_rank_limited"):
        plan = validate_plan(plan_data)
        ok_sem, sem_err = check_semantic_rank_limited(plan, payload)
        if not ok_sem:
            failures.append(sem_err or "semantic_rank_not_limited")

    return len(failures) == 0, failures
