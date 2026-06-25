"""Phase 7 — API foundry vs local gateway (mocked)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from app.api import app, foundry_error_response  # noqa: E402
from app.foundry_client import FoundryAgentError  # noqa: E402


class TestApiFoundryMode(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_local_mode_returns_source(self) -> None:
        mock_payload = {
            "request_id": "local-req-1",
            "latency_ms": 10,
            "execution_status": "ok",
            "response": {
                "final_recommendation": "Maynard commute is about 41.7 minutes.",
                "top_matches": [],
            },
        }

        with patch("app.api.config.BACKEND_AGENT_MODE", "local"):
            with patch("app.api._suburbs_dataset_loaded", return_value=True):
                with patch("app.query_agent.query_agent_available", return_value=True):
                    with patch(
                        "app.query_agent.handle_query_v2",
                        new=AsyncMock(return_value=mock_payload),
                    ):
                        resp = self.client.post(
                            "/api/query",
                            json={"prompt": "What is the commute from Maynard?"},
                        )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["source"], "local_query_pipeline")
        self.assertIn("41.7", data["answer"])

    def test_query_alias_in_local_mode(self) -> None:
        with patch("app.api.config.BACKEND_AGENT_MODE", "local"):
            with patch("app.api._suburbs_dataset_loaded", return_value=True):
                with patch("app.query_agent.query_agent_available", return_value=True):
                    with patch(
                        "app.query_agent.handle_query_v2",
                        new=AsyncMock(
                            return_value={
                                "request_id": "q1",
                                "execution_status": "ok",
                                "response": {"final_recommendation": "ok", "top_matches": []},
                            }
                        ),
                    ) as handle:
                        resp = self.client.post(
                            "/api/query",
                            json={"query": "Compare Acton and Burlington."},
                        )
        self.assertEqual(resp.status_code, 200)
        handle.assert_awaited_once()
        self.assertEqual(handle.await_args.args[0], "Compare Acton and Burlington.")

    def test_foundry_mode_returns_answer(self) -> None:
        normalized = {
            "answer": "The drive from Maynard to Boston takes approximately 41.7 minutes.",
            "execution_status": "ok",
            "request_id": "foundry-req-1",
            "top_matches": [],
            "source": "foundry_hosted_agent",
            "metadata": {"backend_agent_mode": "foundry"},
            "used_answer_llm": True,
            "response": {"final_recommendation": "The drive from Maynard..."},
        }

        with patch("app.api.config.BACKEND_AGENT_MODE", "foundry"):
            with patch("app.foundry_client.foundry_agent_configured", return_value=True):
                with patch(
                    "app.foundry_client.call_foundry_agent",
                    new=AsyncMock(return_value=normalized),
                ):
                    with patch(
                        "app.foundry_persistence.persist_foundry_turn",
                        return_value={"saved": False},
                    ):
                        resp = self.client.post(
                            "/api/query",
                            json={"prompt": "What is the commute from Maynard?"},
                        )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["source"], "foundry_hosted_agent")
        self.assertIn("41.7", data["answer"])

    def test_foundry_timeout_returns_clean_error(self) -> None:
        with patch("app.api.config.BACKEND_AGENT_MODE", "foundry"):
            with patch("app.api.config.FALLBACK_TO_LOCAL", False):
                with patch("app.foundry_client.foundry_agent_configured", return_value=True):
                    with patch(
                        "app.foundry_client.call_foundry_agent",
                        new=AsyncMock(
                            side_effect=FoundryAgentError("timeout", "request timed out")
                        ),
                    ):
                        resp = self.client.post(
                            "/api/query",
                            json={"prompt": "hello"},
                        )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["error"], "foundry_agent_error")
        self.assertEqual(data["execution_status"], "error")
        self.assertEqual(data["source"], "foundry_hosted_agent")

    def test_foundry_fallback_to_local(self) -> None:
        local_payload = {
            "request_id": "fallback-1",
            "execution_status": "ok",
            "response": {"final_recommendation": "local answer", "top_matches": []},
        }

        with patch("app.api.config.BACKEND_AGENT_MODE", "foundry"):
            with patch("app.api.config.FALLBACK_TO_LOCAL", True):
                with patch("app.foundry_client.foundry_agent_configured", return_value=True):
                    with patch(
                        "app.foundry_client.call_foundry_agent",
                        new=AsyncMock(
                            side_effect=FoundryAgentError("timeout", "down")
                        ),
                    ):
                        with patch("app.api._suburbs_dataset_loaded", return_value=True):
                            with patch(
                                "app.query_agent.query_agent_available",
                                return_value=True,
                            ):
                                with patch(
                                    "app.query_agent.handle_query_v2",
                                    new=AsyncMock(return_value=local_payload),
                                ):
                                    resp = self.client.post(
                                        "/api/query",
                                        json={"prompt": "hello"},
                                    )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["source"], "local_query_pipeline")

    def test_health_includes_backend_mode(self) -> None:
        with patch("app.api.config.BACKEND_AGENT_MODE", "local"):
            with patch("app.api._suburbs_dataset_loaded", return_value=True):
                with patch("app.query_agent.query_agent_available", return_value=True):
                    with patch("app.foundry_client.foundry_agent_configured", return_value=False):
                        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["backend_agent_mode"], "local")
        self.assertFalse(data["foundry_agent_configured"])

    def test_warm_skipped_in_local_mode(self) -> None:
        with patch("app.api.config.BACKEND_AGENT_MODE", "local"):
            resp = self.client.post("/health/warm")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "skipped")
        self.assertFalse(data["warmed"])

    def test_warm_foundry_ok(self) -> None:
        with patch("app.api.config.BACKEND_AGENT_MODE", "foundry"):
            with patch("app.foundry_client.foundry_agent_configured", return_value=True):
                with patch(
                    "app.foundry_client.warm_foundry_agent",
                    new=AsyncMock(return_value={"answer": "yes"}),
                ):
                    resp = self.client.post("/health/warm")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["warmed"])
        self.assertIsNotNone(data["latency_ms"])

    def test_foundry_error_response_helper(self) -> None:
        out = foundry_error_response(FoundryAgentError("auth", "bad token"))
        self.assertEqual(out.error, "foundry_agent_error")
        self.assertEqual(out.execution_status, "error")

    def test_foundry_blocked_maps_trust_gate_fields(self) -> None:
        normalized = {
            "answer": "I can't compare commute to Providence.",
            "execution_status": "blocked",
            "request_id": "foundry-blocked-1",
            "message_code": "commute_destination_compare",
            "trust_gate": "commute_destination_compare",
            "trust_gate_blocks": True,
            "top_matches": [],
            "source": "foundry_hosted_agent",
            "metadata": {"backend_agent_mode": "foundry"},
            "used_answer_llm": False,
        }

        with patch("app.api.config.BACKEND_AGENT_MODE", "foundry"):
            with patch("app.foundry_client.foundry_agent_configured", return_value=True):
                with patch(
                    "app.foundry_client.call_foundry_agent",
                    new=AsyncMock(return_value=normalized),
                ):
                    with patch(
                        "app.foundry_persistence.persist_foundry_turn",
                        return_value={"saved": False},
                    ):
                        resp = self.client.post(
                            "/api/query",
                            json={"prompt": "Acton vs Burlington if I work in Providence."},
                        )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["execution_status"], "blocked")
        self.assertEqual(data["trust_gate"], "commute_destination_compare")
        self.assertTrue(data["trust_gate_blocks"])
        self.assertEqual(data["top_matches"], [])
        self.assertNotIn("{", data["answer"][:20])


if __name__ == "__main__":
    unittest.main()
