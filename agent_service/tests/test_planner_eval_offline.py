"""Offline tests for planner eval fixtures (Layer 1, no LLM)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.evals.planner_eval_scoring import plan_from_dict, score_plan_against_expect  # noqa: E402

MANIFEST = SERVICE_ROOT / "app" / "evals" / "planner_eval_100.json"


class TestPlannerEvalOffline(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MANIFEST.exists():
            raise unittest.SkipTest("Run scripts/generate_planner_eval_100.py first")
        cls.payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.cases = cls.payload.get("cases") or []

    def test_all_fixtures_score_100_percent(self) -> None:
        failures: list[str] = []
        for case in self.cases:
            plan_path = SERVICE_ROOT / case["plan_file"]
            plan = plan_from_dict(json.loads(plan_path.read_text(encoding="utf-8")))
            score = score_plan_against_expect(plan, case.get("expect") or {})
            if not score["passed"]:
                failures.append(f"{case['id']}: {score['failure_reasons']}")

        self.assertEqual(len(self.cases), 100)
        if failures:
            self.fail("\n".join(failures[:20]))


if __name__ == "__main__":
    unittest.main()
