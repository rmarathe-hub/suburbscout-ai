"""Phase 8.5 tests — commute service cache and dataset resolution."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app import config  # noqa: E402
from app.commute_destination import (  # noqa: E402
    detect_commute_destination,
    detect_compare_commute_destination,
    entity_towns_for_compare_gate,
    extract_commute_town_pair,
    extract_compare_commute_destination,
)
from app.commute_service import (  # noqa: E402
    ensure_destination_matrix,
    get_commute_minutes,
    is_boston_destination,
)
from app.config import SUBURBS_JSON_PATH  # noqa: E402


class TestCommuteDestination(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SUBURBS_JSON_PATH.exists():
            raise unittest.SkipTest("suburbs.json missing")

    def test_default_boston(self) -> None:
        dest = detect_commute_destination("Find safe suburbs under 900k")
        self.assertTrue(dest.is_default)
        self.assertIsNone(dest.commute_destination_town)

    def test_cambridge_destination(self) -> None:
        dest = detect_commute_destination("Towns within 30 minutes of Cambridge")
        self.assertFalse(dest.is_default)
        self.assertEqual(dest.destination_town, "Cambridge")
        self.assertTrue(dest.in_dataset)

    def test_hartford_not_in_dataset(self) -> None:
        dest = detect_commute_destination("Commute from Maynard to Hartford")
        self.assertFalse(dest.is_default)
        self.assertFalse(dest.in_dataset)

    def test_extract_commute_pair(self) -> None:
        pair = extract_commute_town_pair("What is the commute from Maynard to Cambridge?")
        self.assertEqual(pair, ("Maynard", "Cambridge"))

    def test_open_reading_default_destination(self) -> None:
        dest = detect_commute_destination("Open Reading.")
        self.assertTrue(dest.is_default)
        self.assertIsNone(dest.commute_destination_town)

    def test_compare_acton_burlington_default_destination(self) -> None:
        dest = detect_commute_destination("Compare Acton and Burlington.")
        self.assertTrue(dest.is_default)
        self.assertIsNone(dest.commute_destination_town)

    def test_compare_for_commute_destination(self) -> None:
        dest = detect_commute_destination("Compare Acton and Burlington for commute to Cambridge.")
        self.assertEqual(dest.destination_town, "Cambridge")
        self.assertEqual(extract_compare_commute_destination(
            "Compare Acton and Burlington for commute to Cambridge."
        ), "Cambridge")

    def test_compare_gate_excludes_destination_town(self) -> None:
        from app.entity_extractor import extract_entities

        entities = extract_entities("Compare Acton and Burlington for commute to Cambridge.")
        gated = entity_towns_for_compare_gate(
            entities,
            "Compare Acton and Burlington for commute to Cambridge.",
            compare_towns=["Acton", "Burlington"],
        )
        self.assertEqual(len(gated), 2)
        self.assertNotIn("Cambridge", gated)

    def test_work_in_cambridge_not_over_captured(self) -> None:
        dest = detect_commute_destination(
            "I work in Cambridge and want safe towns under 900k."
        )
        self.assertEqual(dest.destination_town, "Cambridge")
        self.assertTrue(dest.in_dataset)

    def test_commute_to_burlington_not_over_captured(self) -> None:
        dest = detect_commute_destination(
            "I need to commute to Burlington from a cheaper town with good schools."
        )
        self.assertEqual(dest.destination_town, "Burlington")
        self.assertTrue(dest.in_dataset)

    def test_commute_to_newton_not_over_captured(self) -> None:
        dest = detect_commute_destination(
            "Best suburbs if I care about commute to Newton more than schools."
        )
        self.assertEqual(dest.destination_town, "Newton")
        self.assertTrue(dest.in_dataset)

    def test_office_in_waltham(self) -> None:
        dest = detect_commute_destination(
            "My office is in Waltham. Find towns with strong schools under 1M."
        )
        self.assertEqual(dest.destination_town, "Waltham")
        self.assertFalse(dest.is_default)

    def test_town_commute_phrase_cambridge(self) -> None:
        dest = detect_commute_destination(
            "Find towns where Cambridge commute is under 35 minutes and schools are decent."
        )
        self.assertEqual(dest.destination_town, "Cambridge")
        self.assertFalse(dest.is_default)

    def test_compare_hartford_detected_unsupported(self) -> None:
        dest = detect_compare_commute_destination(
            "Compare Reading and Waltham for commute to Hartford."
        )
        self.assertIsNotNone(dest)
        self.assertFalse(dest.in_dataset)
        self.assertIsNone(dest.destination_town)
        self.assertEqual(dest.label, "Hartford")


class TestCompareCommuteTrustGate(unittest.TestCase):
    def test_acton_burlington_cambridge_not_multi_compare(self) -> None:
        from app.plan_trust_gates import evaluate_plan_trust_gate
        from app.query_plan import validate_plan

        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "compare",
                        "towns": ["Acton", "Burlington"],
                        "commute_destination_town": "Cambridge",
                    }
                ]
            }
        )
        gate = evaluate_plan_trust_gate(
            "Compare Acton and Burlington for commute to Cambridge.",
            plan,
        )
        self.assertIsNone(gate)

    def test_reading_north_reading_waltham_not_multi_compare(self) -> None:
        from app.plan_trust_gates import evaluate_plan_trust_gate
        from app.query_plan import validate_plan

        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "compare",
                        "towns": ["Reading", "North Reading"],
                        "commute_destination_town": "Waltham",
                    }
                ]
            }
        )
        gate = evaluate_plan_trust_gate(
            "Compare Reading and North Reading for commute to Waltham.",
            plan,
        )
        self.assertIsNone(gate)

    def test_hartford_compare_blocked(self) -> None:
        from app.plan_trust_gates import evaluate_plan_trust_gate
        from app.query_plan import validate_plan

        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "compare",
                        "towns": ["Reading", "Waltham"],
                    }
                ]
            }
        )
        gate = evaluate_plan_trust_gate(
            "Compare Reading and Waltham for commute to Hartford.",
            plan,
        )
        self.assertIsNotNone(gate)
        self.assertEqual(gate.gate_type, "commute_destination_compare")

    def test_providence_compare_blocked(self) -> None:
        from app.plan_trust_gates import evaluate_plan_trust_gate
        from app.query_plan import validate_plan

        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "compare",
                        "towns": ["Acton", "Burlington"],
                    }
                ]
            }
        )
        gate = evaluate_plan_trust_gate(
            "Compare Acton and Burlington for commute to Providence.",
            plan,
        )
        self.assertIsNotNone(gate)
        self.assertEqual(gate.gate_type, "commute_destination_compare")

    def test_nyc_compare_blocked(self) -> None:
        from app.plan_trust_gates import evaluate_plan_trust_gate
        from app.query_plan import validate_plan

        plan = validate_plan(
            {
                "ops": [
                    {
                        "op": "compare",
                        "towns": ["Sharon", "Milton"],
                    }
                ]
            }
        )
        gate = evaluate_plan_trust_gate(
            "Compare Sharon and Milton for commute to New York City.",
            plan,
        )
        self.assertIsNotNone(gate)
        self.assertEqual(gate.gate_type, "commute_destination_compare")


class TestSemanticSimilarRegression(unittest.IsolatedAsyncioTestCase):
    async def test_similar_acton_no_server_crash(self) -> None:
        from unittest.mock import AsyncMock, patch

        from app.query_agent import handle_query_v2
        from app.query_plan import validate_plan

        plan = validate_plan(
            {
                "ops": [
                    {"op": "semantic_search", "query_text": "similar to Acton but cheaper", "top_k": 10},
                    {
                        "op": "rank",
                        "preferences": {"similar_to_town": "Acton", "budget_max": 750000},
                        "limit": 10,
                        "use_semantic_candidates": True,
                    },
                ]
            }
        )
        with patch("app.query_agent.query_agent_available", return_value=True):
            with patch("app.query_agent.plan_query_with_llm", return_value=plan):
                with patch(
                    "app.tools.run_semantic_town_search",
                    AsyncMock(
                        return_value={
                            "query": "similar to Acton but cheaper",
                            "error": "Semantic search unavailable: 404",
                            "candidates": [],
                            "candidate_town_names": [],
                        }
                    ),
                ):
                    payload = await handle_query_v2(
                        "Find towns similar to Acton but cheaper.",
                        save_searches=False,
                    )
        self.assertIn(payload.get("execution_status"), ("ok", "partial", "no_rows"))
        self.assertNotEqual(payload.get("execution_status"), "error")


class TestCommuteService(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SUBURBS_JSON_PATH.exists():
            raise unittest.SkipTest("suburbs.json missing")

    def test_boston_uses_suburbs_json(self) -> None:
        result = get_commute_minutes("Maynard", "Boston")
        self.assertEqual(result.source, "suburbs_json")
        self.assertIsNotNone(result.drive_minutes)

    def test_cache_hit_for_pair(self) -> None:
        cache_path = config.COMMUTE_CACHE_PATH
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        key = "Maynard|Cambridge, MA"
        payload = {
            key: {
                "town": "Maynard",
                "origin": "Maynard, MA",
                "destination": "Cambridge, MA",
                "destination_town": "Cambridge",
                "drive_minutes": 32.0,
                "drive_miles": 18.5,
                "source": "google_distance_matrix",
            }
        }
        with open(cache_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

        result = get_commute_minutes("Maynard", "Cambridge")
        self.assertTrue(result.cached)
        self.assertEqual(result.drive_minutes, 32.0)

    @patch("app.commute_service.GOOGLE_MAPS_API_KEY", "")
    def test_dynamic_unavailable_without_api_key(self) -> None:
        result = get_commute_minutes("Acton", "Waltham")
        self.assertIsNone(result.drive_minutes)
        self.assertEqual(result.source, "unavailable")

    def test_ensure_boston_matrix(self) -> None:
        matrix = ensure_destination_matrix("Boston", ["Maynard", "Acton"])
        self.assertIsNotNone(matrix.get("Maynard"))
        self.assertTrue(is_boston_destination("Boston"))


if __name__ == "__main__":
    unittest.main()
