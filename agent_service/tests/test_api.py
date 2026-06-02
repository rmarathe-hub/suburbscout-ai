"""FastAPI gateway tests (Phase 2 Step 6)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.api import app, payload_to_query_response  # noqa: E402


class TestApiGateway(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health(self) -> None:
        with patch("app.api._suburbs_dataset_loaded", return_value=True):
            with patch("app.query_agent.query_agent_available", return_value=True):
                resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["suburbs_dataset_loaded"])

    def test_query_mocked(self) -> None:
        mock_payload = {
            "request_id": "test-req-1",
            "latency_ms": 42,
            "execution_status": "ok",
            "message_code": None,
            "used_answer_llm": True,
            "plan": {"ops": [{"op": "lookup"}]},
            "raw_llm_plan": {"ops": [{"op": "lookup"}]},
            "response": {
                "final_recommendation": "Maynard commute is about 42 minutes.",
                "top_matches": [],
            },
        }

        async def _fake_handle(prompt: str, *, save_searches: bool = False) -> dict:
            self.assertEqual(prompt, "What is the commute from Maynard?")
            self.assertFalse(save_searches)
            return mock_payload

        with patch("app.api._suburbs_dataset_loaded", return_value=True):
            with patch("app.query_agent.query_agent_available", return_value=True):
                with patch(
                    "app.query_agent.handle_query_v2",
                    new=AsyncMock(side_effect=_fake_handle),
                ):
                    resp = self.client.post(
                        "/api/query",
                        json={"prompt": "What is the commute from Maynard?", "debug": True},
                    )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["execution_status"], "ok")
        self.assertEqual(data["request_id"], "test-req-1")
        self.assertIn("Maynard", data["answer"])
        self.assertIsNotNone(data.get("plan"))

    def test_query_not_configured(self) -> None:
        with patch("app.api._suburbs_dataset_loaded", return_value=True):
            with patch("app.query_agent.query_agent_available", return_value=False):
                resp = self.client.post("/api/query", json={"prompt": "hello"})
        self.assertEqual(resp.status_code, 503)

    def test_payload_mapper_debug_off(self) -> None:
        out = payload_to_query_response(
            {
                "request_id": "r1",
                "execution_status": "ok",
                "response": {"final_recommendation": "hi", "top_matches": [{"name": "Acton"}]},
                "plan": {"ops": []},
            },
            debug=False,
        )
        self.assertIsNone(out.plan)
        self.assertEqual(out.answer, "hi")


if __name__ == "__main__":
    unittest.main()
