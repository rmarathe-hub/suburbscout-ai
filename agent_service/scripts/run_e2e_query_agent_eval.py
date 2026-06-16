#!/usr/bin/env python3
"""Layer 4 — full E2E query agent eval (planner → trust → execute → answer)."""

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

DEFAULT_EVAL = SERVICE_ROOT / "app" / "evals" / "e2e_query_agent_150.json"
RESULTS_DIR = SERVICE_ROOT / "app" / "evals" / "results"


def _load_cases(path: Path, limit: int | None) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") or []
    if limit:
        cases = cases[:limit]
    return payload, cases


def _check_expect(
    case: dict[str, Any],
    payload: dict[str, Any],
    *,
    rescore_mode: bool = False,
) -> tuple[bool, list[str]]:
    from app.evals.layered_eval_checks import (
        check_answer_llm_skipped,
        check_hallucinated_facts,
        check_wrong_commute_destination_rank,
    )
    from app.evals.planner_eval_scoring import score_plan_against_expect
    from app.query_plan import validate_plan

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

    if plan_data and (ops_any := expect.get("plan_ops_contains_any")):
        actual_ops = [o.get("op") for o in plan_data.get("ops") or []]
        if not any(o in actual_ops for o in ops_any):
            failures.append(f"plan ops {actual_ops} missing any of {ops_any}")

    if expect.get("forbid_hallucinated_facts") and not rescore_mode:
        ok, errs = check_hallucinated_facts(payload)
        if not ok:
            failures.extend(errs)

    if expect.get("forbid_wrong_commute_rank") and not rescore_mode:
        ok, msg = check_wrong_commute_destination_rank(prompt, payload)
        if not ok:
            failures.append(msg or "wrong commute destination ranking")

    if not rescore_mode:
        llm_ok, llm_err = check_answer_llm_skipped(payload)
        if not llm_ok:
            failures.append(llm_err or "answer LLM policy violation")

    if plan_expect := expect.get("plan_expect"):
        if plan_data:
            plan = validate_plan(plan_data)
            score = score_plan_against_expect(plan, plan_expect)
            if not score["passed"]:
                failures.extend(score["failure_reasons"])

    return len(failures) == 0, failures


async def _run(cases: list[dict[str, Any]], *, save_audit: bool) -> list[dict[str, Any]]:
    from app import config
    from app.query_agent import handle_query_v2, query_agent_available

    if not query_agent_available():
        raise SystemExit(
            "Query agent unavailable. Set USE_LLM_QUERY_AGENT=true and Azure credentials."
        )

    config.USE_LLM_QUERY_AGENT = True
    rows: list[dict[str, Any]] = []
    for case in cases:
        prompt = case["prompt"]
        try:
            payload = await handle_query_v2(prompt, save_searches=save_audit)
            plan_valid = bool(payload.get("plan"))
            repair_count = 0
        except Exception as exc:
            rows.append(
                {
                    **case,
                    "passed": False,
                    "failure_reasons": [f"pipeline_error: {exc}"],
                    "plan_validation_pass": False,
                }
            )
            continue

        passed, failures = _check_expect(case, payload)
        rows.append(
            {
                **case,
                "passed": passed,
                "failure_reasons": failures,
                "execution_status": payload.get("execution_status"),
                "trust_gate": payload.get("trust_gate"),
                "used_answer_llm": payload.get("used_answer_llm"),
                "plan_ops": [
                    o.get("op") for o in (payload.get("plan") or {}).get("ops") or []
                ],
                "plan_validation_pass": plan_valid,
                "repair_count": repair_count,
                "final_snippet": (payload.get("response") or {}).get(
                    "final_recommendation", ""
                )[:200],
            }
        )
    return rows


def _summarize(
    rows: list[dict[str, Any]],
    targets: dict[str, Any],
) -> dict[str, Any]:
    n = len(rows)
    passed = sum(1 for r in rows if r.get("passed"))
    halluc = sum(
        1
        for r in rows
        if any("price" in (x or "").lower() or "not in execution" in (x or "") for x in r.get("failure_reasons") or [])
    )
    wrong_dest = sum(
        1
        for r in rows
        if any("commute" in (x or "").lower() and "limitation" in (x or "").lower() for x in r.get("failure_reasons") or [])
    )
    skipped_ok = sum(
        1
        for r in rows
        if r.get("execution_status") in ("blocked", "not_found", "out_of_scope", "no_rows")
        and not r.get("used_answer_llm")
    )
    refusal_total = sum(
        1
        for r in rows
        if r.get("execution_status") in ("blocked", "not_found", "out_of_scope", "no_rows")
    )

    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    for r in rows:
        cat = r.get("category", "?")
        by_cat[cat]["total"] += 1
        if r.get("passed"):
            by_cat[cat]["passed"] += 1

    failures = Counter()
    for r in rows:
        if not r.get("passed"):
            for reason in r.get("failure_reasons") or ["unknown"]:
                failures[reason[:80]] += 1

    return {
        "layer": "e2e_full",
        "total": n,
        "passed": passed,
        "pass_rate": round(passed / n, 3) if n else 0,
        "targets": targets,
        "met_targets": {
            "final_pass_count": passed >= targets.get("final_pass_count", 135),
            "hallucinated_unsupported_facts": halluc == 0,
            "wrong_commute_destination_ranking": wrong_dest == 0,
        },
        "answer_llm_skipped_on_refusal": skipped_ok,
        "refusal_total": refusal_total,
        "by_category": dict(by_cat),
        "top_failures": failures.most_common(12),
    }


def _row_payload_from_result(row: dict[str, Any]) -> dict[str, Any]:
    """Rebuild minimal pipeline payload for rescoring stored results."""
    return {
        "execution_status": row.get("execution_status"),
        "trust_gate": row.get("trust_gate"),
        "used_answer_llm": row.get("used_answer_llm"),
        "plan": {"ops": [{"op": op} for op in (row.get("plan_ops") or [])]},
        "response": {"final_recommendation": row.get("final_snippet", "")},
    }


def rescore_results(
    eval_path: Path,
    results_path: Path,
    *,
    limit: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Re-apply build_e2e_expect to saved results without re-running the LLM."""
    from app.evals.e2e_expect import build_e2e_expect

    payload, cases = _load_cases(eval_path, limit)
    stored = json.loads(results_path.read_text(encoding="utf-8"))
    rows = stored.get("results") or []
    case_by_id = {c["id"]: c for c in cases}

    updated: list[dict[str, Any]] = []
    for row in rows:
        case = case_by_id.get(row.get("id"))
        if not case:
            updated.append(row)
            continue
        expect = build_e2e_expect(case)
        row_payload = _row_payload_from_result(row)
        passed, failures = _check_expect({**case, "expect": expect}, row_payload, rescore_mode=True)
        updated.append(
            {
                **row,
                "passed": passed,
                "failure_reasons": failures,
                "expect": expect,
            }
        )

    summary = _summarize(updated, payload.get("targets") or {})
    return summary, updated


def main() -> None:
    parser = argparse.ArgumentParser(description="E2E query-agent eval (Layer 4)")
    parser.add_argument("--eval", type=Path, default=DEFAULT_EVAL)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--save-audit", action="store_true")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--rescore",
        type=Path,
        default=None,
        help="Re-score an existing results JSON with current build_e2e_expect rules",
    )
    args = parser.parse_args()

    if not args.eval.exists():
        raise SystemExit(f"Missing {args.eval}. Run: python scripts/generate_e2e_150.py")

    if args.rescore:
        if not args.rescore.exists():
            raise SystemExit(f"Missing results file: {args.rescore}")
        summary, rows = rescore_results(args.eval, args.rescore, limit=args.limit)
        out = args.out or args.rescore
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"summary": summary, "results": rows}, indent=2), encoding="utf-8")
        print(json.dumps(summary, indent=2))
        print(f"\nRescored {len(rows)} rows -> {out}")
        if not summary["met_targets"].get("final_pass_count", True):
            sys.exit(1)
        return

    payload, cases = _load_cases(args.eval, args.limit)
    rows = asyncio.run(_run(cases, save_audit=args.save_audit))
    summary = _summarize(rows, payload.get("targets") or {})

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or RESULTS_DIR / f"e2e_query_agent_150_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"summary": summary, "results": rows}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {out}")
    if not summary["met_targets"].get("final_pass_count", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
