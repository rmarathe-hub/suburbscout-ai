"""Phase 2 tests — plan executor against suburbs.json."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.plan_executor import ExecutionStatus, execute_plan  # noqa: E402
from app.query_plan import validate_plan  # noqa: E402


class TestPlanExecutor(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from app.config import SUBURBS_JSON_PATH

        if not SUBURBS_JSON_PATH.exists():
            raise unittest.SkipTest("suburbs.json missing — run build_suburbs_dataset.py")

    def _run_fixture(self, name: str):
        path = SERVICE_ROOT / "tests" / "fixtures" / "plans" / name
        plan = validate_plan(json.loads(path.read_text(encoding="utf-8")))
        return execute_plan(plan)

    def test_lookup_maynard_commute_ok(self) -> None:
        result = self._run_fixture("lookup_maynard_commute.json")
        self.assertIn(result.status, (ExecutionStatus.OK, ExecutionStatus.PARTIAL))
        lookup = result.ops_results[0]
        self.assertEqual(lookup.op, "lookup")
        items = lookup.data["items"]
        self.assertTrue(items[0]["found"])
        self.assertEqual(items[0]["field"], "commute")
        self.assertIn("drive_minutes_to_boston", items[0]["values"])

    def test_rank_returns_matches(self) -> None:
        result = self._run_fixture("rank_budget_commute.json")
        self.assertEqual(result.status, ExecutionStatus.OK)
        matches = result.ops_results[0].data.get("top_matches") or []
        self.assertGreaterEqual(len(matches), 1)
        self.assertIsNotNone(matches[0].get("name"))

    def test_compare_newton_brookline_ok(self) -> None:
        result = self._run_fixture("compare_newton_brookline.json")
        self.assertEqual(result.status, ExecutionStatus.OK)
        table = result.ops_results[0].data.get("comparison_table") or []
        self.assertGreaterEqual(len(table), 2)
        names = {row["town"] for row in table}
        self.assertIn("Newton", names)
        self.assertIn("Brookline", names)

    def test_lookup_unknown_town_not_found(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "Brooklyn, MA", "field": "school"}],
                    }
                ]
            }
        )
        result = execute_plan(plan)
        self.assertEqual(result.status, ExecutionStatus.NOT_FOUND)
        self.assertEqual(result.message_code, "town_not_in_dataset")

    def test_unsupported_out_of_scope(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "unsupported",
                        "category": "live_market",
                        "reason": "User asked for current Zillow listings.",
                    }
                ]
            }
        )
        result = execute_plan(plan)
        self.assertEqual(result.status, ExecutionStatus.OUT_OF_SCOPE)
        self.assertIn("Zillow", result.refusal_message())

    def test_rank_no_rows_impossible_budget(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "rank",
                        "preferences": {
                            "budget_max": 1,
                            "max_commute_minutes": 1,
                            "require_housing_for_budget": True,
                        },
                        "limit": 5,
                    }
                ]
            }
        )
        result = execute_plan(plan)
        self.assertEqual(result.status, ExecutionStatus.NO_ROWS)
        self.assertEqual(result.message_code, "no_matching_towns")

    def test_answer_context_has_ops(self) -> None:
        result = self._run_fixture("lookup_maynard_commute.json")
        self.assertIn("ops", result.answer_context)
        self.assertEqual(result.answer_context["execution_status"], result.status.value)


if __name__ == "__main__":
    unittest.main()
