#!/usr/bin/env python3
"""Generate app/evals/holdout_150_v5_prompts.json — Holdout Set #5."""

from __future__ import annotations

import json
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
OUT = SERVICE_ROOT / "app" / "evals" / "holdout_150_v5_prompts.json"

LABELS = {
    "A_lookup": "A. Lookup / single-town facts",
    "B_membership": "B. Membership / scope / aliases",
    "C_typo": "C. Typos / fuzzy town names",
    "D_compare": "D. Natural comparison questions",
    "E_budget": "E. Budget / affordability constraints",
    "F_commute": "F. Commute / distance constraints",
    "G_coastal": "G. Coastal / region filters",
    "H_semantic": "H. Semantic / vibe prompts",
    "I_inverted": "I. Inverted / tradeoff-heavy prompts",
}

CASES: list[tuple[str, str, str]] = [
    # A Lookup
    ("A_lookup", "lookup_single_town", "Bring up Gardner's entry from the suburb dataset."),
    ("A_lookup", "lookup_single_town", "What saved statistics are available for Shrewsbury?"),
    ("A_lookup", "lookup_single_town", "Give me Acton's commute, price, and safety details."),
    ("A_lookup", "lookup_single_town", "In your data, does Burlington look expensive?"),
    ("A_lookup", "lookup_single_town", "What information is incomplete for Worcester?"),
    ("A_lookup", "lookup_single_town", "Show the main numbers you store for Westford."),
    ("A_lookup", "lookup_single_town", "Is Salem on the risky side according to your safety data?"),
    ("A_lookup", "lookup_single_town", "What median price do you have attached to Quincy?"),
    ("A_lookup", "lookup_single_town", "Does Framingham have any missing dataset fields?"),
    ("A_lookup", "lookup_single_town", "How far is Rockport from South Station in your data?"),
    ("A_lookup", "lookup_single_town", "Is there a school score recorded for Newton?"),
    ("A_lookup", "lookup_single_town", "What is Chelsea's safety profile?"),
    ("A_lookup", "lookup_single_town", "Give me a quick data-based summary of Lynn."),
    ("A_lookup", "lookup_single_town", "How long would Plymouth take to Boston?"),
    ("A_lookup", "lookup_single_town", "What do Ipswich's school and crime numbers look like?"),
    ("A_lookup", "lookup_single_town", "Is Lowell listed as a full-data town?"),
    ("A_lookup", "lookup_single_town", "Pull North Reading's school score."),
    ("A_lookup", "lookup_single_town", "Does Beverly have a coastal tag?"),
    ("A_lookup", "lookup_single_town", "What home value is stored for Concord?"),
    ("A_lookup", "lookup_single_town", "Is Peabody treated as inland?"),
    # B Membership
    ("B_membership", "dataset_membership", "Would Westboro return a valid result?"),
    ("B_membership", "dataset_membership", "Is Foxboro an accepted alias?"),
    ("B_membership", "dataset_membership", "Do you have Foxborough in the actual data?"),
    ("B_membership", "dataset_membership", "Can Marlborough be searched?"),
    ("B_membership", "dataset_membership", "Is Marlboro understood as Marlborough?"),
    ("B_membership", "dataset_membership", "Does Northboro point to Northborough?"),
    ("B_membership", "dataset_membership", "Is Northborough directly supported?"),
    ("B_membership", "dataset_membership", "Does the dataset include Dover?"),
    ("B_membership", "dataset_membership", "Is Stow one of the suburbs in scope?"),
    ("B_membership", "dataset_membership", "Are Maynard recommendations possible?"),
    ("B_membership", "dataset_membership", "Is Hudson usable in this app?"),
    ("B_membership", "refuse_out_of_scope", "Would Providence be considered out of bounds?"),
    ("B_membership", "refuse_out_of_scope", "Is Nashua ignored because it is not in Massachusetts?"),
    ("B_membership", "refuse_out_of_scope", "Is Springfield outside the curated Boston-area towns?"),
    ("B_membership", "refuse_out_of_scope", "Is Amherst outside this suburb tool?"),
    ("B_membership", "refuse_out_of_scope", "Does your town list include Cape Cod communities?"),
    ("B_membership", "refuse_out_of_scope", "Can this system answer for non-MA towns?"),
    ("B_membership", "dataset_membership", "Was Worcester included in the 200-town load?"),
    ("B_membership", "dataset_membership", "Is Manchester-by-the-Sea the canonical spelling?"),
    ("B_membership", "refuse_out_of_scope", "What answer do you give for a town you cannot find?"),
    # C Typo
    ("C_typo", "lookup_single_town", "Pull up Shrewsberyy."),
    ("C_typo", "dataset_membership", "Is Worcster searchable?"),
    ("C_typo", "lookup_single_town", "Give me Burlingtn's price."),
    ("C_typo", "compare_towns", "Compare Framingam and Natick on schools."),
    ("C_typo", "dataset_membership", "Is Westforrd recognized?"),
    ("C_typo", "lookup_single_town", "What is Marlborogh's safety score?"),
    ("C_typo", "compare_towns", "Lexingtn vs Winchester for commute."),
    ("C_typo", "lookup_single_town", "Do you have Manchster-by-the-Sea?"),
    ("C_typo", "lookup_single_town", "Is Swampscot coastal or inland?"),
    ("C_typo", "lookup_single_town", "What does Wellesely cost?"),
    ("C_typo", "compare_towns", "Needam vs Dedham for affordability."),
    ("C_typo", "lookup_single_town", "Is Brooklinee in the data?"),
    ("C_typo", "lookup_single_town", "Chelsia safety rating?"),
    ("C_typo", "lookup_single_town", "How far is Somervill from Boston?"),
    ("C_typo", "compare_towns", "North Readin compared with Reading."),
    # D Compare
    ("D_compare", "compare_towns", "Acton and Concord: which one is safer?"),
    ("D_compare", "compare_towns", "Revere or Lynn — which has the higher crime number?"),
    ("D_compare", "compare_towns", "For schools and safety, would you choose Sharon or Westford?"),
    ("D_compare", "compare_towns", "Is Waltham less dangerous than Burlington?"),
    ("D_compare", "compare_towns", "Quincy versus Milton: which is lower cost?"),
    ("D_compare", "compare_towns", "Which costs more, Needham or Newton?"),
    ("D_compare", "compare_towns", "Does Gloucester have a shorter commute than Rockport?"),
    ("D_compare", "compare_towns", "Beverly or Salem for lower crime?"),
    ("D_compare", "compare_towns", "Is Brookline less affordable than Cambridge?"),
    ("D_compare", "compare_towns", "Marblehead compared to Swampscott — which is cheaper?"),
    ("D_compare", "compare_towns", "Reading vs Stoneham, who wins on school score?"),
    ("D_compare", "compare_towns", "Is Shrewsbury safer than Worcester?"),
    ("D_compare", "compare_towns", "Arlington or Lexington for stronger schools?"),
    ("D_compare", "compare_towns", "Does Quincy have a price advantage over Milton?"),
    ("D_compare", "compare_towns", "If value matters, Braintree or Weymouth?"),
    ("D_compare", "compare_towns", "Which gets to Boston faster, Malden or Medford?"),
    ("D_compare", "compare_towns", "Everett or Chelsea — which has worse safety?"),
    ("D_compare", "compare_towns", "Framingham vs Wellesley if I care mostly about price."),
    ("D_compare", "compare_towns", "Salem compared with Peabody: which is waterfront/coastal?"),
    ("D_compare", "compare_towns", "For family living, Beverly or Lynn?"),
    # E Budget
    ("E_budget", "recommend_structured", "Find places at 650k or below with not-bad safety."),
    ("E_budget", "recommend_structured", "Only show towns under 850k that include home-price data."),
    ("E_budget", "recommend_structured", "Give me options no more expensive than $700k."),
    ("E_budget", "recommend_structured", "My housing limit is 950k and schools matter most."),
    ("E_budget", "recommend_structured", "Show towns below 575k where Boston is still reachable."),
    ("E_budget", "recommend_structured", "If my ceiling is 450k, what towns qualify?"),
    ("E_budget", "recommend_structured", "Best school towns under $1.2 million."),
    ("E_budget", "recommend_structured", "Keep results under $1M and remove partial-data towns."),
    ("E_budget", "recommend_structured", "Cheapest reasonable towns, but avoid the worst safety cases."),
    ("E_budget", "recommend_structured", "Under 725k with schools that are not weak."),
    ("E_budget", "recommend_structured", "Find the best towns with a 550k cap."),
    ("E_budget", "recommend_structured", "I'll spend up to 900k for a high-quality town."),
    ("E_budget", "recommend_structured", "Do not include anything above 800k."),
    ("E_budget", "recommend_structured", "Complete-record towns only, under 600k."),
    ("E_budget", "recommend_structured", "Show realistic tradeoffs below 700k."),
    # F Commute
    ("F_commute", "recommend_structured", "I need towns inside a 20-minute Boston commute."),
    ("F_commute", "recommend_structured", "Which places are half an hour or less from Boston?"),
    ("F_commute", "recommend_structured", "Show me towns in the 30 to 45 minute range."),
    ("F_commute", "recommend_structured", "I'm okay being 45 minutes or farther from Boston."),
    ("F_commute", "recommend_structured", "Keep drive time to Boston at 40 minutes max."),
    ("F_commute", "recommend_structured", "I prefer outer suburbs over inner suburbs."),
    ("F_commute", "recommend_structured", "Long commute is okay if the schools are strong."),
    ("F_commute", "recommend_structured", "Find towns from 25 through 35 minutes away."),
    ("F_commute", "recommend_structured", "I care about low cost and a short Boston drive."),
    ("F_commute", "recommend_structured", "Search under 50 minutes and under $750k."),
    ("F_commute", "recommend_structured", "Close to Boston but not unsafe — what works?"),
    ("F_commute", "recommend_structured", "Give me cheaper towns beyond a 50-minute commute."),
    ("F_commute", "recommend_structured", "Skip the close-in towns."),
    ("F_commute", "recommend_structured", "Which towns are roughly 40–60 minutes out?"),
    ("F_commute", "recommend_structured", "I'm willing to accept a worse commute for affordability."),
    # G Coastal
    ("G_coastal", "recommend_structured", "Coastal only, below 950k."),
    ("G_coastal", "recommend_structured", "Give me safe-ish towns near the water."),
    ("G_coastal", "recommend_structured", "North Shore choices that are not insanely priced."),
    ("G_coastal", "recommend_structured", "Family-focused South Shore recommendations."),
    ("G_coastal", "recommend_structured", "I want coastal without an urban feel."),
    ("G_coastal", "recommend_structured", "Beach-adjacent towns below 850k."),
    ("G_coastal", "lookup_single_town", "Is Salem flagged as coastal?"),
    ("G_coastal", "lookup_single_town", "Is Beverly waterfront/coastal in the data?"),
    ("G_coastal", "lookup_single_town", "Is Reading tagged inland?"),
    ("G_coastal", "lookup_single_town", "Boxford is inland, right?"),
    ("G_coastal", "recommend_structured", "Coastal towns with stronger schools."),
    ("G_coastal", "recommend_structured", "North Shore towns that are safer than average."),
    ("G_coastal", "recommend_structured", "Affordable South Shore towns."),
    ("G_coastal", "recommend_structured", "Water-adjacent and under a million."),
    ("G_coastal", "recommend_structured", "I do not want inland towns in the list."),
    # H Semantic
    ("H_semantic", "recommend_semantic", "Give me an upscale but calm suburb with strong schools."),
    ("H_semantic", "recommend_semantic", "Concord-like but more affordable."),
    ("H_semantic", "recommend_semantic", "Newton feels right, but the price is too high."),
    ("H_semantic", "recommend_semantic", "Something with Brookline convenience but more suburban."),
    ("H_semantic", "recommend_semantic", "I want an old-town-center New England vibe."),
    ("H_semantic", "recommend_semantic", "Quiet, connected, and not too isolated."),
    ("H_semantic", "recommend_semantic", "A suburb for educated families with good schools."),
    ("H_semantic", "recommend_semantic", "Winchester-ish but cheaper."),
    ("H_semantic", "recommend_semantic", "Give me a Wellesley alternative that costs less."),
    ("H_semantic", "recommend_semantic", "Like Westford, but with an easier Boston commute."),
    ("H_semantic", "recommend_semantic", "Calm, safe, family-oriented, and stable."),
    ("H_semantic", "recommend_semantic", "Suburban feel with access to things nearby."),
    ("H_semantic", "recommend_semantic", "Coastal vibe without millionaire pricing."),
    ("H_semantic", "recommend_semantic", "Best balanced value suburb for a family."),
    ("H_semantic", "recommend_semantic", "Strong schools even if affordability takes a hit."),
    # I Inverted
    ("I_inverted", "recommend_structured", "I'm okay with lower school scores if the town is cheaper."),
    ("I_inverted", "recommend_structured", "Find affordable towns where safety is a downside."),
    ("I_inverted", "recommend_structured", "Do not factor schools much; prioritize price and commute."),
    ("I_inverted", "recommend_structured", "Lower home prices, even with more crime."),
    ("I_inverted", "recommend_structured", "Show the absolute cheapest towns in the file."),
    ("I_inverted", "recommend_structured", "Fast commute matters more than safety."),
    ("I_inverted", "recommend_structured", "Lower-cost towns where school quality is weak."),
    ("I_inverted", "recommend_structured", "Sort affordable towns from highest crime downward."),
    ("I_inverted", "recommend_structured", "Cheap options, but tell me the bad parts."),
    ("I_inverted", "recommend_structured", "Show second-tier practical towns, not just the polished ones."),
    ("I_inverted", "recommend_structured", "Good commute, lower price, weak schools accepted."),
    ("I_inverted", "recommend_structured", "Affordable towns with real warnings attached."),
    ("I_inverted", "recommend_structured", "Under 600k, give me the most compromised options."),
    ("I_inverted", "recommend_structured", "Which sub-700k towns have the worst safety scores?"),
    ("I_inverted", "recommend_structured", "I want cheap and close, even if the safety rating is poor."),
]


def main() -> None:
    counters: dict[str, int] = {}
    cases = []
    for cat, intent, prompt in CASES:
        counters[cat] = counters.get(cat, 0) + 1
        cases.append({
            "id": f"{cat}_{counters[cat]:02d}",
            "category": cat,
            "category_label": LABELS[cat],
            "expected_intent": intent,
            "prompt": prompt,
        })
    payload = {
        "description": "Holdout Set #5 — fresh 150 prompts (fifth phrasing variant)",
        "prompt_count": len(cases),
        "cases": cases,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {OUT}")


if __name__ == "__main__":
    main()
