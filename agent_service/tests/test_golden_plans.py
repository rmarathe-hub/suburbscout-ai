"""Phase 3 — golden plan executor regression tests."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from tests.golden_plan_assertions import (  # noqa: E402
    assert_golden_case,
    load_manifest,
    run_golden_case,
)


class TestGoldenPlans(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from app.config import SUBURBS_JSON_PATH

        if not SUBURBS_JSON_PATH.exists():
            raise unittest.SkipTest("suburbs.json missing")

        cls.manifest = load_manifest()
        cls.cases = cls.manifest.get("cases") or []
        # Default skip semantic (needs live embeddings) unless explicitly enabled.
        cls.skip_semantic = os.getenv("ENABLE_SEMANTIC_GOLDEN", "").lower() not in (
            "1",
            "true",
            "yes",
        )

    def test_manifest_has_cases(self) -> None:
        self.assertGreaterEqual(len(self.cases), 10)

    def test_all_golden_plans(self) -> None:
        all_failures: list[str] = []
        ran = 0
        for case in self.cases:
            if case.get("requires_live_embeddings") and self.skip_semantic:
                continue
            ran += 1
            result = run_golden_case(case)
            all_failures.extend(assert_golden_case(case, result))

        self.assertGreater(ran, 0, "no golden cases executed")
        if all_failures:
            self.fail("\n".join(all_failures))


if __name__ == "__main__":
    unittest.main()
