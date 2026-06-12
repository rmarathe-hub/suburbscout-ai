"""Phase 7 — API schema validation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from pydantic import ValidationError

from app.api_schemas import QueryRequest, QueryResponse


class TestQueryRequest(unittest.TestCase):
    def test_prompt_only(self) -> None:
        body = QueryRequest(prompt="What is the commute from Maynard?")
        self.assertEqual(body.resolved_prompt(), "What is the commute from Maynard?")

    def test_query_alias(self) -> None:
        body = QueryRequest(query="Compare Acton and Burlington.")
        self.assertEqual(body.resolved_prompt(), "Compare Acton and Burlington.")

    def test_prompt_takes_precedence_when_both_set(self) -> None:
        body = QueryRequest(prompt="from prompt", query="from query")
        self.assertEqual(body.resolved_prompt(), "from prompt")

    def test_requires_one_of_prompt_or_query(self) -> None:
        with self.assertRaises(ValidationError):
            QueryRequest()

    def test_rejects_whitespace_only(self) -> None:
        with self.assertRaises(ValidationError):
            QueryRequest(prompt="   ")


class TestQueryResponse(unittest.TestCase):
    def test_phase7_optional_fields_default_none(self) -> None:
        resp = QueryResponse(
            answer="hi",
            execution_status="ok",
            request_id="r1",
        )
        self.assertIsNone(resp.source)
        self.assertIsNone(resp.metadata)
        self.assertIsNone(resp.comparison)

    def test_foundry_shape(self) -> None:
        resp = QueryResponse(
            answer="41.7 minutes",
            execution_status="ok",
            request_id="r2",
            source="foundry_hosted_agent",
            metadata={"agent_name": "suburbscout-hosted", "backend_agent_mode": "foundry"},
            score_disclaimer="Scores are 0-10 percentile ranks...",
        )
        self.assertEqual(resp.source, "foundry_hosted_agent")
        self.assertEqual(resp.metadata["agent_name"], "suburbscout-hosted")


if __name__ == "__main__":
    unittest.main()
