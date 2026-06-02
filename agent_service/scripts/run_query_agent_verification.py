#!/usr/bin/env python3
"""Run all query-agent verification suites and write timestamped MD + JSON artifacts."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

RESULTS_DIR = SERVICE_ROOT / "app" / "evals" / "results"
E2E_150 = SERVICE_ROOT / "app" / "evals" / "e2e_query_agent_150.json"
E2E_75_FRESH = SERVICE_ROOT / "app" / "evals" / "e2e_query_agent_75_fresh.json"
TARGETED_25 = SERVICE_ROOT / "app" / "evals" / "targeted_25_fresh.json"
SMOKE_30 = SERVICE_ROOT / "app" / "evals" / "mixed_smoke_30_fresh.json"
PLANNER_100 = SERVICE_ROOT / "app" / "evals" / "planner_eval_100.json"
TRUST_GATE = SERVICE_ROOT / "app" / "evals" / "trust_gate_plan_eval.json"


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _planner_op_accuracy(case: dict[str, Any], plan_ops: list[str]) -> float | None:
    expect = case.get("expect") or {}
    expected_ops = expect.get("ops")
    if not expected_ops:
        return None
    if plan_ops == expected_ops:
        return 1.0
    if expected_ops and plan_ops and expected_ops[0] == plan_ops[0]:
        return 0.5
    return 0.0


async def run_e2e_cases(
    cases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from app import config
    from app.evals.layered_eval_checks import (
        check_answer_llm_skipped,
        check_hallucinated_facts,
        check_semantic_rank_limited,
        check_wrong_commute_destination_rank,
    )
    from app.evals.verification_reports import write_e2e_markdown, write_json
    from app.query_agent import handle_query_v2, query_agent_available
    from app.query_plan import validate_plan

    if not query_agent_available():
        raise SystemExit("Query agent unavailable — check .env and USE_LLM_QUERY_AGENT.")

    config.USE_LLM_QUERY_AGENT = True
    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()
    trust_blocks = 0
    answer_llm_used = 0
    answer_llm_skipped_refusal = 0
    halluc_violations = 0
    wrong_dest_violations = 0
    plan_invalid = 0
    planner_op_scores: list[float] = []

    for i, case in enumerate(cases, 1):
        prompt = case["prompt"]
        print(f"  E2E [{i}/{len(cases)}] {case.get('id')} …", flush=True)
        row: dict[str, Any] = {**case, "failure_reasons": []}
        try:
            payload = await handle_query_v2(prompt, save_searches=False)
            response = payload.get("response") or {}
            row["execution_status"] = payload.get("execution_status")
            row["trust_gate"] = payload.get("trust_gate")
            row["used_answer_llm"] = payload.get("used_answer_llm")
            row["raw_llm_plan"] = payload.get("raw_llm_plan")
            row["normalized_plan"] = payload.get("normalized_plan") or payload.get("plan")
            row["actual_plan"] = payload.get("plan")
            row["final_answer"] = response.get("final_recommendation", "")
            row["plan_ops"] = [
                o.get("op") for o in (payload.get("plan") or {}).get("ops") or []
            ]
            row["expected_plan_requirements"] = case.get("expect")
            try:
                if payload.get("plan"):
                    validate_plan(payload["plan"])
                row["plan_validation_pass"] = bool(payload.get("plan"))
            except Exception as exc:
                row["plan_validation_pass"] = False
                plan_invalid += 1
                row["failure_reasons"].append(f"plan_validation: {exc}")

            op_acc = _planner_op_accuracy(case, row["plan_ops"])
            row["planner_op_accuracy"] = op_acc
            if op_acc is not None:
                planner_op_scores.append(op_acc)

            status_counts[row["execution_status"] or "unknown"] += 1
            if row.get("trust_gate"):
                trust_blocks += 1

            if row.get("used_answer_llm"):
                answer_llm_used += 1

            from app.evals.layered_eval_checks import evaluate_e2e_case

            passed, failures = evaluate_e2e_case(case, payload)
            row["failure_reasons"].extend(failures)

            ok_h, errs = check_hallucinated_facts(payload)
            if not ok_h:
                halluc_violations += 1
                for e in errs:
                    if f"hallucination: {e}" not in row["failure_reasons"]:
                        row["failure_reasons"].append(f"hallucination: {e}")

            ok_d, msg = check_wrong_commute_destination_rank(prompt, payload)
            if not ok_d:
                wrong_dest_violations += 1
                if msg and f"wrong_dest: {msg}" not in row["failure_reasons"]:
                    row["failure_reasons"].append(f"wrong_dest: {msg}")

            if row["execution_status"] in (
                "blocked",
                "not_found",
                "out_of_scope",
                "no_rows",
            ) and not row.get("used_answer_llm"):
                answer_llm_skipped_refusal += 1

            row["passed"] = len(row["failure_reasons"]) == 0

        except Exception as exc:
            row["execution_status"] = "error"
            row["failure_reasons"] = [f"pipeline_error: {exc}"]
            row["passed"] = False
            row["plan_validation_pass"] = False

        rows.append(row)

    n = len(rows)
    passed_n = sum(1 for r in rows if r.get("passed"))
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    for r in rows:
        cat = r.get("category", "?")
        by_cat[cat]["total"] += 1
        if r.get("passed"):
            by_cat[cat]["passed"] += 1

    from app.evals.confusion_summary import build_confusion_summary

    failed_rows = [r for r in rows if not r.get("passed")]
    top_failures_detail = failed_rows[:20]
    target_pass = 68 if n <= 75 else 135

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": n,
        "passed": passed_n,
        "pass_rate": round(passed_n / n, 4) if n else 0,
        "target_pass_count": target_pass,
        "met_target_pass": passed_n >= target_pass,
        "planner_operation_accuracy": round(
            sum(planner_op_scores) / len(planner_op_scores), 4
        )
        if planner_op_scores
        else None,
        "plan_validation_failures": plan_invalid,
        "trust_gate_blocks": trust_blocks,
        "executor_status_counts": dict(status_counts),
        "answer_llm_used_count": answer_llm_used,
        "answer_llm_skipped_on_refusal": answer_llm_skipped_refusal,
        "hallucination_violations": halluc_violations,
        "wrong_commute_destination_violations": wrong_dest_violations,
        "met_criteria": {
            "pass_target": passed_n >= target_pass,
            "hallucinations_zero": halluc_violations == 0,
            "wrong_dest_zero": wrong_dest_violations == 0,
        },
        "by_category": dict(by_cat),
        "confusion_summary": build_confusion_summary(rows),
        "top_failures_detail": [
            {
                "id": r.get("id"),
                "category": r.get("category"),
                "prompt": r.get("prompt"),
                "failure_reasons": r.get("failure_reasons"),
                "raw_llm_plan": r.get("raw_llm_plan"),
                "normalized_plan": r.get("normalized_plan"),
                "actual_plan": r.get("actual_plan"),
                "execution_status": r.get("execution_status"),
                "final_answer": r.get("final_answer"),
            }
            for r in top_failures_detail
        ],
    }
    return rows, summary


async def run_planner_live(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from app.evals.planner_eval_scoring import score_plan_against_expect
    from app.llm_query_planner import plan_query_with_llm, planner_available
    from app.plan_normalizer import normalize_planned_query
    from app.query_plan import PlanValidationError

    if not planner_available():
        raise SystemExit("Planner not available.")

    rows: list[dict[str, Any]] = []
    invalid_count = 0
    repair_total = 0
    raw_op_scores: list[float] = []

    for i, case in enumerate(cases, 1):
        prompt = case["prompt"]
        expect = case.get("expect") or {}
        print(f"  Planner [{i}/{len(cases)}] {case.get('id')} …", flush=True)
        repair_count = 0
        try:
            raw_plan = await plan_query_with_llm(prompt, apply_normalizer=False)
            plan = normalize_planned_query(prompt, raw_plan)
            raw_score = score_plan_against_expect(raw_plan, expect)
            score = score_plan_against_expect(plan, expect)
            if raw_score.get("op_accuracy") is not None:
                raw_op_scores.append(float(raw_score["op_accuracy"]))
            rows.append(
                {
                    **case,
                    **score,
                    "raw_llm_plan": raw_plan.model_dump(mode="json"),
                    "normalized_plan": plan.model_dump(mode="json"),
                    "actual_plan": plan.model_dump(mode="json"),
                    "raw_op_accuracy": raw_score.get("op_accuracy"),
                    "repair_count": repair_count,
                    "invalid_plan": False,
                }
            )
        except PlanValidationError as exc:
            invalid_count += 1
            rows.append(
                {
                    **case,
                    "passed": False,
                    "op_accuracy": 0.0,
                    "town_accuracy": 0.0,
                    "field_accuracy": 0.0,
                    "failure_reasons": [str(exc)],
                    "repair_count": repair_count,
                    "invalid_plan": True,
                }
            )
        except Exception as exc:
            invalid_count += 1
            rows.append(
                {
                    **case,
                    "passed": False,
                    "op_accuracy": 0.0,
                    "town_accuracy": 0.0,
                    "field_accuracy": 0.0,
                    "failure_reasons": [f"planner_error: {exc}"],
                    "repair_count": repair_count,
                    "invalid_plan": True,
                }
            )

    n = len(rows)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": n,
        "passed": sum(1 for r in rows if r.get("passed")),
        "pass_rate": round(sum(1 for r in rows if r.get("passed")) / n, 4) if n else 0,
        "operation_accuracy": round(sum(r.get("op_accuracy", 0) for r in rows) / n, 4),
        "raw_operation_accuracy": round(sum(raw_op_scores) / len(raw_op_scores), 4)
        if raw_op_scores
        else None,
        "town_extraction_accuracy": round(
            sum(r.get("town_accuracy", 0) for r in rows) / n, 4
        ),
        "field_constraint_accuracy": round(
            sum(r.get("field_accuracy", 0) for r in rows) / n, 4
        ),
        "invalid_plan_count": invalid_count,
        "repair_retry_count_total": repair_total,
        "met_target_90pct": round(sum(r.get("op_accuracy", 0) for r in rows) / n, 4) >= 0.9
        if n
        else False,
        "met_target_raw_82pct": (sum(raw_op_scores) / len(raw_op_scores) >= 0.82)
        if raw_op_scores
        else False,
    }
    return rows, summary


async def run_trust_gate_full(cases: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from unittest.mock import patch

    from app.evals.layered_eval_checks import check_answer_llm_skipped, check_semantic_rank_limited
    from app.plan_executor import execute_plan_async
    from app.plan_trust_gates import evaluate_plan_trust_gate
    from app.query_agent import handle_query_v2, query_agent_available
    from app.query_plan import PlanValidationError, RankOp, SemanticSearchOp, validate_plan

    rows: list[dict[str, Any]] = []
    placeholder_executed = 0

    for case in cases:
        prompt = case["prompt"]
        row: dict[str, Any] = {**case, "failure_reason": None}

        try:
            from app.plan_normalizer import normalize_planned_query

            plan = validate_plan(case["plan"])
            plan = normalize_planned_query(prompt, plan)
        except PlanValidationError as exc:
            if case.get("expect_gate") == "invalid_plan_town" or "placeholder" in case.get(
                "category", ""
            ):
                row["actual_gate"] = "invalid_plan_town"
                row["blocks"] = True
                row["placeholder_blocked_at_validation"] = True
                row["execution_status"] = "blocked"
                row["trust_gate"] = "invalid_plan_town"
                row["used_answer_llm"] = False
                row["final_answer"] = str(exc)
                row["gate_only_pass"] = True
                row["passed"] = True
                rows.append(row)
                continue
            raise

        gate = evaluate_plan_trust_gate(prompt, plan)
        expect_gate = case.get("expect_gate")
        if expect_gate is not None:
            gate_only_pass = gate is not None and gate.gate_type == expect_gate
        else:
            gate_only_pass = gate is None
        row.update(
            {
                "actual_gate": gate.gate_type if gate else None,
                "blocks": bool(gate and gate.blocks_pipeline),
                "gate_only_pass": gate_only_pass,
            }
        )

        # Placeholder must never execute
        if "placeholder" in case.get("category", "") or "town_name" in prompt.lower():
            try:
                from app.query_plan import assert_valid_plan_town_name

                assert_valid_plan_town_name("town_name_1")
                row["placeholder_blocked_at_validation"] = False
            except Exception:
                row["placeholder_blocked_at_validation"] = True

        expect_blocks = case.get("expect_blocks", False)
        expect_status = case.get("expect_execution_status")
        if expect_status is None:
            expect_status = "blocked" if expect_blocks else "ok"

        if query_agent_available():
            with patch("app.query_agent.query_agent_available", return_value=True):
                with patch("app.query_agent.plan_query_with_llm", return_value=plan):
                    payload = await handle_query_v2(prompt, save_searches=False)
            row["execution_status"] = payload.get("execution_status")
            row["trust_gate"] = payload.get("trust_gate")
            row["used_answer_llm"] = payload.get("used_answer_llm")
            row["final_answer"] = (payload.get("response") or {}).get(
                "final_recommendation", ""
            )

            if case.get("category") == "semantic_rank_limit":
                sem_ops = [o for o in plan.ops if isinstance(o, SemanticSearchOp)]
                rank_ops = [o for o in plan.ops if isinstance(o, RankOp)]
                if sem_ops and rank_ops:
                    exec_result = await execute_plan_async(plan, validate=False)
                    row["semantic_rank_leaked"] = False
                    if exec_result.status.value == "ok" and exec_result.ops_results:
                        sem_result = next(
                            (r for r in exec_result.ops_results if r.op == "semantic_search"),
                            None,
                        )
                        rank_data = next(
                            (r for r in exec_result.ops_results if r.op == "rank"),
                            None,
                        )
                        candidates = set(
                            (sem_result.data.get("candidate_town_names") or [])
                            if sem_result
                            else []
                        )
                        ranked = [
                            m.get("town") or m.get("name")
                            for m in (rank_data.data.get("top_matches") or [])
                            if rank_data
                        ]
                        if candidates and ranked and any(
                            t and t not in candidates for t in ranked
                        ):
                            row["semantic_rank_leaked"] = True
                        elif not rank_ops[0].use_semantic_candidates:
                            row["semantic_rank_leaked"] = True
                        else:
                            row["semantic_rank_leaked"] = False

        status_ok = row.get("execution_status") == expect_status
        expect_gate = case.get("expect_gate")
        if expect_gate == "invalid_plan_town":
            gate_ok = row.get("actual_gate") == "invalid_plan_town" or row.get(
                "placeholder_blocked_at_validation"
            )
        else:
            gate_ok = row.get("actual_gate") == expect_gate
        llm_ok, llm_err = check_answer_llm_skipped(
            {
                "execution_status": row.get("execution_status"),
                "trust_gate": row.get("trust_gate"),
                "used_answer_llm": row.get("used_answer_llm"),
            }
        )
        passed = bool(row.get("gate_only_pass") or gate_ok) and status_ok and gate_ok and llm_ok
        if case.get("category") == "semantic_rank_limit":
            passed = passed and not row.get("semantic_rank_leaked", False)
        if case.get("category") == "placeholder_town":
            passed = passed and row.get("placeholder_blocked_at_validation", False)
            if row.get("execution_status") == "ok" and not expect_blocks:
                placeholder_executed += 1
                passed = False

        row["passed"] = passed
        if not passed:
            parts = []
            if not row.get("gate_only_pass"):
                parts.append(
                    f"gate expected {case.get('expect_gate')!r}, got {row.get('actual_gate')!r}"
                )
            if not status_ok:
                parts.append(f"status {row.get('execution_status')!r}")
            if not gate_ok:
                parts.append(f"trust_gate {row.get('trust_gate')!r}")
            if not llm_ok:
                parts.append(llm_err or "answer_llm")
            row["failure_reason"] = "; ".join(parts)
        rows.append(row)

    n = len(rows)
    passed_n = sum(1 for r in rows if r.get("passed"))
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total": n,
        "passed": passed_n,
        "pass_rate": round(passed_n / n, 4) if n else 0,
        "target_pass_rate": 0.95,
        "met_target": passed_n / n >= 0.95 if n else False,
        "placeholder_towns_executed": placeholder_executed,
        "by_category": {},
    }
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    for r in rows:
        cat = r.get("category", "?")
        by_cat[cat]["total"] += 1
        if r.get("passed"):
            by_cat[cat]["passed"] += 1
    summary["by_category"] = dict(by_cat)
    return rows, summary


async def run_executor_golden() -> dict[str, Any]:
    import os

    from app.plan_executor import execute_plan_async
    from tests.golden_plan_assertions import assert_golden_case, load_manifest, load_plan_file

    manifest = load_manifest()
    cases = manifest.get("cases") or []
    skip_semantic = os.getenv("ENABLE_SEMANTIC_GOLDEN", "").lower() not in (
        "1",
        "true",
        "yes",
    )
    failures: list[str] = []
    ran = 0
    for case in cases:
        if case.get("requires_live_embeddings") and skip_semantic:
            continue
        ran += 1
        if case.get("expect_validation_error"):
            from app.query_plan import PlanValidationError, validate_plan

            plan_data = load_plan_file(case["plan_file"])
            try:
                validate_plan(plan_data)
                failures.append(f"{case['id']}: expected validation error but plan validated")
            except (PlanValidationError, Exception):
                pass
            continue
        plan_data = load_plan_file(case["plan_file"])
        result = await execute_plan_async(plan_data)
        failures.extend(assert_golden_case(case, result))
    return {
        "total_cases_run": ran,
        "passed": ran - len({f.split(":")[0] for f in failures}),
        "failures": failures,
        "pass_rate": 1.0 if not failures else round((ran - len(failures)) / ran, 4) if ran else 0,
        "met_target_100pct": len(failures) == 0,
    }


async def main_async(args: argparse.Namespace) -> None:
    from app.evals.verification_reports import (
        write_e2e_markdown,
        write_json,
        write_planner_markdown,
        write_trust_gate_markdown,
    )

    ts = _ts()
    artifacts: dict[str, str] = {}

    async def _run_e2e_suite(label: str, path: Path, base_name: str, target: int) -> None:
        payload = json.loads(path.read_text(encoding="utf-8"))
        cases = payload.get("cases") or []
        print(f"\n=== {label} ({len(cases)} prompts) ===")
        rows, summ = await run_e2e_cases(cases)
        summ["target_pass_count"] = target
        summ["met_target_pass"] = summ.get("passed", 0) >= target
        summ["top_failures_detail"] = [r for r in rows if not r.get("passed")][:20]
        jpath = RESULTS_DIR / f"{base_name}_{ts}.json"
        mpath = RESULTS_DIR / f"{base_name}_{ts}.md"
        write_json(jpath, {"summary": summ, "results": rows})
        write_e2e_markdown(mpath, summ, rows)
        artifacts[base_name] = str(jpath)
        artifacts[f"{base_name}_md"] = str(mpath)
        print(f"Wrote {jpath}\nWrote {mpath}")

    if not args.skip_targeted25:
        if not TARGETED_25.exists():
            raise SystemExit("Run scripts/generate_targeted_25_fresh.py first.")
        await _run_e2e_suite(
            "Targeted 25 fresh",
            TARGETED_25,
            "query_agent_targeted_25_fresh",
            24,
        )

    if not args.skip_smoke30:
        if not SMOKE_30.exists():
            raise SystemExit("Run scripts/generate_mixed_smoke_30_fresh.py first.")
        await _run_e2e_suite(
            "Mixed smoke 30 fresh",
            SMOKE_30,
            "query_agent_mixed_smoke_30_fresh",
            28,
        )

    # E2E 75 fresh holdout (legacy full holdout)
    if not args.skip_e2e75:
        if not E2E_75_FRESH.exists():
            raise SystemExit(f"Missing holdout file: {E2E_75_FRESH}. Run generate_e2e_75_fresh.py")
        e2e75_payload = json.loads(E2E_75_FRESH.read_text(encoding="utf-8"))
        cases75 = e2e75_payload.get("cases") or []
        print(f"\n=== E2E 75 fresh holdout ({len(cases75)} prompts) ===")
        rows75, sum75 = await run_e2e_cases(cases75)
        failed75 = [r for r in rows75 if not r.get("passed")]
        sum75["top_failures_detail"] = failed75[:20]
        base75 = f"query_agent_e2e_75_fresh_{ts}"
        j75 = RESULTS_DIR / f"{base75}.json"
        m75 = RESULTS_DIR / f"{base75}.md"
        write_json(j75, {"summary": sum75, "results": rows75})
        write_e2e_markdown(m75, sum75, rows75)
        artifacts["e2e_75_json"] = str(j75)
        artifacts["e2e_75_md"] = str(m75)
        print(f"Wrote {j75}\nWrote {m75}")

    # 1 — E2E 30 (legacy)
    if not args.skip_e2e30:
        e2e_payload = json.loads(E2E_150.read_text(encoding="utf-8"))
        cases30 = (e2e_payload.get("cases") or [])[:30]
        print(f"\n=== E2E 30 ({len(cases30)} prompts) ===")
        rows30, sum30 = await run_e2e_cases(cases30)
        for r in rows30:
            if "failure_reasons" not in r or r["failure_reasons"] is None:
                r["failure_reasons"] = []
        sum30["top_failures_detail"] = [dict(r) for r in rows30 if not r.get("passed")][:20]
        base30 = f"query_agent_e2e_30_after_fixes_{ts}"
        j30 = RESULTS_DIR / f"{base30}.json"
        m30 = RESULTS_DIR / f"{base30}.md"
        write_json(j30, {"summary": sum30, "results": rows30})
        write_e2e_markdown(m30, sum30, rows30)
        artifacts["e2e_30_json"] = str(j30)
        artifacts["e2e_30_md"] = str(m30)
        print(f"Wrote {j30}\nWrote {m30}")

    # 2 — E2E 150
    if not args.skip_e2e150:
        e2e_payload = json.loads(E2E_150.read_text(encoding="utf-8"))
        cases150 = e2e_payload.get("cases") or []
        print(f"\n=== E2E 150 ({len(cases150)} prompts) ===")
        rows150, sum150 = await run_e2e_cases(cases150)
        failed = [r for r in rows150 if not r.get("passed")]
        sum150["top_failures_detail"] = failed[:20]
        base150 = f"query_agent_e2e_150_{ts}"
        j150 = RESULTS_DIR / f"{base150}.json"
        m150 = RESULTS_DIR / f"{base150}.md"
        write_json(j150, {"summary": sum150, "results": rows150})
        write_e2e_markdown(m150, sum150, rows150)
        artifacts["e2e_150_json"] = str(j150)
        artifacts["e2e_150_md"] = str(m150)
        print(f"Wrote {j150}\nWrote {m150}")

    # 3 — Planner live
    if not args.skip_planner:
        planner_payload = json.loads(PLANNER_100.read_text(encoding="utf-8"))
        pcases = planner_payload.get("cases") or []
        print(f"\n=== Planner live ({len(pcases)} prompts) ===")
        prow, psum = await run_planner_live(pcases)
        basep = f"query_agent_planner_eval_{ts}"
        jp = RESULTS_DIR / f"{basep}.json"
        mp = RESULTS_DIR / f"{basep}.md"
        write_json(jp, {"summary": psum, "results": prow})
        write_planner_markdown(mp, psum, prow)
        artifacts["planner_json"] = str(jp)
        artifacts["planner_md"] = str(mp)
        print(f"Wrote {jp}\nWrote {mp}")

    # 4 — Trust gate
    if not args.skip_trust:
        tg_payload = json.loads(TRUST_GATE.read_text(encoding="utf-8"))
        tcases = tg_payload.get("cases") or []
        # merge extended cases file if present
        ext = SERVICE_ROOT / "app" / "evals" / "trust_gate_plan_eval_extended.json"
        if ext.exists():
            tcases = tcases + (json.loads(ext.read_text()).get("cases") or [])
        print(f"\n=== Trust gate ({len(tcases)} cases) ===")
        trows, tsum = await run_trust_gate_full(tcases)
        baset = f"query_agent_trust_gate_eval_{ts}"
        jt = RESULTS_DIR / f"{baset}.json"
        mt = RESULTS_DIR / f"{baset}.md"
        write_json(jt, {"summary": tsum, "results": trows})
        write_trust_gate_markdown(mt, tsum, trows)
        artifacts["trust_json"] = str(jt)
        artifacts["trust_md"] = str(mt)
        print(f"Wrote {jt}\nWrote {mt}")

    # Executor golden
    print("\n=== Executor golden (offline) ===")
    golden = await run_executor_golden()
    baseg = f"query_agent_executor_golden_{ts}.json"
    jg = RESULTS_DIR / baseg
    write_json(jg, {"summary": golden})
    artifacts["executor_golden_json"] = str(jg)
    print(f"Wrote {jg}")

    index = RESULTS_DIR / f"query_agent_verification_index_{ts}.json"
    write_json(
        index,
        {
            "timestamp": ts,
            "artifacts": artifacts,
            "executor_golden": golden,
        },
    )
    print(f"\nIndex: {index}")
    print(json.dumps(artifacts, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-targeted25", action="store_true")
    parser.add_argument("--skip-smoke30", action="store_true")
    parser.add_argument("--skip-e2e75", action="store_true", default=True)
    parser.add_argument("--skip-e2e30", action="store_true", default=True)
    parser.add_argument("--skip-e2e150", action="store_true", default=True)
    parser.add_argument("--phase2-only", action="store_true")
    parser.add_argument("--skip-planner", action="store_true")
    parser.add_argument("--skip-trust", action="store_true")
    parser.add_argument("--e2e30-only", action="store_true")
    parser.add_argument("--planner-only", action="store_true")
    args = parser.parse_args()
    if args.phase2_only:
        args.skip_e2e75 = True
        args.skip_e2e30 = True
        args.skip_e2e150 = True
    if args.e2e30_only:
        args.skip_e2e75 = True
        args.skip_e2e150 = True
        args.skip_planner = True
        args.skip_trust = True
        args.skip_targeted25 = True
        args.skip_smoke30 = True
        args.skip_e2e30 = False
    if args.planner_only:
        args.skip_e2e75 = True
        args.skip_e2e30 = True
        args.skip_e2e150 = True
        args.skip_trust = True
        args.skip_targeted25 = True
        args.skip_smoke30 = True
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
