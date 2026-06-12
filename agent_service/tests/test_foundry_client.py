"""Phase 7 — Foundry client (offline)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.foundry_client import (  # noqa: E402
    FoundryAgentError,
    build_responses_endpoint,
    foundry_agent_configured,
    normalize_foundry_http_response,
    normalize_foundry_payload,
)


class TestFoundryEndpoint(unittest.TestCase):
    def test_build_from_project_endpoint(self) -> None:
        with patch("app.foundry_client.config") as cfg:
            cfg.FOUNDRY_AGENT_RESPONSES_ENDPOINT = None
            cfg.FOUNDRY_PROJECT_ENDPOINT = (
                "https://acct.services.ai.azure.com/api/projects/my-project"
            )
            cfg.FOUNDRY_AGENT_NAME = "suburbscout-hosted"
            cfg.FOUNDRY_AGENT_VERSION = None
            url = build_responses_endpoint()
        self.assertEqual(
            url,
            "https://acct.services.ai.azure.com/api/projects/my-project"
            "/agents/suburbscout-hosted/endpoint/protocols/openai/responses",
        )

    def test_build_with_version_metadata_only(self) -> None:
        with patch("app.foundry_client.config") as cfg:
            cfg.FOUNDRY_AGENT_RESPONSES_ENDPOINT = None
            cfg.FOUNDRY_PROJECT_ENDPOINT = (
                "https://acct.services.ai.azure.com/api/projects/my-project"
            )
            cfg.FOUNDRY_AGENT_NAME = "suburbscout-hosted"
            cfg.FOUNDRY_AGENT_VERSION = "3"
            url = build_responses_endpoint()
        self.assertEqual(
            url,
            "https://acct.services.ai.azure.com/api/projects/my-project"
            "/agents/suburbscout-hosted/endpoint/protocols/openai/responses",
        )
        self.assertNotIn("/versions/", url or "")

    def test_responses_request_url_appends_api_version(self) -> None:
        from app.foundry_client import _responses_request_url

        self.assertEqual(
            _responses_request_url("https://x/responses"),
            "https://x/responses?api-version=v1",
        )
        self.assertEqual(
            _responses_request_url("https://x/responses?api-version=v1"),
            "https://x/responses?api-version=v1",
        )

    def test_explicit_endpoint_override(self) -> None:
        with patch("app.foundry_client.config") as cfg:
            cfg.FOUNDRY_AGENT_RESPONSES_ENDPOINT = "https://custom.example/responses"
            cfg.FOUNDRY_PROJECT_ENDPOINT = ""
            cfg.FOUNDRY_AGENT_NAME = ""
            cfg.FOUNDRY_AGENT_VERSION = None
            self.assertEqual(build_responses_endpoint(), "https://custom.example/responses")
            self.assertTrue(foundry_agent_configured())


class TestFoundryNormalize(unittest.TestCase):
    def test_maynard_commute_json(self) -> None:
        raw = {
            "query": "what is the commute from maynard to boston",
            "final_recommendation": (
                "The drive from Maynard to Boston takes approximately 41.7 minutes "
                "and covers a distance of about 29.18 miles."
            ),
            "top_matches": [],
            "comparison": None,
            "tradeoff_warning": None,
            "score_disclaimer": "Scores are 0-10 percentile ranks within the 200-town dataset.",
        }
        with patch("app.foundry_client.config") as cfg:
            cfg.FOUNDRY_AGENT_NAME = "suburbscout-hosted"
            cfg.FOUNDRY_AGENT_VERSION = "3"
            out = normalize_foundry_payload(raw, request_id="req-1")

        self.assertIn("41.7", out["answer"])
        self.assertEqual(out["source"], "foundry_hosted_agent")
        self.assertEqual(out["metadata"]["agent_name"], "suburbscout-hosted")
        self.assertEqual(out["execution_status"], "ok")

    def test_compare_acton_burlington(self) -> None:
        raw = {
            "final_recommendation": "Acton vs Burlington comparison summary.",
            "comparison": {
                "town_a": {"town": "Acton"},
                "town_b": {"town": "Burlington"},
            },
            "top_matches": [],
        }
        with patch("app.foundry_client.config") as cfg:
            cfg.FOUNDRY_AGENT_NAME = "suburbscout-hosted"
            cfg.FOUNDRY_AGENT_VERSION = None
            out = normalize_foundry_payload(raw)

        self.assertIsNotNone(out["comparison"])
        self.assertIn("Acton", out["answer"])

    def test_responses_api_with_fenced_json(self) -> None:
        agent_json = {
            "final_recommendation": "I cannot provide live Zillow listings.",
            "top_matches": [],
        }
        wrapped = {
            "output_text": "```json\n" + json.dumps(agent_json) + "\n```",
        }
        with patch("app.foundry_client.config") as cfg:
            cfg.FOUNDRY_AGENT_NAME = "suburbscout-hosted"
            cfg.FOUNDRY_AGENT_VERSION = None
            out = normalize_foundry_http_response(wrapped, request_id="z1")

        self.assertIn("Zillow", out["answer"])
        self.assertEqual(out["source"], "foundry_hosted_agent")

    def test_malformed_empty_output(self) -> None:
        with self.assertRaises(FoundryAgentError) as ctx:
            normalize_foundry_http_response({"output": []})
        self.assertEqual(ctx.exception.code, "malformed")


class TestCallFoundryAgent(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_returns_clean_error(self) -> None:
        import httpx

        from app.foundry_client import call_foundry_agent

        with patch("app.foundry_client.build_responses_endpoint", return_value="https://x/responses"):
            with patch("app.foundry_client._get_bearer_token", return_value="token"):
                with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
                    post.side_effect = httpx.TimeoutException("timed out")
                    with self.assertRaises(FoundryAgentError) as ctx:
                        await call_foundry_agent("hello")
        self.assertEqual(ctx.exception.code, "timeout")

    async def test_success_mocked(self) -> None:
        from app.foundry_client import call_foundry_agent

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "final_recommendation": "Maynard is about 41.7 minutes from Boston.",
            "top_matches": [],
        }

        with patch("app.foundry_client.build_responses_endpoint", return_value="https://x/responses"):
            with patch("app.foundry_client._get_bearer_token", return_value="token"):
                with patch("httpx.AsyncClient") as client_cls:
                    client = AsyncMock()
                    client.__aenter__.return_value = client
                    client.__aexit__.return_value = None
                    client.post = AsyncMock(return_value=mock_resp)
                    client_cls.return_value = client

                    with patch("app.foundry_client.config") as cfg:
                        cfg.FOUNDRY_AGENT_NAME = "suburbscout-hosted"
                        cfg.FOUNDRY_AGENT_VERSION = "3"
                        out = await call_foundry_agent("commute Maynard")

        self.assertEqual(out["source"], "foundry_hosted_agent")
        self.assertIn("41.7", out["answer"])


if __name__ == "__main__":
    unittest.main()
