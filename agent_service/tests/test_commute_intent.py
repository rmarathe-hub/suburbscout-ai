"""Tests for LLM-proposed commute intent with Python validation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.commute_intent import (  # noqa: E402
    CommuteContext,
    CommuteIntent,
    apply_commute_intent_to_plan,
    resolve_commute_intent,
)
from app.commute_destination import detect_commute_destination_regex  # noqa: E402
from app.config import SUBURBS_JSON_PATH  # noqa: E402
from app.plan_trust_gates import evaluate_plan_trust_gate  # noqa: E402
from app.query_plan import validate_plan  # noqa: E402
from app.schemas import Preferences  # noqa: E402


class TestResolveCommuteIntent(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SUBURBS_JSON_PATH.exists():
            raise unittest.SkipTest("suburbs.json missing")

    def test_llm_unsupported_providence_compare(self) -> None:
        intent = CommuteIntent(
            commute_destination_town="Providence",
            commute_context=CommuteContext.UNSUPPORTED,
            compare_towns=["Bedford", "Lexington"],
        )
        resolved = resolve_commute_intent(
            "Compare Bedford and Lexington if my job is in Providence.",
            intent,
        )
        self.assertEqual(resolved.commute_context, CommuteContext.UNSUPPORTED)
        self.assertIsNone(resolved.commute_destination_town)
        self.assertEqual(resolved.compare_towns, ("Bedford", "Lexington"))

    def test_llm_cambridge_rank(self) -> None:
        intent = CommuteIntent(
            commute_destination_town="Cambridge",
            commute_context=CommuteContext.DESTINATION_TOWN,
        )
        resolved = resolve_commute_intent(
            "My job is in Cambridge, and I want safe towns below 900k.",
            intent,
        )
        self.assertEqual(resolved.commute_destination_town, "Cambridge")
        self.assertEqual(resolved.commute_context, CommuteContext.DESTINATION_TOWN)

    def test_regex_fallback_job_in_waltham(self) -> None:
        resolved = resolve_commute_intent("My job is in Waltham and I want schools.")
        self.assertEqual(resolved.commute_destination_town, "Waltham")
        self.assertEqual(resolved.commute_context, CommuteContext.DESTINATION_TOWN)
        self.assertEqual(resolved.source, "regex")

    def test_regex_fallback_commute_into_burlington(self) -> None:
        resolved = resolve_commute_intent(
            "I have to commute into Burlington; show me towns with strong schools."
        )
        self.assertEqual(resolved.commute_destination_town, "Burlington")

    def test_regex_shorthand_waltham_commute(self) -> None:
        resolved = resolve_commute_intent(
            "Waltham commute under 25 minutes, good schools, under 1M."
        )
        self.assertEqual(resolved.commute_destination_town, "Waltham")

    def test_apply_to_compare_plan(self) -> None:
        plan = validate_plan(
            {
                "commute_intent": {
                    "commute_destination_town": "Cambridge",
                    "commute_context": "destination_town",
                    "compare_towns": ["Acton", "Burlington"],
                },
                "ops": [{"op": "compare", "towns": ["Acton", "Burlington"]}],
            }
        )
        updated = apply_commute_intent_to_plan(
            "Acton or Burlington if my office is in Cambridge?",
            plan,
        )
        compare = updated.ops[0]
        self.assertEqual(compare.commute_destination_town, "Cambridge")


class TestCommuteIntentTrustGates(unittest.TestCase):
    def test_providence_compare_blocked_with_llm_intent(self) -> None:
        plan = validate_plan(
            {
                "commute_intent": {
                    "commute_destination_town": "Providence",
                    "commute_context": "unsupported",
                    "compare_towns": ["Bedford", "Lexington"],
                },
                "ops": [{"op": "compare", "towns": ["Bedford", "Lexington"]}],
            }
        )
        gate = evaluate_plan_trust_gate(
            "Compare Bedford and Lexington if my job is in Providence.",
            plan,
        )
        self.assertIsNotNone(gate)
        self.assertEqual(gate.gate_type, "commute_destination_compare")

    def test_somerville_commute_into_not_multi_compare(self) -> None:
        plan = validate_plan(
            {
                "commute_intent": {
                    "commute_destination_town": "Somerville",
                    "commute_context": "destination_town",
                    "compare_towns": ["Westford", "Reading"],
                },
                "ops": [{"op": "compare", "towns": ["Westford", "Reading"]}],
            }
        )
        gate = evaluate_plan_trust_gate(
            "Westford vs Reading for commuting into Somerville.",
            plan,
        )
        self.assertIsNone(gate)

    def test_regex_only_providence_compare_blocked(self) -> None:
        plan = validate_plan(
            {
                "ops": [{"op": "compare", "towns": ["Bedford", "Lexington"]}],
            }
        )
        gate = evaluate_plan_trust_gate(
            "Compare Bedford and Lexington if my job is in Providence.",
            plan,
        )
        self.assertIsNotNone(gate)
        self.assertEqual(gate.gate_type, "commute_destination_compare")


class TestRegexFallbackPatterns(unittest.TestCase):
    def test_job_is_in_cambridge(self) -> None:
        dest = detect_commute_destination_regex(
            "My job is in Cambridge, and I want safe towns below 900k."
        )
        self.assertEqual(dest.destination_town, "Cambridge")


class TestLlmFirstCommuteIntent(unittest.TestCase):
    def test_plain_compare_vague_destination_defaults_boston(self) -> None:
        intent = CommuteIntent(
            commute_destination_town="that place",
            commute_context=CommuteContext.UNSUPPORTED,
        )
        resolved = resolve_commute_intent(
            "Compare Brookline and Cambridge on price and schools.",
            intent,
        )
        self.assertTrue(resolved.is_default)
        self.assertIsNone(resolved.commute_destination_town)

    def test_providence_stays_unsupported(self) -> None:
        intent = CommuteIntent(
            commute_destination_town="Providence",
            commute_context=CommuteContext.UNSUPPORTED,
            compare_towns=["Acton", "Burlington"],
        )
        resolved = resolve_commute_intent(
            "Acton vs Burlington if I work in Providence.",
            intent,
        )
        self.assertEqual(resolved.commute_context, CommuteContext.UNSUPPORTED)
        self.assertIn("Providence", resolved.label)

    @classmethod
    def setUpClass(cls) -> None:
        if not SUBURBS_JSON_PATH.exists():
            raise unittest.SkipTest("suburbs.json missing")

    def test_rank_enforces_dynamic_max_commute(self) -> None:
        from unittest.mock import patch

        from app.ranking import rank_suburbs

        prefs = Preferences(
            max_commute_minutes=30,
            commute_destination_town="Somerville",
            safety_priority="high",
        )
        fake_matrix = {
            "Reading": 20.8,
            "Sharon": 39.3,
            "Bedford": 27.9,
        }
        with patch("app.ranking.ensure_destination_matrix", return_value=fake_matrix):
            results = rank_suburbs(prefs, top_n=10)
        for row in results:
            minutes = row["data"]["drive_minutes_to_destination"]
            self.assertLessEqual(minutes, 30, msg=row["name"])


if __name__ == "__main__":
    unittest.main()
