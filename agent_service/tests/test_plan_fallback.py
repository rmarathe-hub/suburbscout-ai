"""Tests for rule-based QueryPlan fallback (Phase 2 Step 3)."""

from __future__ import annotations

import unittest

from app.plan_contract import CANONICAL_PLAN_EXAMPLES
from app.plan_fallback import (
    build_rule_fallback_plan,
    can_rule_fallback_plan,
    plan_with_rule_fallback,
)
from app.plan_normalizer import normalize_planned_query
from app.query_plan import CompareOp, LookupOp, MembershipOp, QueryPlan, RankOp, UnsupportedOp


class TestPlanFallback(unittest.TestCase):
    def test_can_fallback_rank_prompt(self) -> None:
        self.assertTrue(
            can_rule_fallback_plan("Safe suburb under $900k with good schools")
        )

    def test_cannot_fallback_lookup(self) -> None:
        self.assertFalse(can_rule_fallback_plan("What is the commute from Maynard?"))

    def test_cannot_fallback_compare(self) -> None:
        self.assertFalse(
            can_rule_fallback_plan("Compare Acton and Framingham on safety")
        )

    def test_build_fallback_rank_plan(self) -> None:
        plan = build_rule_fallback_plan("Safe suburb under $900k with good schools")
        self.assertEqual(len(plan.ops), 1)
        self.assertIsInstance(plan.ops[0], RankOp)
        self.assertIsNotNone(plan.ops[0].preferences.budget_max)

    def test_plan_with_fallback_applies_normalizer(self) -> None:
        plan = plan_with_rule_fallback(
            "Waterfront towns in the dataset under $1.2M",
            apply_normalizer=True,
        )
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertTrue(any(isinstance(o, RankOp) for o in plan.ops))


class TestPlanContractExamples(unittest.TestCase):
    """Offline checks that normalizer maps canonical phrases toward expected ops."""

    def test_lookup_example(self) -> None:
        phrase = CANONICAL_PLAN_EXAMPLES[0].phrase
        raw = QueryPlan(
            ops=[
                LookupOp.model_validate(
                    {
                        "op": "lookup",
                        "items": [{"town": "Maynard", "field": "commute"}],
                    }
                )
            ]
        )
        plan = normalize_planned_query(phrase, raw)
        ops = [o.op for o in plan.ops]
        self.assertIn("lookup", ops)

    def test_compare_example(self) -> None:
        phrase = CANONICAL_PLAN_EXAMPLES[1].phrase
        raw = QueryPlan(
            ops=[
                CompareOp.model_validate(
                    {
                        "op": "compare",
                        "towns": ["Acton", "Framingham"],
                        "columns": ["school_score", "safety_score"],
                    }
                )
            ]
        )
        plan = normalize_planned_query(phrase, raw)
        self.assertEqual(plan.ops[0].op, "compare")

    def test_unsupported_neighborhood_example(self) -> None:
        phrase = CANONICAL_PLAN_EXAMPLES[4].phrase
        raw = QueryPlan(
            ops=[
                UnsupportedOp.model_validate(
                    {
                        "op": "unsupported",
                        "category": "neighborhood",
                        "reason": "neighborhood-level detail",
                    }
                )
            ]
        )
        plan = normalize_planned_query(phrase, raw)
        self.assertEqual(plan.ops[0].op, "unsupported")

    def test_rank_fallback_matches_contract(self) -> None:
        phrase = CANONICAL_PLAN_EXAMPLES[2].phrase
        plan = build_rule_fallback_plan(phrase)
        self.assertEqual(plan.ops[0].op, "rank")


if __name__ == "__main__":
    unittest.main()
