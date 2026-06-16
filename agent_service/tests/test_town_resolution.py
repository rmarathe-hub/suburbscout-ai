"""Tests for confidence-gated town resolution."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.town_normalizer import resolve_town_for_plan  # noqa: E402


class TestTownResolution(unittest.TestCase):
    KNOWN = ["Lexington", "Acton", "Concord", "Manchester-by-the-Sea", "Wilmington"]

    def test_clear_typo_resolves(self) -> None:
        res = resolve_town_for_plan("Lexingtn", self.KNOWN)
        self.assertEqual(res.resolved, "Lexington")
        self.assertFalse(res.ambiguous)

    def test_exact_alias_resolves(self) -> None:
        res = resolve_town_for_plan("Marlboro", ["Marlborough", "Burlington"])
        self.assertEqual(res.resolved, "Marlborough")
        self.assertFalse(res.ambiguous)

    def test_unknown_returns_none(self) -> None:
        res = resolve_town_for_plan("ZZZNOTATOWN", self.KNOWN)
        self.assertIsNone(res.resolved)
        self.assertFalse(res.ambiguous)


if __name__ == "__main__":
    unittest.main()
