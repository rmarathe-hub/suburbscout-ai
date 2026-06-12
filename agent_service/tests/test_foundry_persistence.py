"""Phase 7 Step 4 — Foundry turn persistence (offline)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.foundry_persistence import (  # noqa: E402
    build_persist_payload_from_foundry,
    persist_foundry_turn,
)


class TestFoundryPersistence(unittest.TestCase):
    def _normalized_maynard(self) -> dict:
        return {
            "answer": "The drive from Maynard to Boston takes approximately 41.7 minutes.",
            "execution_status": "ok",
            "request_id": "foundry-req-1",
            "top_matches": [],
            "comparison": None,
            "tradeoff_warning": None,
            "score_disclaimer": "Scores are 0-10 percentile ranks within the 200-town dataset.",
            "source": "foundry_hosted_agent",
            "metadata": {
                "agent_name": "suburbscout-hosted",
                "agent_version": "3",
                "backend_agent_mode": "foundry",
            },
            "used_answer_llm": True,
            "response": {
                "query": "commute from Maynard",
                "final_recommendation": "The drive from Maynard to Boston takes approximately 41.7 minutes.",
                "top_matches": [],
            },
        }

    def test_build_payload_sets_final_recommendation_for_answer_log(self) -> None:
        payload = build_persist_payload_from_foundry(self._normalized_maynard(), latency_ms=99)
        self.assertEqual(payload["request_id"], "foundry-req-1")
        self.assertEqual(payload["message_code"], "foundry_hosted_agent")
        self.assertEqual(payload["latency_ms"], 99)
        self.assertIn("41.7", payload["response"]["final_recommendation"])

    def test_build_payload_compare_result_type_fields(self) -> None:
        normalized = {
            **self._normalized_maynard(),
            "answer": "Acton vs Burlington summary.",
            "comparison": {"town_a": {"town": "Acton"}, "town_b": {"town": "Burlington"}},
            "response": {
                "final_recommendation": "Acton vs Burlington summary.",
                "comparison": {"town_a": {"town": "Acton"}, "town_b": {"town": "Burlington"}},
            },
        }
        payload = build_persist_payload_from_foundry(normalized)
        self.assertIsNotNone(payload["response"]["comparison"])
        self.assertEqual(payload["response"]["comparison"]["town_a"]["town"], "Acton")

    def test_persist_skipped_when_save_audit_false(self) -> None:
        result = persist_foundry_turn(
            "commute Maynard",
            self._normalized_maynard(),
            save_audit=False,
        )
        self.assertFalse(result["saved"])

    def test_persist_calls_repository_when_save_audit_true(self) -> None:
        with patch("app.foundry_persistence.persist_query_turn") as mock_persist:
            mock_persist.return_value = {"saved": True, "request_id": "foundry-req-1"}
            result = persist_foundry_turn(
                "What is the commute from Maynard?",
                self._normalized_maynard(),
                session_id="sess-1",
                save_audit=True,
                latency_ms=50,
            )

        self.assertTrue(result["saved"])
        mock_persist.assert_called_once()
        args, kwargs = mock_persist.call_args
        self.assertEqual(args[0], "What is the commute from Maynard?")
        self.assertEqual(kwargs["session_id"], "sess-1")
        self.assertTrue(kwargs["save_jsonl"])
        self.assertEqual(args[1]["request_id"], "foundry-req-1")
        self.assertEqual(args[1]["message_code"], "foundry_hosted_agent")


if __name__ == "__main__":
    unittest.main()
