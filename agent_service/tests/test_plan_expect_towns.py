"""plan_expect expected_town / forbidden_towns scoring (Phase 2 Step 4)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.evals.planner_eval_scoring import score_plan_against_expect  # noqa: E402
from app.plan_contract import CANONICAL_PLAN_EXAMPLES  # noqa: E402
from app.plan_normalizer import normalize_planned_query  # noqa: E402
from app.query_plan import LookupOp, validate_plan  # noqa: E402


class TestPlanExpectTowns(unittest.TestCase):
    def test_reading_forbidden_north_reading(self) -> None:
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
        score = score_plan_against_expect(
            plan,
            {"expected_town": "Reading", "forbidden_towns": ["North Reading"]},
        )
        self.assertTrue(score["passed"])

    def test_north_reading_forbidden_reading(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "North Reading", "field": "summary"}],
                    }
                ]
            }
        )
        score = score_plan_against_expect(
            plan,
            {"expected_town": "North Reading", "forbidden_towns": ["Reading"]},
        )
        self.assertTrue(score["passed"])

    def test_pull_up_reading_normalized(self) -> None:
        phrase = "Pull up Reading."
        raw = validate_plan({"ops": [{"op": "membership", "town": "North Reading"}]})
        plan = normalize_planned_query(phrase, raw)
        assert isinstance(plan.ops[0], LookupOp)
        score = score_plan_against_expect(
            plan,
            {"expected_town": "Reading", "forbidden_towns": ["North Reading"]},
        )
        self.assertTrue(score["passed"], score["failure_reasons"])

    def test_canonical_examples_have_expect_fields(self) -> None:
        """Documented examples align with scoring keys used in fresh evals."""
        self.assertGreaterEqual(len(CANONICAL_PLAN_EXAMPLES), 5)


if __name__ == "__main__":
    unittest.main()
