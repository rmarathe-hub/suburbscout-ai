#!/usr/bin/env python3
"""Generate app/evals/holdout_150_v3_prompts.json — Holdout Set #3."""

from __future__ import annotations

import json
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
OUT = SERVICE_ROOT / "app" / "evals" / "holdout_150_v3_prompts.json"

CASES: list[tuple[str, str, str, str]] = [
    # A. Lookup / single-town facts
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Show me the stored profile for Gardner."),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What does the dataset report for Shrewsbury?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Pull Acton's commute and safety numbers."),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Tell me whether Burlington is pricey in your data."),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What fields are unavailable for Worcester?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Give me Westford's basic suburb record."),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Does Salem look risky based on your crime data?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What is Quincy's median home value in the dataset?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Is Framingham's data complete?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "How many miles is Rockport from Boston?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Do you know Newton's school score?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What safety rating does Chelsea have?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Summarize Lynn using your stored data."),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What is Plymouth's Boston drive time?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Pull Ipswich's school and safety info."),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Is Lowell marked full or partial?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What school percentile does North Reading have?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Is Beverly tagged as coastal?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What price do you have for Concord?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Is Peabody inland according to your tags?"),
    # B. Membership / scope / aliases
    ("B_membership", "B. Membership / scope / aliases", "dataset_membership", "Can your system handle Westboro?"),
    ("B_membership", "B. Membership / scope / aliases", "dataset_membership", "Is Foxboro mapped to Foxborough?"),
    ("B_membership", "B. Membership / scope / aliases", "dataset_membership", "Is Foxborough in the curated list?"),
    ("B_membership", "B. Membership / scope / aliases", "dataset_membership", "Do you keep Marlborough records?"),
    ("B_membership", "B. Membership / scope / aliases", "dataset_membership", 'Would "Marlboro" resolve to Marlborough?'),
    ("B_membership", "B. Membership / scope / aliases", "dataset_membership", "Is Northboro recognized as Northborough?"),
    ("B_membership", "B. Membership / scope / aliases", "dataset_membership", "Can you search Northborough?"),
    ("B_membership", "B. Membership / scope / aliases", "dataset_membership", "Is Dover covered by the 200-town dataset?"),
    ("B_membership", "B. Membership / scope / aliases", "dataset_membership", "Is Stow part of the suburb scope?"),
    ("B_membership", "B. Membership / scope / aliases", "dataset_membership", "Do you support Maynard queries?"),
    ("B_membership", "B. Membership / scope / aliases", "dataset_membership", "Can the app answer Hudson questions?"),
    ("B_membership", "B. Membership / scope / aliases", "refuse_out_of_scope", "Is Providence outside your coverage area?"),
    ("B_membership", "B. Membership / scope / aliases", "refuse_out_of_scope", "Is Nashua excluded from the Massachusetts scope?"),
    ("B_membership", "B. Membership / scope / aliases", "refuse_out_of_scope", "Is Springfield outside the Boston suburb set?"),
    ("B_membership", "B. Membership / scope / aliases", "refuse_out_of_scope", "Would Amherst be considered out of scope?"),
    ("B_membership", "B. Membership / scope / aliases", "refuse_out_of_scope", "Do you include Cape towns?"),
    ("B_membership", "B. Membership / scope / aliases", "refuse_out_of_scope", "Are non-Massachusetts towns supported?"),
    ("B_membership", "B. Membership / scope / aliases", "dataset_membership", "Is Worcester one of the towns you loaded?"),
    ("B_membership", "B. Membership / scope / aliases", "dataset_membership", "Is Manchester by the Sea normalized to Manchester-by-the-Sea?"),
    ("B_membership", "B. Membership / scope / aliases", "refuse_out_of_scope", "What happens if I ask about a town that is missing?"),
    # C. Typos / fuzzy town names
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Tell me about Shrewsburry."),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Is Worceester in the dataset?"),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Give me Burllington's commute."),
    ("C_typo", "C. Typos / fuzzy town names", "compare_towns", "Compare Framinghamn with Natick."),
    ("C_typo", "C. Typos / fuzzy town names", "dataset_membership", "Is Westferd covered?"),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "What commute do you have for Marlbourough?"),
    ("C_typo", "C. Typos / fuzzy town names", "compare_towns", "Compare Lexingtn with Arlington."),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Pull facts for Manchster-by-the-Sea."),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Is Swampscot coastal?"),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Does Wellesly have a school score?"),
    ("C_typo", "C. Typos / fuzzy town names", "compare_towns", "Compare Needhm and Dedham."),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Is Brokline expensive?"),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "What is Chelsae's safety score?"),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "How close is Somervile to Boston?"),
    ("C_typo", "C. Typos / fuzzy town names", "compare_towns", "Compare North Reading with Readng."),
    # D. Natural comparison questions
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Between Acton and Concord, who wins on safety?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Between Lynn and Revere, which has lower crime?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Would Sharon or Westford be stronger for families?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Is Waltham safer than Burlington?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Does Milton cost more than Quincy?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Which is pricier, Newton or Needham?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Rockport or Gloucester — which commute is longer?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Salem versus Beverly: which is safer?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Is Cambridge cheaper than Brookline?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Which is more affordable, Swampscott or Marblehead?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Reading or Stoneham — which is better for schools?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Is Shrewsbury better than Worcester for safety?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Which has stronger schools, Arlington or Lexington?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Does Quincy beat Milton on affordability?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Braintree vs Weymouth: which is the better value?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "For commute, Medford or Malden?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Is Everett safer than Chelsea?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "If price matters, should I pick Framingham or Wellesley?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Salem or Peabody — which one is coastal?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Beverly vs Lynn for a family — which looks better?"),
    # E. Budget / affordability constraints
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "Show towns below 650k with okay safety."),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "Best options under 850k, no missing prices."),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "Give me towns capped at $700k."),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "I'm working with 950k and care about schools."),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "Find a place below 575k with manageable commute."),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "What are my choices if I only have 450k?"),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "Find towns below $1.2M with strong schools."),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "Stay under one million and skip partial data."),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "Make affordability the top priority, but avoid awful safety."),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "Show towns under 725k where schools are decent."),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "Best towns for $550k max."),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "I can go up to 900k if the town is worth it."),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "Leave out towns above 800k."),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "Full-data towns below 600k only."),
    ("E_budget", "E. Budget / affordability constraints", "recommend_structured", "Under 700k, show the strongest realistic compromises."),
    # F. Commute / distance constraints
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "I need a suburb less than 20 minutes from Boston."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Show towns within 30 minutes of Boston."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Find suburbs in the 30–45 minute commute band."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "I prefer towns 45+ minutes from Boston."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Commute should be 40 minutes or less."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "I want outer suburbs, not close-in places."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Find towns with tough Boston commutes but good schools."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Show places 25 to 35 minutes from Boston."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "I want both short commute and low cost."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Commute under 50 and price under 750k."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Which towns are near Boston and still safe?"),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Show towns beyond 50 minutes with lower prices."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "I do not want inner-ring suburbs."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Which towns fall between 40 and 60 minutes from Boston?"),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Recommend towns where commute can be the sacrifice."),
    # G. Coastal / region filters
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Only coastal towns under 950k."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Ocean-adjacent suburbs with acceptable safety."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "North Shore towns that are not super expensive."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "South Shore towns that work for families."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Coastal but not urban/city-like."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Beach-area options under 850k."),
    ("G_coastal", "G. Coastal / region filters", "lookup_single_town", "Is Salem tagged coastal?"),
    ("G_coastal", "G. Coastal / region filters", "lookup_single_town", "Does Beverly count as coastal?"),
    ("G_coastal", "G. Coastal / region filters", "lookup_single_town", "Is Reading inland?"),
    ("G_coastal", "G. Coastal / region filters", "lookup_single_town", "Is Boxford inland or coastal?"),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Coastal towns with above-average schools."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Safer towns on the North Shore."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Lower-price towns on the South Shore."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Near-water town under $1M."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Remove inland towns from consideration."),
    # H. Semantic / vibe prompts
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "Find me a polished, calm suburb with strong schools."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "Something with Concord vibes but cheaper."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "I like Newton but need a lower price point."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "Brookline-like, but less dense."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "I want a historic town-center feel."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "Quiet but still connected to amenities."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "Educated family suburb vibe."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "Winchester-like but not as expensive."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "A cheaper Wellesley alternative."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "Westford-like but closer to Boston."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "Safe, stable, low-drama suburb."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "Suburban but not isolated."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "Coastal feel without luxury pricing."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "Balanced family suburb with good value."),
    ("H_semantic", "H. Semantic / vibe prompts", "recommend_semantic", "Strong schools where price is the tradeoff."),
    # I. Inverted / unusual preference prompts
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Cheaper towns where weaker schools are acceptable."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Places where affordability is good but safety is weak."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Price and commute only; ignore schools."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Higher-crime but lower-cost places."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Cheapest towns you have."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Bad safety but short commute."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Below-average schools but cheaper homes."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Among affordable towns, sort by highest crime."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Low-price options with serious tradeoffs."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Practical towns that are not top-ranked."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Good commute but weak schools."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Affordable towns, but include clear warnings."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Tradeoff-heavy options below 600k."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Worst safety among towns under 700k."),
    ("I_inverted", "I. Inverted / unusual preference prompts", "recommend_structured", "Cheap and close to Boston even if safety is poor."),
]


def main() -> None:
    counters: dict[str, int] = {}
    cases = []
    for cat, label, intent, prompt in CASES:
        counters[cat] = counters.get(cat, 0) + 1
        cases.append({
            "id": f"{cat}_{counters[cat]:02d}",
            "category": cat,
            "category_label": label,
            "expected_intent": intent,
            "prompt": prompt,
        })
    payload = {
        "description": "Holdout Set #3 — fresh 150 prompts (third phrasing variant)",
        "prompt_count": len(cases),
        "cases": cases,
    }
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {OUT}")


if __name__ == "__main__":
    main()
