"""Phase 4 tests — LLM query planner (offline + optional live)."""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.llm_query_planner import (  # noqa: E402
    plan_from_llm_response,
    planner_available,
    plan_query_with_llm,
)
from app.query_plan import CompareOp, LookupOp, RankOp, UnsupportedOp  # noqa: E402


class TestLlmQueryPlannerOffline(unittest.TestCase):
    def test_plan_from_llm_response_ml01(self) -> None:
        text = json.dumps(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [
                            {"town": "Maynard", "field": "commute"},
                            {"town": "Newton", "field": "price"},
                        ],
                    }
                ],
                "user_intent_summary": "commute and price",
            }
        )
        plan = plan_from_llm_response(text)
        self.assertIsInstance(plan.ops[0], LookupOp)
        self.assertEqual(len(plan.ops[0].items), 2)

    def test_plan_from_llm_response_fenced(self) -> None:
        fenced = """```json
{"ops": [{"op": "compare", "towns": ["Newton", "Needham"]}]}
```"""
        plan = plan_from_llm_response(fenced)
        self.assertIsInstance(plan.ops[0], CompareOp)

    def test_plan_from_llm_response_unsupported(self) -> None:
        text = json.dumps(
            {
                "ops": [
                    {
                        "op": "unsupported",
                        "category": "live_market",
                        "reason": "Zillow listings requested",
                    }
                ]
            }
        )
        plan = plan_from_llm_response(text)
        self.assertIsInstance(plan.ops[0], UnsupportedOp)

    def test_plan_from_llm_response_rank(self) -> None:
        text = json.dumps(
            {
                "ops": [
                    {
                        "op": "rank",
                        "preferences": {"budget_max": 600000, "exclude_towns": ["Sharon"]},
                        "limit": 5,
                    }
                ]
            }
        )
        plan = plan_from_llm_response(text)
        self.assertIsInstance(plan.ops[0], RankOp)
        self.assertEqual(plan.ops[0].preferences.budget_max, 600000)


@unittest.skipUnless(
    planner_available()
    and os.getenv("ENABLE_LIVE_LLM_PLANNER", "").lower() in ("1", "true", "yes"),
    "set ENABLE_LIVE_LLM_PLANNER=1 to run live Azure planner test",
)
class TestLlmQueryPlannerLive(unittest.IsolatedAsyncioTestCase):
    async def test_plan_maynard_commute(self) -> None:
        plan = await plan_query_with_llm("What is the commute from Maynard?")
        self.assertGreaterEqual(len(plan.ops), 1)
        first = plan.ops[0]
        if isinstance(first, LookupOp):
            towns = {i.town.lower() for i in first.items}
            self.assertIn("maynard", towns)


if __name__ == "__main__":
    unittest.main()
