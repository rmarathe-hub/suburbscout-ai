"""Phase 6 tests — plan trust gates and semantic→rank hybrid execution."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.plan_executor import execute_plan  # noqa: E402
from app.plan_trust_gates import evaluate_plan_trust_gate, plan_to_query_route  # noqa: E402
from app.query_plan import validate_plan  # noqa: E402


class TestPlanTrustGates(unittest.TestCase):
    def test_plan_to_route_multi_lookup(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "lookup",
                        "items": [
                            {"town": "Maynard", "field": "commute"},
                            {"town": "Newton", "field": "price"},
                        ],
                    }
                ]
            }
        )
        route = plan_to_query_route("commute Maynard and price Newton", plan)
        self.assertEqual(route.intent, "lookup_multi_town")
        self.assertEqual(len(route.lookup_specs), 2)

    def test_unsupported_compare_field_blocks(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "compare",
                        "towns": ["Newton", "Needham"],
                        "columns": ["latest_home_price"],
                    }
                ]
            }
        )
        gate = evaluate_plan_trust_gate(
            "Which is more walkable, Newton or Needham?",
            plan,
        )
        self.assertIsNotNone(gate)
        assert gate is not None
        self.assertTrue(gate.blocks_pipeline)
        self.assertEqual(gate.gate_type, "unsupported_compare")

    def test_semantic_then_rank_uses_candidates(self) -> None:
        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "semantic_search",
                        "query_text": "affordable family suburb",
                        "top_k": 10,
                    },
                    {
                        "op": "rank",
                        "preferences": {"budget_max": 900000},
                        "limit": 3,
                    },
                ]
            }
        )
        mock_semantic = AsyncMock(
            return_value={
                "query": "affordable family suburb",
                "candidate_town_names": ["Acton", "Maynard", "Concord"],
                "candidates": [],
            }
        )
        with patch("app.plan_executor.run_semantic_town_search", mock_semantic):
            result = execute_plan(plan)
        rank_results = [r for r in result.ops_results if r.op == "rank"]
        self.assertEqual(len(rank_results), 1)
        names = rank_results[0].data.get("semantic_candidate_towns") or []
        self.assertIn("Acton", names)


class TestQueryAgentTrustGate(unittest.IsolatedAsyncioTestCase):
    async def test_trust_gate_blocks_before_execute(self) -> None:
        from app.query_agent import handle_query_v2

        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "compare",
                        "towns": ["Newton", "Needham"],
                    }
                ]
            }
        )
        with patch("app.query_agent.query_agent_available", return_value=True):
            with patch("app.query_agent.plan_query_with_llm", return_value=plan):
                payload = await handle_query_v2("Compare Newton vs Needham on walkability")

        self.assertEqual(payload.get("trust_gate"), "unsupported_compare")
        self.assertEqual(payload.get("execution_status"), "blocked")
        self.assertFalse(payload.get("used_answer_llm"))
        self.assertIn("walkab", payload["response"]["final_recommendation"].lower())


if __name__ == "__main__":
    unittest.main()
