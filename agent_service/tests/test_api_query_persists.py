"""API persistence integration tests (Phase 3A)."""

from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.api import app  # noqa: E402
from tests.db_test_utils import postgres_integration_enabled, temporary_database_url  # noqa: E402


class TestApiQueryPersists(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    @unittest.skipUnless(
        postgres_integration_enabled(),
        "Postgres not available",
    )
    def test_api_query_persists_search_row(self) -> None:
        from app.repositories import SearchRepository

        rid = f"api-test-{uuid.uuid4()}"
        mock_payload = {
            "request_id": rid,
            "latency_ms": 12,
            "execution_status": "ok",
            "message_code": None,
            "used_answer_llm": False,
            "plan": {"ops": [{"op": "lookup"}]},
            "raw_llm_plan": {"ops": [{"op": "lookup"}]},
            "normalized_plan": {"ops": [{"op": "lookup"}]},
            "response": {
                "final_recommendation": "Test answer for persistence.",
                "top_matches": [],
            },
        }

        async def _fake_handle(
            prompt: str,
            *,
            save_searches: bool = False,
            session_id: str | None = None,
        ) -> dict:
            from app.repositories import persist_query_turn

            persist_query_turn(
                prompt,
                mock_payload,
                session_id=session_id,
                save_jsonl=save_searches,
            )
            return mock_payload

        with patch("app.api._suburbs_dataset_loaded", return_value=True):
            with patch("app.query_agent.query_agent_available", return_value=True):
                with patch(
                    "app.query_agent.handle_query_v2",
                    new=AsyncMock(side_effect=_fake_handle),
                ):
                    resp = self.client.post(
                        "/api/query",
                        json={"prompt": "Persistence smoke test"},
                    )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["request_id"], rid)

        trace = SearchRepository().get_search_trace(rid)
        self.assertIsNotNone(trace)
        assert trace is not None
        self.assertEqual(trace["prompt"], "Persistence smoke test")

        list_resp = self.client.get("/api/searches?limit=5")
        self.assertEqual(list_resp.status_code, 200)
        ids = [row["request_id"] for row in list_resp.json()["searches"]]
        self.assertIn(rid, ids)

    def test_history_endpoints_503_without_database_url(self) -> None:
        with temporary_database_url(None):
            self.assertEqual(self.client.get("/api/searches").status_code, 503)
            self.assertEqual(
                self.client.get("/api/searches/does-not-exist").status_code,
                503,
            )
            self.assertEqual(
                self.client.get("/api/sessions/demo").status_code,
                503,
            )


if __name__ == "__main__":
    unittest.main()
