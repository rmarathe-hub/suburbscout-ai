#!/usr/bin/env python3
"""Generate app/evals/tier1_trust_eval.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

OUT = SERVICE_ROOT / "app" / "evals" / "tier1_trust_eval.json"

CASES = [
    # Commute destination — must block, not Boston-rank
    {"id": "dest_rank_01", "category": "commute_destination", "expect_gate": "commute_destination_rank", "prompt": "Towns within 30 minutes of Cambridge"},
    {"id": "dest_rank_02", "category": "commute_destination", "expect_gate": "commute_destination_rank", "prompt": "I work in Burlington, find affordable towns"},
    {"id": "dest_rank_03", "category": "commute_destination", "expect_gate": "commute_destination_rank", "prompt": "Find towns within 35 minutes of Waltham"},
    {"id": "dest_rank_04", "category": "commute_destination", "expect_gate": "commute_destination_rank", "prompt": "I commute to Kendall Square, recommend towns under 700k"},
    {"id": "dest_lookup_01", "category": "commute_destination", "expect_gate": "commute_destination_lookup", "prompt": "How far is Shrewsbury from Worcester?"},
    {"id": "dest_lookup_02", "category": "commute_destination", "expect_gate": "commute_destination_lookup", "prompt": "How far is Acton from Cambridge?"},
    # Unsupported compare
    {"id": "cmp_unsup_01", "category": "unsupported_compare", "expect_gate": "unsupported_compare", "prompt": "Which is more walkable, Newton or Brookline?"},
    {"id": "cmp_unsup_02", "category": "unsupported_compare", "expect_gate": "unsupported_compare", "prompt": "Which is more diverse, Framingham or Quincy?"},
    {"id": "cmp_unsup_03", "category": "unsupported_compare", "expect_gate": "unsupported_compare", "prompt": "Is Salem more touristy than Plymouth?"},
    # Unsupported rank (no supported constraints)
    {"id": "rank_unsup_01", "category": "unsupported_rank", "expect_gate": "unsupported_rank", "prompt": "Most diverse towns near Boston"},
    {"id": "rank_unsup_02", "category": "unsupported_rank", "expect_gate": "unsupported_rank", "prompt": "Find me the most walkable towns"},
    {"id": "rank_unsup_03", "category": "unsupported_rank", "expect_gate": "unsupported_rank", "prompt": "Best towns for MBTA access"},
    {"id": "rank_unsup_04", "category": "unsupported_rank", "expect_gate": "commute_destination_rank", "prompt": "Towns near Worcester with good schools"},
    # Multi compare (Phase 2 table — 3 towns, no block gate)
    {"id": "multi_cmp_01", "category": "multi_compare", "expect_gate": None, "expect_intent": "compare_multi_town", "prompt": "Compare Newton, Needham, and Wellesley for schools"},
    {"id": "multi_cmp_02", "category": "multi_compare", "expect_gate": None, "expect_intent": "compare_multi_town", "prompt": "Compare Acton, Concord, and Lexington on commute"},
    # Compare parse fixes — should succeed without trust gate
    {"id": "cmp_ok_01", "category": "compare_ok", "expect_gate": None, "expect_intent": "compare_towns", "prompt": "Compare commute from Gardner and Shrewsbury"},
    {"id": "cmp_ok_02", "category": "compare_ok", "expect_gate": None, "expect_intent": "compare_towns", "prompt": "Gardner vs Shrewsbury commute"},
    {"id": "cmp_ok_03", "category": "compare_ok", "expect_gate": None, "expect_intent": "compare_towns", "prompt": "Is Newton safer and cheaper than Brookline?"},
    # Controls — must still work (no blocking gate)
    {"id": "ctrl_01", "category": "control", "expect_gate": None, "expect_intent": "recommend_structured", "prompt": "Find towns under 600k within 35 minutes of Boston"},
    {"id": "ctrl_02", "category": "control", "expect_gate": None, "expect_intent": "lookup_single_town", "prompt": "How far is Acton from Boston?"},
    {"id": "ctrl_03", "category": "control", "expect_gate": None, "expect_intent": "compare_towns", "prompt": "Compare Newton and Needham on commute"},
    {"id": "ctrl_04", "category": "control", "expect_gate": None, "expect_intent": "lookup_single_town", "prompt": "Is Newton walkable?"},
    {"id": "ctrl_05", "category": "control", "expect_gate": None, "expect_intent": "lookup_single_town", "unsupported_field": True, "prompt": "Is Shrewsbury mountainous?"},
]

if __name__ == "__main__":
    payload = {
        "description": "Tier 1 trust gates — block silent-wrong routing",
        "prompt_count": len(CASES),
        "cases": CASES,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(CASES)} cases to {OUT}")
