#!/usr/bin/env python3
"""Generate 25 fresh targeted regression prompts (Phase 2 buckets)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.evals.e2e_expect import build_e2e_expect  # noqa: E402

DEFAULT_OUT = SERVICE_ROOT / "app" / "evals" / "targeted_25_fresh.json"

CASES: list[tuple[str, str]] = [
    # pull-up lookup (7)
    ("pullup_lookup", "Pull up Woburn."),
    ("pullup_lookup", "Bring up Stoughton."),
    ("pullup_lookup", "Open Reading."),
    ("pullup_lookup", "Show me Hopkinton."),
    ("pullup_lookup", "Pull up Westborro."),
    ("pullup_lookup", "Show Acton."),
    ("pullup_lookup", "Bring up North Readng."),
    # inverted crime-affordability (6)
    ("inverted_crime", "Crime can be higher if homes are cheap."),
    ("inverted_crime", "Higher crime is okay if prices are low."),
    ("inverted_crime", "I can tolerate worse safety for affordability."),
    ("inverted_crime", "Safety can be mediocre if the town is affordable."),
    ("inverted_crime", "I care more about cheap homes than low crime."),
    ("inverted_crime", "Prioritize affordability even with worse safety scores."),
    # neighborhood unsupported (6)
    ("neighborhood", "Which neighborhood in Brookline is best for kids?"),
    ("neighborhood", "Best area inside Newton for families."),
    ("neighborhood", "Safest part of Quincy."),
    ("neighborhood", "Neighborhoods in Cambridge with good schools."),
    ("neighborhood", "Best part of Somerville to live in."),
    ("neighborhood", "Which part of Arlington should we avoid?"),
    # semantic lifestyle (6)
    ("semantic_lifestyle", "Places similar to Newton for young families."),
    ("semantic_lifestyle", "Towns like Brookline for families."),
    ("semantic_lifestyle", "Hingham-like suburbs for young professionals."),
    ("semantic_lifestyle", "Similar to Concord for raising kids."),
    ("semantic_lifestyle", "Suburbs like Wellesley for family-friendly living."),
    ("semantic_lifestyle", "Lexington-like towns for raising children."),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260603)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if len(CASES) != 25:
        raise SystemExit(f"Expected 25 cases, got {len(CASES)}")

    rows: list[dict[str, Any]] = []
    by_cat: dict[str, int] = {}
    for i, (cat, prompt) in enumerate(CASES, 1):
        case = {"id": f"tgt25_{args.seed}_{i:03d}", "category": cat, "prompt": prompt}
        case["expect"] = build_e2e_expect(case)
        if cat == "neighborhood":
            case["expect"]["execution_status_in"] = ["blocked", "out_of_scope"]
            case["expect"]["expect_used_answer_llm"] = False
        if cat == "semantic_lifestyle":
            case["expect"]["require_semantic_rank_limited"] = True
            case["expect"].pop("expect_used_answer_llm", None)
        rows.append(case)
        by_cat[cat] = by_cat.get(cat, 0) + 1

    payload = {
        "description": "Phase 2 targeted regression — 25 fresh prompts",
        "seed": args.seed,
        "target_pass_count": 24,
        "by_category": by_cat,
        "cases": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
