#!/usr/bin/env python3
"""Generate Phase 2 eval cases (multi lookup + multi compare, max 20)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
OUT = SERVICE_ROOT / "app" / "evals" / "phase2_eval.json"

MULTI_LOOKUP = [
    {"id": "ml_01", "category": "multi_lookup", "expect_intent": "lookup_multi_town", "prompt": "What is commute from Maynard, housing cost in Newton?"},
    {"id": "ml_02", "category": "multi_lookup", "expect_intent": "lookup_multi_town", "prompt": "Commute from Maynard and home price in Newton"},
    {"id": "ml_03", "category": "multi_lookup", "expect_intent": "lookup_multi_town", "prompt": "What is commute from manyard, housing cost in newton?"},
    {"id": "ml_04", "category": "multi_lookup", "expect_intent": "lookup_multi_town", "prompt": "School score in Lexington and commute from Acton"},
    {"id": "ml_05", "category": "multi_lookup", "expect_intent": "lookup_multi_town", "prompt": "Safety in Chelsea and price in Revere"},
    {
        "id": "ml_06",
        "category": "multi_lookup",
        "expect_intent": "lookup_multi_town",
        "min_specs": 5,
        "prompt": (
            "compare schools of westboro, commute from gardner, housing prices of concord, "
            "schools of concord, commute of newton, crime of everett"
        ),
    },
]

MULTI_COMPARE = [
    {"id": "mc_03", "category": "multi_compare", "expect_intent": "compare_multi_town", "min_rows": 3, "prompt": "Compare Newton, Needham, and Wellesley on schools"},
    {"id": "mc_05", "category": "multi_compare", "expect_intent": "compare_multi_town", "min_rows": 5, "prompt": "Compare Newton, Needham, Wellesley, Acton, and Concord on commute and schools"},
    {"id": "mc_10", "category": "multi_compare", "expect_intent": "compare_multi_town", "min_rows": 10, "prompt": (
        "Compare Acton, Arlington, Bedford, Belmont, Burlington, Concord, Lexington, Lincoln, "
        "Maynard, and Waltham on price and commute"
    )},
    {"id": "mc_20", "category": "multi_compare", "expect_intent": "compare_multi_town", "min_rows": 20, "prompt": (
        "Compare Acton, Arlington, Bedford, Belmont, Beverly, Braintree, Burlington, Cambridge, "
        "Chelsea, Concord, Dedham, Dover, Framingham, Gardner, Gloucester, Hingham, Lexington, "
        "Lincoln, Lowell, and Lynn on commute"
    )},
]

CONTROLS = [
    {"id": "ctrl_2town", "category": "control", "expect_intent": "compare_towns", "prompt": "Compare Newton and Needham on commute"},
    {"id": "ctrl_1town_2field", "category": "control", "expect_intent": "lookup_single_town", "prompt": "What are Newton's home price and school score?"},
    {"id": "ctrl_gate_21", "category": "too_many", "expect_gate": "too_many_compare", "prompt": (
        "Compare " + ", ".join(
            [
                "Acton", "Arlington", "Bedford", "Belmont", "Beverly", "Braintree", "Burlington",
                "Cambridge", "Chelsea", "Concord", "Dedham", "Dover", "Framingham", "Gardner",
                "Gloucester", "Hingham", "Lexington", "Lincoln", "Lowell", "Lynn", "Malden",
            ]
        )
        + " on schools"
    )},
]

CASES = MULTI_LOOKUP + MULTI_COMPARE + CONTROLS

if __name__ == "__main__":
    payload = {
        "description": "Phase 2 — multi-town lookup (max 20 specs) and compare table (max 20 towns)",
        "prompt_count": len(CASES),
        "cases": CASES,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(CASES)} cases to {OUT}")
