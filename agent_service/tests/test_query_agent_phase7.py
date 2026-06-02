"""Phase 7 tests — audit log and eval scoring (offline)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.evals.query_agent_runner import evaluate_query_agent_case  # noqa: E402
from app.query_agent_audit import save_query_agent_turn  # noqa: E402


class TestQueryAgentPhase7(unittest.TestCase):
    def test_save_query_agent_turn(self) -> None:
        from app import config

        with tempfile.TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            config.QUERY_AGENT_AUDIT_PATH = audit_path
            payload = {
                "execution_status": "ok",
                "used_answer_llm": True,
                "response": {"final_recommendation": "Maynard commute is 42 min."},
                "plan": {"ops": [{"op": "lookup"}]},
            }
            result = save_query_agent_turn("commute Maynard", payload)
            self.assertTrue(result["saved"])
            lines = audit_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            record = json.loads(lines[0])
            self.assertEqual(record["prompt"], "commute Maynard")
            self.assertEqual(record["execution_status"], "ok")

    def test_evaluate_blocked_trust_gate(self) -> None:
        case = {
            "id": "t",
            "expect_execution_status": "blocked",
            "expect_trust_gate": "unsupported_compare",
            "must_satisfy": {"query_agent": True},
        }
        payload = {
            "execution_status": "blocked",
            "trust_gate": "unsupported_compare",
            "used_answer_llm": False,
            "response": {
                "query_agent": True,
                "final_recommendation": "dataset does not include walkability",
            },
        }
        ok, reasons = evaluate_query_agent_case(case, payload)
        self.assertTrue(ok, reasons)

    def test_evaluate_not_found(self) -> None:
        case = {
            "id": "t",
            "expect_execution_status": "not_found",
            "must_satisfy": {"message_contains": ["dataset"]},
        }
        payload = {
            "execution_status": "not_found",
            "response": {
                "query_agent": True,
                "final_recommendation": "not in the curated 200-town dataset",
            },
        }
        ok, reasons = evaluate_query_agent_case(case, payload)
        self.assertTrue(ok, reasons)


if __name__ == "__main__":
    unittest.main()
