#!/usr/bin/env python3
"""Generate fresh 75-question E2E holdout (no reuse of prior 30/150 prompts)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.evals.e2e_expect import build_e2e_expect  # noqa: E402

DEFAULT_OUT = SERVICE_ROOT / "app" / "evals" / "e2e_query_agent_75_fresh.json"

# (category, prompt) — required cases first, then fill to 75
CASES: list[tuple[str, str]] = [
    # Required
    ("membership_typo", "Would Wstford resolve to a town?"),
    ("membership_typo", "Can I use North Readng?"),
    ("membership_typo", "Does Westboro map to Westborough?"),
    ("membership_typo", "Is Manchster-by-the-Sea recognized?"),
    ("typo", "Pull up Chelmsfrd."),
    ("typo", "Marlborugh versus Burlington for safety."),
    ("semantic", "Show towns with a Concord-like vibe but cheaper."),
    ("semantic", "Find suburbs similar to Hingham but less expensive."),
    ("semantic", "Give me a Brookline-like feel with lower prices."),
    ("coastal", "Show water-adjacent towns."),
    ("coastal", "Beachy suburbs under $900k."),
    ("inverted", "I do not care much about schools if the town is affordable."),
    ("inverted", "Safety can be mediocre, I mostly care about price."),
    ("commute", "Rank towns within 35 minutes of Cambridge."),
    ("unsupported", "Which is more walkable, Newton or Needham?"),
    ("unsupported", "Show current Zillow listings in Acton."),
    # membership / alias (fill to 8)
    ("membership", "Is Tewksbury part of your curated coverage?"),
    ("membership", "Would you recognize Stow as a valid town name?"),
    ("membership", "Is Littleton loaded in the dataset?"),
    ("membership_typo", "Is Boxbourgh accepted spelling for Boxborough?"),
    # lookup (10)
    ("lookup", "What's the median home price in Wellesley?"),
    ("lookup", "How long is the drive from Sudbury to Boston?"),
    ("lookup", "Give me the school score for Sharon."),
    ("lookup", "Is Marblehead marked coastal in your data?"),
    ("lookup", "What safety score does Melrose have?"),
    ("lookup", "Summarize Andover for me."),
    ("lookup", "Crime rate for Arlington — what do you have?"),
    ("lookup", "Does Natick show up as North Shore or elsewhere region-wise?"),
    ("lookup", "Home price year and value for Dover."),
    # compare (10)
    ("compare", "Newton or Needham — which has better schools?"),
    ("compare", "Compare Lexington and Winchester on safety and price."),
    ("compare", "Is Brookline pricier than Somerville?"),
    ("compare", "Framingham vs Quincy on commute to Boston."),
    ("compare", "Which is safer, Belmont or Watertown?"),
    ("compare", "Compare Arlington, Medford, and Malden on home price."),
    ("compare", "Rockport versus Gloucester on coastal status and price."),
    ("compare", "Bedford or Burlington for school scores."),
    ("compare", "Is Sharon more affordable than Weston on median price?"),
    # budget (10)
    ("budget", "Suburbs under $650k with decent schools."),
    ("budget", "Where can I buy under $500k within an hour of Boston?"),
    ("budget", "Affordable towns that are not tiny — budget cap $550k."),
    ("budget", "Best value towns if our ceiling is $725,000."),
    ("budget", "Recommend places under $600k, schools matter."),
    ("budget", "Towns realistically under $800k for a first home."),
    ("budget", "Stretch to $900k max — what fits?"),
    ("budget", "Cheaper than Newton but still commutable."),
    ("budget", "Lowest median prices you track near Boston."),
    # commute (10; includes Cambridge required)
    ("commute", "Under 45 minutes to South Station, prioritize schools."),
    ("commute", "Short commute towns, max 25 minutes driving."),
    ("commute", "I can do 50+ minutes if schools are strong."),
    ("commute", "Commute under 40 min and safe neighborhoods."),
    ("commute", "Towns between 20 and 35 minutes from Boston."),
    ("commute", "Quick commute is the top priority."),
    ("commute", "Farther out is fine — at least 40 minutes to Boston."),
    ("commute", "Max 30 minute drive, budget up to $1.2M."),
    ("commute", "Commute window 35–50 minutes, coastal optional."),
    # coastal (7; includes required)
    ("coastal", "Ocean-adjacent options with good schools."),
    ("coastal", "List seaside towns you track."),
    ("coastal", "Waterfront communities under $1M."),
    ("coastal", "Coastal suburbs with a shorter Boston commute."),
    ("coastal", "Beach towns that are still somewhat affordable."),
    # semantic (10; includes required)
    ("semantic", "Quiet family suburbs with a Lexington feel."),
    ("semantic", "Towns that feel like Wellesley but less pricey."),
    ("semantic", "Something like Concord but closer to Boston."),
    ("semantic", "Suburbs with an Arlington vibe and good transit-ish commute."),
    ("semantic", "Places similar to Newton for young families."),
    ("semantic", "I want a Medfield-like town under $900k."),
    ("semantic", "Vibe match to Hingham, budget flexible."),
    # inverted (5; includes required)
    ("inverted", "Crime can be higher if homes are cheap."),
    ("inverted", "School quality is secondary — affordability first."),
    ("inverted", "Don't weight safety heavily; show affordable options."),
    # unsupported / trust-style NL (5; includes required)
    ("unsupported", "Best nightlife towns near Boston."),
    ("unsupported", "Which neighborhood in Brookline is best for kids?"),
    ("unsupported", "Show me live Redfin listings in Cambridge."),
    ("unsupported", "Rank towns by walkability score."),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260603)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    if len(CASES) != 75:
        raise SystemExit(f"Expected 75 cases, got {len(CASES)}")

    prompts = {p for _, p in CASES}
    if len(prompts) != 75:
        raise SystemExit("Duplicate prompts in holdout set")

    e2e_cases: list[dict[str, Any]] = []
    by_cat: dict[str, int] = {}
    for i, (category, prompt) in enumerate(CASES, 1):
        case = {
            "id": f"hold75_{args.seed}_{i:03d}",
            "category": category,
            "prompt": prompt,
        }
        case["expect"] = build_e2e_expect(case)
        e2e_cases.append(case)
        by_cat[category] = by_cat.get(category, 0) + 1

    payload = {
        "description": "Fresh 75-question E2E holdout for query-agent verification",
        "seed": args.seed,
        "prompt_count": len(e2e_cases),
        "targets": {
            "final_pass_count": 68,
            "final_pass_rate": round(68 / 75, 4),
            "hallucinated_unsupported_facts": 0,
            "wrong_commute_destination_ranking": 0,
        },
        "by_category": by_cat,
        "cases": e2e_cases,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(e2e_cases)} cases to {args.out}")
    print("by_category:", by_cat)


if __name__ == "__main__":
    main()
