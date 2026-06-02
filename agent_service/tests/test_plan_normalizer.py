"""Tests for plan_normalizer repairs."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.plan_normalizer import normalize_planned_query  # noqa: E402
from app.query_plan import (  # noqa: E402
    LookupFieldKind,
    LookupOp,
    MembershipOp,
    RankOp,
    SemanticSearchOp,
    UnsupportedOp,
    validate_plan,
)


class TestPlanNormalizer(unittest.TestCase):
    def test_membership_not_summary_lookup(self) -> None:
        q = "Would Boxford be accepted as a town name?"
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "Boxford", "field": "summary"}],
                    }
                ]
            }
        )
        out = normalize_planned_query(q, plan)
        self.assertEqual(len(out.ops), 1)
        self.assertIsInstance(out.ops[0], MembershipOp)
        self.assertEqual(out.ops[0].town, "Boxford")

    def test_coastal_becomes_rank(self) -> None:
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
        self.assertIsInstance(out.ops[0], RankOp)
        self.assertTrue(out.ops[0].preferences.requires_coastal)

    def test_inverted_school_prefs(self) -> None:
        q = "Affordable towns, weaker schools acceptable"
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "rank",
                        "preferences": {
                            "budget_max": 700000,
                            "school_priority": "high",
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

    def test_membership_strips_compare(self) -> None:
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
        self.assertEqual(len(out.ops), 1)
        self.assertIsInstance(out.ops[0], MembershipOp)

    def test_show_me_zillow_not_pull_up_lookup(self) -> None:
        q = "Show me current Zillow listings in Newton right now"
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "rank",
                        "preferences": {},
                        "limit": 5,
                    }
                ]
            }
        )
        out = normalize_planned_query(q, plan)
        self.assertEqual(len(out.ops), 1)
        self.assertIsInstance(out.ops[0], UnsupportedOp)
        self.assertEqual(out.ops[0].category.value, "live_market")

    def test_pull_up_lookup_not_membership(self) -> None:
        q = "Pull up Chelmsfrd."
        plan = validate_plan({"ops": [{"op": "membership", "town": "Chelmsford"}]})
        out = normalize_planned_query(q, plan)
        self.assertEqual(len(out.ops), 1)
        self.assertIsInstance(out.ops[0], LookupOp)

    def test_inverted_crime_rank(self) -> None:
        q = "Crime can be higher if homes are cheap."
        plan = validate_plan(
            {"ops": [{"op": "unsupported", "category": "lifestyle", "reason": "x"}]}
        )
        out = normalize_planned_query(q, plan)
        self.assertEqual(len(out.ops), 1)
        self.assertIsInstance(out.ops[0], RankOp)
        self.assertTrue(out.ops[0].preferences.allow_low_safety)

    def test_neighborhood_before_pull_up(self) -> None:
        q = "Which neighborhood in Brookline is best for kids?"
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "Brookline", "field": "summary"}],
                    }
                ]
            }
        )
        out = normalize_planned_query(q, plan)
        self.assertEqual(len(out.ops), 1)
        self.assertIsInstance(out.ops[0], UnsupportedOp)
        self.assertEqual(out.ops[0].category.value, "neighborhood")

    def test_commute_lookup_not_downgraded_to_membership(self) -> None:
        q = "What is the commute from Maynard?"
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "membership",
                        "town": "Maynard",
                    }
                ]
            }
        )
        out = normalize_planned_query(q, plan)
        self.assertEqual(len(out.ops), 1)
        self.assertIsInstance(out.ops[0], LookupOp)
        self.assertEqual(out.ops[0].items[0].field, LookupFieldKind.COMMUTE.value)

    def test_open_reading_pull_up_town(self) -> None:
        q = "Open Reading."
        plan = validate_plan({"ops": [{"op": "membership", "town": "North Reading"}]})
        out = normalize_planned_query(q, plan)
        self.assertIsInstance(out.ops[0], LookupOp)
        self.assertEqual(out.ops[0].items[0].town, "Reading")

    def test_open_north_reading_pull_up_town(self) -> None:
        q = "Open North Reading."
        plan = validate_plan({"ops": [{"op": "membership", "town": "Reading"}]})
        out = normalize_planned_query(q, plan)
        self.assertIsInstance(out.ops[0], LookupOp)
        self.assertEqual(out.ops[0].items[0].town, "North Reading")

    def test_zillow_live_market_unsupported(self) -> None:
        q = "Show me current Zillow listings in Newton right now"
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "Newton", "field": "price"}],
                    }
                ]
            }
        )
        out = normalize_planned_query(q, plan)
        self.assertIsInstance(out.ops[0], UnsupportedOp)
        self.assertEqual(out.ops[0].category.value, "live_market")

    def test_vibe_injects_semantic_search(self) -> None:
        q = "Give me a Brookline-like feel with lower prices."
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "rank",
                        "preferences": {"budget_max": 800000},
                        "limit": 5,
                    }
                ]
            }
        )
        out = normalize_planned_query(q, plan)
        self.assertIsInstance(out.ops[0], SemanticSearchOp)
        self.assertIsInstance(out.ops[1], RankOp)
        self.assertTrue(out.ops[1].use_semantic_candidates)


if __name__ == "__main__":
    unittest.main()
