#!/usr/bin/env python3
"""Generate app/evals/tier15_eval.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

OUT = SERVICE_ROOT / "app" / "evals" / "tier15_eval.json"

CASES = [
    # P0 — exclude vs destination
    {"id": "excl_dest_01", "category": "exclude_destination", "expect_intent": "recommend_structured", "expect_gate": None, "prompt": "Recommend towns under $600k but not Framingham"},
    {"id": "excl_dest_02", "category": "exclude_destination", "expect_intent": "recommend_structured", "expect_gate": None, "prompt": "Find affordable towns within 40 minutes of Boston excluding Natick"},
    # P0 — typo lookup
    {"id": "typo_01", "category": "typo_lookup", "expect_intent": "lookup_single_town", "prompt": "Does Chelseaa have strong schools?"},
    {"id": "typo_02", "category": "typo_lookup", "expect_intent": "lookup_single_town", "accept_intents": ["lookup_single_town", "dataset_membership"], "prompt": "Is Westborugh in the list?"},
    # P0 — multi commute compare
    {"id": "multi_lk_01", "category": "multi_lookup", "expect_intent": "compare_towns", "prompt": "What is the commute from Gardner and what is the commute from Shrewsbury?"},
    {"id": "multi_lk_02", "category": "multi_lookup", "expect_intent": "compare_towns", "prompt": "Commute from Gardner and commute from Shrewsbury"},
    # P0 — multi-field lookup
    {"id": "multi_fld_01", "category": "multi_field", "expect_intent": "lookup_single_town", "prompt": "What are Newton's home price and school score?"},
    {"id": "multi_fld_02", "category": "multi_field", "expect_intent": "lookup_single_town", "prompt": "Tell me Acton's commute and safety score"},
    # P1 — coastal list
    {"id": "coastal_01", "category": "coastal_list", "expect_intent": "recommend_structured", "prompt": "Waterfront towns in the dataset"},
    {"id": "coastal_02", "category": "coastal_list", "expect_intent": "recommend_structured", "prompt": "Which coastal towns do you have?"},
    # P1 — open-ended
    {"id": "open_01", "category": "open_ended", "expect_intent": "needs_clarification", "prompt": "What towns should I consider?"},
    {"id": "open_02", "category": "open_ended", "expect_intent": "needs_clarification", "prompt": "What do you recommend?"},
    # P1 — membership typo
    {"id": "member_01", "category": "membership", "expect_intent": "dataset_membership", "prompt": "Is Worchester supported?"},
    # P1 — scope meta lookup
    {"id": "scope_01", "category": "scope_lookup", "expect_intent": "lookup_single_town", "prompt": "Is Hull excluded?"},
    # P1 — exclude in ranking
    {"id": "excl_rank_01", "category": "exclude_rank", "expect_intent": "recommend_structured", "prompt": "Towns under 700k but not Sharon"},
    # Controls
    {"id": "ctrl_01", "category": "control", "expect_intent": "recommend_structured", "expect_gate": "commute_destination_rank", "prompt": "Towns within 30 minutes of Cambridge"},
    {"id": "ctrl_02", "category": "control", "expect_intent": "lookup_single_town", "prompt": "How far is Acton from Boston?"},
]

if __name__ == "__main__":
    payload = {
        "description": "Tier 1.5 routing + trust fixes",
        "prompt_count": len(CASES),
        "cases": CASES,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(CASES)} cases to {OUT}")
