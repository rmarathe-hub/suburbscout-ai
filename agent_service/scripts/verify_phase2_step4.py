#!/usr/bin/env python3
"""Phase 2 Step 4 — normalizer hardening + plan_expect towns + audit fields."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


def _fail(msg: str) -> None:
    print(f"  FAIL: {msg}")
    sys.exit(1)


def _pass(msg: str) -> None:
    print(f"  PASS: {msg}")


def check_normalizer_order() -> None:
    print("1. Normalizer hard-unsupported runs first")
    import inspect

    from app import plan_normalizer

    src = inspect.getsource(plan_normalizer.normalize_planned_query)
    idx_hard = src.find("_rewrite_hard_unsupported")
    idx_pull = src.find("_rewrite_pull_up_lookup")
    if idx_hard < 0 or idx_pull < 0 or idx_hard > idx_pull:
        _fail("expected _rewrite_hard_unsupported before _rewrite_pull_up_lookup")
    _pass("neighborhood/live-market before pull-up/membership")


def check_pull_up_town() -> None:
    print("\n2. Pull-up town disambiguation (Reading vs North Reading)")
    from app.plan_normalizer import normalize_planned_query
    from app.query_plan import LookupOp, validate_plan

    for phrase, expected in (
        ("Open Reading.", "Reading"),
        ("Open North Reading.", "North Reading"),
        ("Pull up Westboro.", "Westborough"),
    ):
        raw = validate_plan({"ops": [{"op": "membership", "town": "Wrong"}]})
        plan = normalize_planned_query(phrase, raw)
        if not isinstance(plan.ops[0], LookupOp):
            _fail(f"{phrase!r} expected lookup op")
        town = plan.ops[0].items[0].town
        if town != expected:
            _fail(f"{phrase!r} expected {expected}, got {town}")
    _pass("Reading / North Reading / Westborough pull-up towns")


def check_lookup_guard() -> None:
    print("\n3. Factual lookups not downgraded to membership")
    from app.plan_normalizer import normalize_planned_query
    from app.query_plan import LookupFieldKind, LookupOp, validate_plan

    q = "What is the commute from Maynard?"
    raw = validate_plan({"ops": [{"op": "membership", "town": "Maynard"}]})
    plan = normalize_planned_query(q, raw)
    if not isinstance(plan.ops[0], LookupOp):
        _fail("commute question should become lookup")
    if plan.ops[0].items[0].field != LookupFieldKind.COMMUTE.value:
        _fail("expected commute field on lookup")
    _pass("commute lookup preserved")


def check_audit_fields() -> None:
    print("\n4. Audit log record shape")
    import inspect

    from app import query_agent_audit

    sig = inspect.signature(query_agent_audit.save_query_agent_turn)
    params = sig.parameters
    for name in ("request_id", "latency_ms", "raw_plan"):
        if name not in params:
            _fail(f"save_query_agent_turn missing {name}")
    _pass("audit supports request_id, latency_ms, raw_plan")


def check_plan_expect_scoring() -> None:
    print("\n5. plan_expect expected_town / forbidden_towns")
    from app.evals.planner_eval_scoring import score_plan_against_expect
    from app.query_plan import validate_plan

    plan = validate_plan(
        {
            "ops": [
                {
                    "op": "lookup",
                    "items": [{"town": "Reading", "field": "summary"}],
                }
            ]
        }
    )
    ok = score_plan_against_expect(
        plan,
        {"expected_town": "Reading", "forbidden_towns": ["North Reading"]},
    )
    if not ok["passed"]:
        _fail(f"scoring failed: {ok['failure_reasons']}")
    bad = validate_plan(
        {
            "ops": [
                {
                    "op": "lookup",
                    "items": [{"town": "North Reading", "field": "summary"}],
                }
            ]
        }
    )
    fail = score_plan_against_expect(
        bad,
        {"expected_town": "Reading", "forbidden_towns": ["North Reading"]},
    )
    if fail["passed"]:
        _fail("expected forbidden North Reading to fail")
    _pass("town expect scoring")


def run_unit_tests() -> None:
    print("\n6. Unit tests")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.test_plan_normalizer",
            "tests.test_plan_expect_towns",
            "-v",
        ],
        cwd=str(SERVICE_ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        _fail("unit tests failed")
    _pass("test_plan_normalizer + test_plan_expect_towns")


def main() -> None:
    print("=== Phase 2 Step 4: Hardening ===\n")
    check_normalizer_order()
    check_pull_up_town()
    check_lookup_guard()
    check_audit_fields()
    check_plan_expect_scoring()
    run_unit_tests()
    print("\n=== Phase 2 Step 4 verification: PASSED ===")
    print("Optional full eval: python scripts/run_query_agent_verification.py --phase2-only")


if __name__ == "__main__":
    main()
