"""Tests for LLM-first plan preference merge."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.commute_intent import CommuteContext, CommuteIntent  # noqa: E402
from app.plan_preferences import merge_rank_preferences  # noqa: E402
from app.schemas import Preferences  # noqa: E402


class TestMergeRankPreferences(unittest.TestCase):
    def test_planner_fields_not_overridden_by_empty_fallback(self) -> None:
        planner = Preferences(max_commute_minutes=30, budget_max=850_000, safety_priority="high")
        merged = merge_rank_preferences(
            "Keep me below 30 minutes to Somerville and under 850k.",
            planner,
            commute_intent=CommuteIntent(
                commute_destination_town="Somerville",
                commute_context=CommuteContext.DESTINATION_TOWN,
            ),
        )
        self.assertEqual(merged.max_commute_minutes, 30)
        self.assertEqual(merged.budget_max, 850_000)
        self.assertEqual(merged.safety_priority, "high")

    def test_strips_absurd_budget_with_commute_intent(self) -> None:
        planner = Preferences(budget_max=30_000, max_commute_minutes=30)
        merged = merge_rank_preferences(
            "Quincy drive under 30, affordable towns only.",
            planner,
            commute_intent=CommuteIntent(
                commute_destination_town="Quincy",
                commute_context=CommuteContext.DESTINATION_TOWN,
            ),
            regex_fallback=False,
        )
        self.assertIsNone(merged.budget_max)
        self.assertEqual(merged.max_commute_minutes, 30)

    def test_regex_fallback_fills_only_missing(self) -> None:
        planner = Preferences(safety_priority="high")
        merged = merge_rank_preferences(
            "Find towns with good schools within 30 minutes of Waltham.",
            planner,
            regex_fallback=True,
        )
        self.assertEqual(merged.safety_priority, "high")
        self.assertEqual(merged.max_commute_minutes, 30)
        self.assertEqual(merged.commute_destination_town, "Waltham")


class TestValidatePlannerPlanSemantics(unittest.TestCase):
    def test_rejects_minutes_as_budget(self) -> None:
        from app.plan_preferences import validate_planner_plan_semantics
        from app.query_plan import PlanValidationError, QueryPlan, RankOp

        plan = QueryPlan(
            commute_intent=CommuteIntent(
                commute_destination_town="Quincy",
                commute_context=CommuteContext.DESTINATION_TOWN,
            ),
            ops=[
                RankOp(
                    preferences=Preferences(budget_max=30_000, max_commute_minutes=30),
                    limit=10,
                )
            ],
        )
        with self.assertRaises(PlanValidationError):
            validate_planner_plan_semantics(plan)

    def test_requires_max_commute_when_intent_has_cap(self) -> None:
        from app.plan_preferences import validate_planner_plan_semantics
        from app.query_plan import PlanValidationError, QueryPlan, RankOp

        plan = QueryPlan(
            commute_intent=CommuteIntent(
                commute_destination_town="Salem",
                commute_context=CommuteContext.DESTINATION_TOWN,
                max_commute_minutes=35,
            ),
            ops=[RankOp(preferences=Preferences(safety_priority="high"), limit=10)],
        )
        with self.assertRaises(PlanValidationError):
            validate_planner_plan_semantics(plan)

    def test_sync_intent_cap_to_rank_prefs(self) -> None:
        planner = Preferences(affordability_priority="high")
        merged = merge_rank_preferences(
            "Waltham below 25 min commute and affordable.",
            planner,
            commute_intent=CommuteIntent(
                commute_destination_town="Waltham",
                commute_context=CommuteContext.DESTINATION_TOWN,
                max_commute_minutes=25,
            ),
        )
        self.assertEqual(merged.max_commute_minutes, 25)

    def test_plain_compare_requires_default_boston(self) -> None:
        from app.plan_preferences import validate_planner_plan_semantics
        from app.query_plan import CompareOp, PlanValidationError, QueryPlan

        plan = QueryPlan(
            commute_intent=CommuteIntent(
                commute_destination_town="unsupported",
                commute_context=CommuteContext.UNSUPPORTED,
            ),
            ops=[CompareOp(towns=["Newton", "Wellesley"], columns=["school_score", "price"])],
        )
        with self.assertRaises(PlanValidationError):
            validate_planner_plan_semantics(plan)


if __name__ == "__main__":
    unittest.main()
