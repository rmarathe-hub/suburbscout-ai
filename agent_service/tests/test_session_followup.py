"""Session follow-up persistence tests (Phase 3A)."""

from __future__ import annotations

import sys
import unittest
import uuid
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from tests.db_test_utils import postgres_integration_enabled  # noqa: E402


class TestSessionFollowup(unittest.TestCase):
    @unittest.skipUnless(
        postgres_integration_enabled(),
        "Postgres not available",
    )
    def test_session_preferences_merge_on_follow_up(self) -> None:
        from app.repositories import SearchRepository

        session_id = f"session-{uuid.uuid4()}"
        repo = SearchRepository()
        repo.upsert_session_preferences(
            session_id,
            {"school_priority": "high", "commute_priority": "medium"},
        )

        plan = {
            "ops": [
                {
                    "op": "rank",
                    "preferences": {"budget_max": 850000},
                }
            ]
        }
        repo.update_session_from_turn(
            session_id,
            prompt="Make commute more important than schools.",
            plan=plan,
        )

        session = repo.get_session(session_id)
        assert session is not None
        prefs = session["latest_preferences"]
        assert prefs is not None
        self.assertEqual(prefs["commute_priority"], "high")
        self.assertEqual(prefs["school_priority"], "medium")
        self.assertEqual(prefs["budget_max"], 850000)

        ctx = repo.get_session_context(session_id)
        assert ctx is not None
        self.assertEqual(ctx["session_id"], session_id)
        self.assertEqual(ctx["latest_preferences"]["commute_priority"], "high")

    @unittest.skipUnless(
        postgres_integration_enabled(),
        "Postgres not available",
    )
    def test_session_created_via_save_turn(self) -> None:
        from app.repositories import SearchRepository

        session_id = f"session-{uuid.uuid4()}"
        rid = f"req-{uuid.uuid4()}"
        payload = {
            "request_id": rid,
            "latency_ms": 5,
            "execution_status": "ok",
            "message_code": None,
            "used_answer_llm": False,
            "normalized_plan": {
                "ops": [
                    {
                        "op": "rank",
                        "preferences": {"safety_priority": "high"},
                    }
                ]
            },
            "plan": {
                "ops": [
                    {
                        "op": "rank",
                        "preferences": {"safety_priority": "high"},
                    }
                ]
            },
            "response": {
                "final_recommendation": "Here are safe towns.",
                "top_matches": [{"name": "Acton"}],
            },
        }
        SearchRepository().save_turn(
            "Safe suburbs please",
            payload,
            session_id=session_id,
        )

        session = SearchRepository().get_session(session_id)
        assert session is not None
        self.assertEqual(session["latest_preferences"]["safety_priority"], "high")


if __name__ == "__main__":
    unittest.main()
