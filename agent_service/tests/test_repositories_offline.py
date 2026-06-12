"""Offline unit tests for Phase 3A repository helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.repositories import _merge_session_preferences  # noqa: E402


class TestSessionPreferenceMerge(unittest.TestCase):
    def test_follow_up_commute_priority(self) -> None:
        merged = _merge_session_preferences(
            {"school_priority": "high", "commute_priority": "medium"},
            None,
            "Make commute more important than schools.",
        )
        self.assertEqual(merged["commute_priority"], "high")
        self.assertEqual(merged["school_priority"], "medium")

    def test_rank_plan_preferences_merged(self) -> None:
        plan = {
            "ops": [
                {
                    "op": "rank",
                    "preferences": {"budget_max": 900000, "safety_priority": "high"},
                }
            ]
        }
        merged = _merge_session_preferences({}, plan, "Find safe towns under 900k")
        self.assertEqual(merged["budget_max"], 900000)
        self.assertEqual(merged["safety_priority"], "high")


if __name__ == "__main__":
    unittest.main()
