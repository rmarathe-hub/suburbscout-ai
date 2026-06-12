"""Database connectivity tests (Phase 3A)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from tests.db_test_utils import postgres_integration_enabled, temporary_database_url  # noqa: E402


class TestDbConnection(unittest.TestCase):
    def test_db_configured_without_url(self) -> None:
        from app.db import db_configured

        with temporary_database_url(None):
            self.assertFalse(db_configured())

    @unittest.skipUnless(
        postgres_integration_enabled(),
        "Postgres not available — start docker compose and set DATABASE_URL",
    )
    def test_db_available_select_one(self) -> None:
        from app.db import db_available, db_configured

        self.assertTrue(db_configured())
        self.assertTrue(db_available())

    @unittest.skipUnless(
        postgres_integration_enabled(),
        "Postgres not available — start docker compose and set DATABASE_URL",
    )
    def test_migrations_tables_exist(self) -> None:
        from sqlalchemy import inspect

        from app.db import _get_engine

        inspector = inspect(_get_engine())
        tables = set(inspector.get_table_names())
        expected = {
            "searches",
            "query_plans",
            "recommendation_results",
            "answer_logs",
            "audit_events",
            "sessions",
        }
        self.assertTrue(expected.issubset(tables), f"missing tables: {expected - tables}")


if __name__ == "__main__":
    unittest.main()
