#!/usr/bin/env python3
"""Phase 2 Step 3 — QueryPlan / Preferences contract + rule fallback."""

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


def check_docs() -> None:
    print("1. Plan contract documentation")
    md = SERVICE_ROOT / "docs" / "PLAN_CONTRACT.md"
    if not md.exists():
        _fail(f"Missing {md}")
    text = md.read_text(encoding="utf-8")
    if "diversity" not in text.lower() or "not supported" not in text.lower():
        _fail("PLAN_CONTRACT.md should list unsupported concepts (e.g. diversity)")
    if "QueryPlan" not in text:
        _fail("PLAN_CONTRACT.md should describe QueryPlan pipeline")
    _pass("docs/PLAN_CONTRACT.md present")


def check_contract_module() -> None:
    print("\n2. plan_contract.py")
    from app.plan_contract import (
        CANONICAL_PLAN_EXAMPLES,
        PIPELINE_NOTE,
        SUPPORTED_PREFERENCE_FIELDS,
        UNSUPPORTED_PREFERENCE_CONCEPTS,
    )

    if len(CANONICAL_PLAN_EXAMPLES) != 5:
        _fail(f"expected 5 canonical examples, got {len(CANONICAL_PLAN_EXAMPLES)}")
    ops_sets = {tuple(ex.expected_ops) for ex in CANONICAL_PLAN_EXAMPLES}
    required = {
        ("lookup",),
        ("compare",),
        ("rank",),
        ("semantic_search", "rank"),
        ("unsupported",),
    }
    if ops_sets != required:
        _fail(f"canonical op sets mismatch: {ops_sets}")
    if "diversity" not in " ".join(UNSUPPORTED_PREFERENCE_CONCEPTS).lower():
        _fail("diversity should be listed as unsupported")
    if len(SUPPORTED_PREFERENCE_FIELDS) < 10:
        _fail("SUPPORTED_PREFERENCE_FIELDS too short")
    if "normalizer" not in PIPELINE_NOTE:
        _fail("PIPELINE_NOTE should mention normalizer")
    _pass("5 canonical examples + preference field lists")


def check_fallback_module() -> None:
    print("\n3. Rule fallback (offline)")
    from app.plan_fallback import build_rule_fallback_plan, can_rule_fallback_plan

    rank_phrase = "Safe suburb under $900k with good schools"
    if not can_rule_fallback_plan(rank_phrase):
        _fail("rank prompt should be fallback-eligible")
    plan = build_rule_fallback_plan(rank_phrase)
    if plan.ops[0].op != "rank":
        _fail(f"expected rank op, got {plan.ops[0].op}")
    lookup_phrase = "What is the commute from Maynard?"
    if can_rule_fallback_plan(lookup_phrase):
        _fail("lookup prompt should not be fallback-eligible")
    _pass("fallback eligibility + rank plan build")


def check_planner_wires_fallback() -> None:
    print("\n4. Planner imports fallback")
    import inspect

    from app import llm_query_planner

    src = inspect.getsource(llm_query_planner.plan_query_with_llm)
    if "plan_with_rule_fallback" not in src:
        _fail("plan_query_with_llm should call plan_with_rule_fallback")
    _pass("llm_query_planner uses rule fallback on failure")


def check_unit_tests() -> None:
    print("\n5. Unit tests (test_plan_fallback)")
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "tests.test_plan_fallback", "-v"],
        cwd=str(SERVICE_ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        _fail("tests.test_plan_fallback failed")
    _pass("unittest tests.test_plan_fallback")


def main() -> None:
    print("=== Phase 2 Step 3: QueryPlan contract + fallback ===\n")
    check_docs()
    check_contract_module()
    check_fallback_module()
    check_planner_wires_fallback()
    check_unit_tests()
    print("\n=== Phase 2 Step 3 verification: PASSED ===")
    print("Docs: agent_service/docs/PLAN_CONTRACT.md")


if __name__ == "__main__":
    main()
