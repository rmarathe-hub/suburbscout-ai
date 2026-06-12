"""Postgres persistence for save_search / SearchRepository (Phase 3A)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from tests.db_test_utils import postgres_integration_enabled, temporary_database_url  # noqa: E402


def _sample_payload(*, request_id: str | None = None) -> dict:
    rid = request_id or str(uuid.uuid4())
    return {
        "request_id": rid,
        "latency_ms": 99,
        "execution_status": "ok",
        "message_code": None,
        "used_answer_llm": True,
        "plan": {"ops": [{"op": "lookup", "items": [{"town": "Maynard", "field": "commute"}]}]},
        "raw_llm_plan": {"ops": [{"op": "lookup", "items": [{"town": "Maynard", "field": "commute"}]}]},
        "normalized_plan": {"ops": [{"op": "lookup", "items": [{"town": "Maynard", "field": "commute"}]}]},
        "response": {
            "final_recommendation": "Maynard commute is about 42 minutes.",
            "top_matches": [{"name": "Maynard"}],
        },
    }


class TestSaveSearchPostgres(unittest.TestCase):
    @unittest.skipUnless(
        postgres_integration_enabled(),
        "Postgres not available",
    )
    def test_search_repository_save_turn(self) -> None:
        from app.repositories import SearchRepository

        rid = f"test-save-{uuid.uuid4()}"
        prompt = "What is the commute from Maynard?"
        payload = _sample_payload(request_id=rid)

        result = SearchRepository().save_turn(prompt, payload, session_id="test-session")
        self.assertTrue(result["saved"])
        self.assertEqual(result["request_id"], rid)

        trace = SearchRepository().get_search_trace(rid)
        assert trace is not None
        self.assertEqual(trace["prompt"], prompt)
        self.assertEqual(trace["execution_status"], "ok")
        self.assertEqual(trace["session_id"], "test-session")
        self.assertIn("Maynard", trace["answer"]["text"] or "")
        self.assertEqual(trace["recommendation_result"]["result_type"], "rank")

    def test_persist_query_turn_never_raises_on_bad_payload(self) -> None:
        from app.repositories import persist_query_turn

        result = persist_query_turn("", {"request_id": ""})
        self.assertFalse(result.get("saved"))

    def test_persist_legacy_search_jsonl_fallback(self) -> None:
        from app import config
        from app.repositories import persist_legacy_search

        original_saved_path = config.SAVED_SEARCHES_PATH
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "saved.jsonl"
            config.SAVED_SEARCHES_PATH = path
            with temporary_database_url(None):
                result = persist_legacy_search(
                    "safe towns under 900k",
                    results=[{"name": "Acton"}],
                    preferences={"budget_max": 900000},
                )
            config.SAVED_SEARCHES_PATH = original_saved_path

            self.assertTrue(result["saved"])
            self.assertEqual(result["storage"], "jsonl")
            lines = path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertEqual(record["prompt"], "safe towns under 900k")
            self.assertEqual(record["results"][0]["name"], "Acton")

    def test_save_search_tool_uses_postgres(self) -> None:
        from app.tools import save_search_tool

        with patch("app.repositories.db_configured", return_value=True):
            with patch(
                "app.repositories.SearchRepository.save_turn",
                return_value={"saved": True, "request_id": "legacy-rid"},
            ) as mock_save:
                out = save_search_tool(
                    "Find safe suburbs",
                    top_matches=[{"name": "Acton"}],
                    preferences={"safety_priority": "high"},
                )
        self.assertTrue(out["saved"])
        self.assertEqual(out["storage"], "postgres")
        mock_save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
