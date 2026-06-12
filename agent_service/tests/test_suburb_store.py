"""Phase 3C — suburb store (JSON fallback + optional Postgres)."""

from __future__ import annotations

import unittest
from pathlib import Path
from app.config import SUBURBS_JSON_PATH
from app.suburb_store import (
    clear_suburbs_cache,
    load_suburbs,
    suburbs_dataset_available,
    suburbs_table_count,
)
from tests.db_test_utils import postgres_integration_enabled, temporary_database_url


class SuburbStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_suburbs_cache()

    def tearDown(self) -> None:
        clear_suburbs_cache()

    def test_json_fallback_loads_200_towns(self) -> None:
        if not SUBURBS_JSON_PATH.is_file():
            self.skipTest("suburbs.json missing")
        with temporary_database_url(None):
            suburbs = load_suburbs()
        self.assertEqual(len(suburbs), 200)
        self.assertIn("name", suburbs[0])

    def test_suburbs_dataset_available_with_json(self) -> None:
        if not SUBURBS_JSON_PATH.is_file():
            self.skipTest("suburbs.json missing")
        with temporary_database_url(None):
            self.assertTrue(suburbs_dataset_available())

    def test_explicit_path_bypasses_cache(self) -> None:
        if not SUBURBS_JSON_PATH.is_file():
            self.skipTest("suburbs.json missing")
        suburbs = load_suburbs(SUBURBS_JSON_PATH)
        self.assertEqual(len(suburbs), 200)

    @unittest.skipUnless(
        postgres_integration_enabled(),
        "Postgres not available (set DATABASE_URL and run docker compose up -d)",
    )
    def test_postgres_load_when_seeded(self) -> None:
        from app.suburb_store import seed_suburbs_from_json

        seed_suburbs_from_json()
        clear_suburbs_cache()
        count = suburbs_table_count()
        self.assertGreaterEqual(count, 200)
        suburbs = load_suburbs()
        self.assertEqual(len(suburbs), 200)
        names = {s["name"] for s in suburbs}
        self.assertIn("Boston", names)

    @unittest.skipUnless(
        postgres_integration_enabled(),
        "Postgres not available",
    )
    def test_postgres_matches_json_record_count(self) -> None:
        from app.suburb_store import seed_suburbs_from_json

        with temporary_database_url(None):
            json_suburbs = load_suburbs(SUBURBS_JSON_PATH)
        seed_suburbs_from_json()
        clear_suburbs_cache()
        db_suburbs = load_suburbs()
        self.assertEqual(len(db_suburbs), len(json_suburbs))


if __name__ == "__main__":
    unittest.main()
