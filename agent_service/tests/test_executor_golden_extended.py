"""Extended executor golden tests including no_rows and semantic→rank."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from tests.golden_plan_assertions import (  # noqa: E402
    assert_golden_case,
    load_manifest,
    load_plan_file,
    run_golden_case,
)


class TestExecutorGoldenExtended(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from app.config import SUBURBS_JSON_PATH

        if not SUBURBS_JSON_PATH.exists():
            raise unittest.SkipTest("suburbs.json missing")
        cls.cases = {
            c["id"]: c
            for c in load_manifest().get("cases") or []
            if c["id"].startswith("executor_")
        }

    def test_rank_no_rows(self) -> None:
        case = self.cases["executor_rank_no_rows"]
        result = run_golden_case(case)
        failures = assert_golden_case(case, result)
        self.assertEqual(failures, [])

    def test_semantic_then_rank_uses_candidates(self) -> None:
        case = self.cases["executor_semantic_rank_offline"]
        plan_data = load_plan_file(case["plan_file"])
        from app.plan_executor import execute_plan

        mock_semantic = AsyncMock(
            return_value={
                "query": "quiet affordable family suburb",
                "candidate_town_names": ["Acton", "Maynard"],
                "candidates": [],
            }
        )
        with patch("app.plan_executor.run_semantic_town_search", mock_semantic):
            result = execute_plan(plan_data)
        failures = assert_golden_case(case, result)
        rank_ops = [r for r in result.ops_results if r.op == "rank"]
        self.assertTrue(rank_ops)
        self.assertIn("Acton", rank_ops[0].data.get("semantic_candidate_towns") or [])
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
