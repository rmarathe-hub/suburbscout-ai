"""Tests for plan_normalizer repairs (Phase 9 — plan-JSON only)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.plan_normalizer import normalize_planned_query  # noqa: E402
from app.query_plan import (  # noqa: E402
    CompareOp,
    LookupOp,
    MembershipOp,
    RankOp,
    SemanticSearchOp,
    UnsupportedOp,
    validate_plan,
)


class TestPlanNormalizer(unittest.TestCase):
    def test_membership_passthrough(self) -> None:
        """Planner membership op is preserved (no query-text rewrite)."""
        q = "Would Boxford be accepted as a town name?"
        plan = validate_plan({"ops": [{"op": "membership", "town": "Boxford"}]})
        out = normalize_planned_query(q, plan)
        self.assertEqual(len(out.ops), 1)
        self.assertIsInstance(out.ops[0], MembershipOp)
        self.assertEqual(out.ops[0].town, "Boxford")

    def test_coastal_semantic_passthrough(self) -> None:
        """Planner semantic op is not rewritten to coastal rank from query text."""
        q = "Show me waterfront towns in the dataset"
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "semantic_search",
                        "query_text": "waterfront coastal",
                        "top_k": 10,
                    }
                ]
            }
        )
        out = normalize_planned_query(q, plan)
        self.assertEqual(len(out.ops), 1)
        self.assertIsInstance(out.ops[0], SemanticSearchOp)

    def test_inverted_school_prefs_from_planner(self) -> None:
        q = "Affordable towns, weaker schools acceptable"
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "rank",
                        "preferences": {
                            "budget_max": 700000,
                            "deprioritize_schools": True,
                            "school_priority": "low",
                        },
                        "limit": 10,
                    }
                ]
            }
        )
        out = normalize_planned_query(q, plan)
        rank = out.ops[0]
        assert isinstance(rank, RankOp)
        self.assertTrue(rank.preferences.deprioritize_schools)
        self.assertNotEqual(rank.preferences.school_priority, "high")

    def test_placeholder_town_rejected(self) -> None:
        from app.query_plan import PlanValidationError, assert_valid_plan_town_name

        with self.assertRaises(PlanValidationError):
            assert_valid_plan_town_name("town_name_12")

    def test_semantic_rank_forces_candidates(self) -> None:
        q = "Find suburbs similar to Hingham but less expensive."
        plan = validate_plan(
            {
                "ops": [
                    {"op": "semantic_search", "query_text": "Hingham similar", "top_k": 10},
                    {
                        "op": "rank",
                        "preferences": {
                            "similar_to_town": "vibe",
                            "unknown_towns": ["Hingham-like"],
                        },
                        "limit": 5,
                        "use_semantic_candidates": False,
                    },
                ]
            }
        )
        out = normalize_planned_query(q, plan)
        self.assertEqual(len(out.ops), 2)
        rank = out.ops[1]
        assert isinstance(rank, RankOp)
        self.assertTrue(rank.use_semantic_candidates)
        self.assertNotIn("Hingham-like", rank.preferences.unknown_towns or [])

    def test_membership_multi_op_passthrough(self) -> None:
        """Extra compare op is not stripped by query-text membership detection."""
        q = "Would North Readin resolve correctly?"
        plan = validate_plan(
            {
                "ops": [
                    {"op": "membership", "town": "North Reading"},
                    {"op": "compare", "towns": ["North Reading", "Reading"]},
                ]
            }
        )
        out = normalize_planned_query(q, plan)
        self.assertEqual(len(out.ops), 2)

    def test_unsupported_passthrough(self) -> None:
        q = "Show me current Zillow listings in Newton right now"
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "unsupported",
                        "category": "live_market",
                        "reason": "live listings",
                    }
                ]
            }
        )
        out = normalize_planned_query(q, plan)
        self.assertIsInstance(out.ops[0], UnsupportedOp)

    def test_lookup_passthrough(self) -> None:
        q = "Pull up Chelmsfrd."
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "Chelmsford", "field": "summary"}],
                    }
                ]
            }
        )
        out = normalize_planned_query(q, plan)
        self.assertIsInstance(out.ops[0], LookupOp)

    def test_lookup_to_compare_from_compare_towns_intent(self) -> None:
        """E21-style: planner put compare_towns but emitted lookup."""
        q = "Compare Lexington and Bedford on schools, safety, and price."
        plan = validate_plan(
            {
                "commute_intent": {
                    "commute_destination_town": "unsupported",
                    "commute_context": "unsupported",
                    "compare_towns": ["Lexington", "Bedford"],
                },
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "Lexington", "field": "price"}],
                    }
                ],
            }
        )
        out = normalize_planned_query(q, plan)
        self.assertEqual(len(out.ops), 1)
        self.assertIsInstance(out.ops[0], CompareOp)
        assert isinstance(out.ops[0], CompareOp)
        self.assertEqual(out.ops[0].towns, ["Lexington", "Bedford"])
        cols = out.ops[0].columns or []
        self.assertTrue("price" in cols or "latest_home_price" in cols)
        self.assertIsNotNone(out.commute_intent)
        self.assertEqual(out.commute_intent.commute_context.value, "default_boston")

    def test_lookup_without_compare_intent_stays_lookup(self) -> None:
        """No compare_towns in plan — lookup is not rewritten from query entities."""
        q = "Compare Lexington and Bedford on schools, safety, and price."
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "Lexington", "field": "price"}],
                    }
                ],
            }
        )
        out = normalize_planned_query(q, plan)
        self.assertIsInstance(out.ops[0], LookupOp)


if __name__ == "__main__":
    unittest.main()
