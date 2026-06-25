"""Phase 5 tests — answer generation and validation (offline)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.llm_answer import (  # noqa: E402
    should_use_answer_llm,
    template_answer_from_execution,
    validate_answer_against_context,
)
from app.plan_executor import ExecutionResult, ExecutionStatus, execute_plan  # noqa: E402
from app.query_plan import validate_plan  # noqa: E402


class TestLlmAnswer(unittest.TestCase):
    def test_should_not_use_llm_on_not_found(self) -> None:
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
        execution = execute_plan(plan)
        self.assertEqual(execution.status, ExecutionStatus.NOT_FOUND)
        self.assertFalse(should_use_answer_llm(execution))

    def test_template_from_lookup_snippets(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "Maynard", "field": "commute"}],
                    }
                ]
            }
        )
        execution = execute_plan(plan)
        text = template_answer_from_execution(execution)
        self.assertIn("Maynard", text)
        self.assertIn("suburbs.json", text)

    def test_validate_rejects_invented_price(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "Acton", "field": "price"}],
                    }
                ]
            }
        )
        execution = execute_plan(plan)
        bad_answer = "Acton homes are $999,999,999 according to our data."
        result = validate_answer_against_context(bad_answer, execution)
        self.assertFalse(result.valid)

    def test_validate_accepts_context_price(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "Acton", "field": "price"}],
                    }
                ]
            }
        )
        execution = execute_plan(plan)
        items = execution.ops_results[0].data["items"]
        price = items[0]["values"].get("latest_home_price")
        if price is None:
            self.skipTest("Acton price missing in dataset")
        good = f"Acton's median home price is ${int(price):,}."
        result = validate_answer_against_context(good, execution)
        self.assertTrue(result.valid)


class TestWestfordSummary(unittest.TestCase):
    def test_open_westford_summary_no_internal_wording(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [{"town": "Westford", "field": "summary"}],
                    }
                ]
            }
        )
        execution = execute_plan(plan)
        self.assertEqual(execution.status, ExecutionStatus.OK)
        snippets = execution.ops_results[0].data.get("snippets") or []
        self.assertTrue(snippets)
        text = template_answer_from_execution(execution)
        combined = f"{snippets[0]} {text}".lower()
        self.assertIn("westford", combined)
        self.assertNotIn("execution payload", combined)
        self.assertNotIn("summary fields", combined)
        self.assertTrue(
            any(token in combined for token in ("price", "school", "dataset", "located")),
            combined,
        )


class TestCompareCommuteDestinationNarration(unittest.TestCase):
    def test_compare_non_boston_destination_in_answer_context(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "compare",
                        "towns": ["Shrewsbury", "Framingham", "Marlborough"],
                        "commute_destination_town": "Cambridge",
                    }
                ]
            }
        )
        execution = execute_plan(plan)
        self.assertIn(
            execution.status,
            {ExecutionStatus.OK, ExecutionStatus.PARTIAL},
        )
        ctx = execution.answer_context
        self.assertEqual(ctx.get("commute_destination_label"), "Cambridge")
        text = template_answer_from_execution(execution)
        self.assertIn("Cambridge", text)
        self.assertNotIn("commute comparison for drive times to boston", text.lower())
        self.assertNotRegex(
            text.lower(),
            r"drive times to (south station|boston)",
        )


class TestQueryAgentOffline(unittest.IsolatedAsyncioTestCase):
    async def test_unsupported_uses_refusal_not_answer_llm(self) -> None:
        from app.query_agent import handle_query_v2

        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "unsupported",
                        "category": "live_market",
                        "reason": "User asked for Zillow listings.",
                    }
                ]
            }
        )
        with patch("app.query_agent.query_agent_available", return_value=True):
            with patch("app.query_agent.plan_query_with_llm", return_value=plan):
                with patch(
                    "app.plan_normalizer.normalize_planned_query",
                    return_value=plan,
                ):
                    payload = await handle_query_v2("show me zillow listings now")

        self.assertEqual(payload["execution_status"], "blocked")
        self.assertEqual(payload.get("trust_gate"), "unsupported_live_market")
        self.assertFalse(payload.get("used_answer_llm"))
        final = payload["response"]["final_recommendation"].lower()
        self.assertTrue("zillow" in final or "live" in final or "listing" in final)


if __name__ == "__main__":
    unittest.main()
