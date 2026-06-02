#!/usr/bin/env python3
"""Generate 30 fresh mixed smoke prompts for query-agent regression."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.evals.e2e_expect import build_e2e_expect  # noqa: E402

DEFAULT_OUT = SERVICE_ROOT / "app" / "evals" / "mixed_smoke_30_fresh.json"

CASES: list[tuple[str, str]] = [
    ("membership", "Is Pepperell in your coverage list?"),
    ("membership", "Would Sudbury be recognized if I misspell it?"),
    ("lookup", "What's the drive time from Bedford to Boston?"),
    ("lookup", "Median price in Milton?"),
    ("compare", "Winchester vs Belmont on school scores."),
    ("compare", "Is Salem cheaper than Beverly on median home price?"),
    ("budget", "Towns under $550k with solid schools."),
    ("budget", "Affordable suburbs capped at $700k."),
    ("commute", "Max 35 minute commute, schools matter."),
    ("commute", "Shortest drive to Boston under 30 minutes."),
    ("coastal", "Seaside towns with good safety."),
    ("coastal", "Ocean towns under $1.1M."),
    ("semantic", "Towns with a Sudbury-like feel."),
    ("semantic", "Similar to Arlington but less expensive."),
    ("inverted", "Schools are not my priority — show cheaper towns."),
    ("inverted", "Don't weight safety heavily; budget under $600k."),
    ("unsupported", "Show current MLS listings in Newton."),
    ("unsupported", "Most walkable towns near Boston."),
    ("typo", "Pull up Marlborugh."),
    ("typo", "Lexinton versus Concord for price."),
    ("membership", "Can I use Carlis as a town name?"),
    ("lookup", "Is Peabody tagged coastal?"),
    ("compare", "Compare Sharon and Canton on safety."),
    ("budget", "Best value towns under $800k."),
    ("commute", "Towns 40–50 minutes from Boston."),
    ("coastal", "Water-adjacent suburbs."),
    ("semantic", "Brookline-like suburbs under $1.5M."),
    ("inverted", "High crime acceptable if affordable."),
    ("unsupported", "Best nightlife in Cambridge."),
    ("membership", "Does Westboro map to Westborough?"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260603)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if len(CASES) != 30:
        raise SystemExit(f"Expected 30 cases, got {len(CASES)}")

    rows: list[dict[str, Any]] = []
    by_cat: dict[str, int] = {}
    for i, (cat, prompt) in enumerate(CASES, 1):
        case = {"id": f"smoke30_{args.seed}_{i:03d}", "category": cat, "prompt": prompt}
        case["expect"] = build_e2e_expect(case)
        rows.append(case)
        by_cat[cat] = by_cat.get(cat, 0) + 1

    payload = {
        "description": "Phase 2 mixed smoke — 30 fresh prompts",
        "seed": args.seed,
        "target_pass_count": 28,
        "by_category": by_cat,
        "cases": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
