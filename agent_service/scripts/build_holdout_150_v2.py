#!/usr/bin/env python3
"""Generate app/evals/holdout_150_v2_prompts.json — Holdout Set #2."""

from __future__ import annotations

import json
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
OUT = SERVICE_ROOT / "app" / "evals" / "holdout_150_v2_prompts.json"

CASES: list[tuple[str, str, str, str]] = [
    # A. Lookup / single-town facts
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Pull up everything you know about Gardner."),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What does your data say about Shrewsbury's commute?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "How long would it take to drive from Acton to Boston?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What is Burlington's safety situation in your dataset?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Is Framingham missing any major data fields?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Give me Westford's price, school score, and commute."),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Does Salem have a high or low crime score?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What is the stored house price for Quincy?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Tell me if Worcester has complete housing data."),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What is Marblehead's commute distance?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Is Newton's school score available?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "How does Chelsea score on safety?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Give me the data profile for Lynn."),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What is the commute estimate for Plymouth?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What do you know about Ipswich?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Is Lowell full-data or partial-data?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "What is the school rating for North Reading?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Does Beverly have coastal status?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "How expensive is Concord?"),
    ("A_lookup", "A. Lookup / single-town facts", "lookup_single_town", "Is Peabody marked as coastal or inland?"),
    # B. Membership / coverage / aliases
    ("B_membership", "B. Membership / coverage / aliases", "dataset_membership", "Are you able to search Westboro?"),
    ("B_membership", "B. Membership / coverage / aliases", "dataset_membership", "Is Foxborough part of your list?"),
    ("B_membership", "B. Membership / coverage / aliases", "dataset_membership", "Do you recognize Foxboro as Foxborough?"),
    ("B_membership", "B. Membership / coverage / aliases", "dataset_membership", "Do you track Marlborough?"),
    ("B_membership", "B. Membership / coverage / aliases", "dataset_membership", "Is Marlboro treated as Marlborough?"),
    ("B_membership", "B. Membership / coverage / aliases", "dataset_membership", "Is Northboro included as Northborough?"),
    ("B_membership", "B. Membership / coverage / aliases", "dataset_membership", "Do you cover Northborough?"),
    ("B_membership", "B. Membership / coverage / aliases", "dataset_membership", "Is Dover one of the 200 towns?"),
    ("B_membership", "B. Membership / coverage / aliases", "dataset_membership", "Is Stow in your dataset?"),
    ("B_membership", "B. Membership / coverage / aliases", "dataset_membership", "Do you support recommendations for Maynard?"),
    ("B_membership", "B. Membership / coverage / aliases", "dataset_membership", "Can you answer questions about Hudson?"),
    ("B_membership", "B. Membership / coverage / aliases", "refuse_out_of_scope", "Is Providence outside your scope?"),
    ("B_membership", "B. Membership / coverage / aliases", "refuse_out_of_scope", "Is Nashua outside your Massachusetts town list?"),
    ("B_membership", "B. Membership / coverage / aliases", "refuse_out_of_scope", "Do you have data for Springfield or is it out of scope?"),
    ("B_membership", "B. Membership / coverage / aliases", "refuse_out_of_scope", "Is Amherst considered in this project?"),
    ("B_membership", "B. Membership / coverage / aliases", "refuse_out_of_scope", "Is Cape Cod included in your list?"),
    ("B_membership", "B. Membership / coverage / aliases", "refuse_out_of_scope", "Do you include towns beyond Massachusetts?"),
    ("B_membership", "B. Membership / coverage / aliases", "dataset_membership", "Is Worcester in the 200-town scope?"),
    ("B_membership", "B. Membership / coverage / aliases", "dataset_membership", "Is \"Manchester-by-the-Sea\" stored with hyphens?"),
    ("B_membership", "B. Membership / coverage / aliases", "refuse_out_of_scope", "What would you do if I ask about a town you don't cover?"),
    # C. Typos / fuzzy town names
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "What do you have for Shrewsbery?"),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Is Worchester in your data?"),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Give me stats for Burllington."),
    ("C_typo", "C. Typos / fuzzy town names", "compare_towns", "Compare Framinghamm and Natick."),
    ("C_typo", "C. Typos / fuzzy town names", "dataset_membership", "Is Westfordd a town you track?"),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "What is the commute from Marlborogh?"),
    ("C_typo", "C. Typos / fuzzy town names", "compare_towns", "Compare Lexingon and Winchester."),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Tell me about Manchster by the Sea."),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Is Swampscottt coastal?"),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Does Welesley have good schools?"),
    ("C_typo", "C. Typos / fuzzy town names", "compare_towns", "Compare Needam and Dedham."),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Is Brrokline expensive?"),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "What is the crime rate in Chelesa?"),
    ("C_typo", "C. Typos / fuzzy town names", "lookup_single_town", "Does Somervile have a short commute?"),
    ("C_typo", "C. Typos / fuzzy town names", "compare_towns", "Compare North Readng and Reading."),
    # D. Natural comparison questions
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Between Acton and Concord, which has better schools?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Between Lynn and Revere, which is safer?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Would Westford or Sharon be better for schools and safety?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Is Burlington more dangerous than Waltham?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Is Quincy cheaper than Milton?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Does Newton cost more than Needham?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Which town has the longer commute, Rockport or Gloucester?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Which has lower crime, Beverly or Salem?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Is Brookline more expensive than Cambridge?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Would Marblehead or Swampscott be more affordable?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Which one is more family-friendly, Reading or Stoneham?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Is Worcester worse than Shrewsbury for safety?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Which has a stronger school profile, Lexington or Arlington?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Does Milton beat Quincy for schools?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Which is the better value, Braintree or Weymouth?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Compare Medford and Malden for commute."),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Is Chelsea less safe than Everett?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Which is better if price matters, Wellesley or Framingham?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Which is more coastal, Salem or Peabody?"),
    ("D_compare", "D. Natural comparison questions", "compare_towns", "Is Beverly a better family option than Lynn?"),
    # E. Budget / price constraints
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "Find towns under 650k with acceptable safety."),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "I want the best places below 850k with no missing price data."),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "Give me options at or below $700,000."),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "My budget is 950k; I care about schools first."),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "Find me a town under 575k with a tolerable commute."),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "What can I get if my max is 450k?"),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "Find towns below 1.2 million with very good schools."),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "Keep everything under $1 million and avoid partial data."),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "I want affordability first, but not a terrible safety score."),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "Show me towns under 725k where schools are at least decent."),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "Find the best towns at $550k or less."),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "I can stretch to 900k only if the town is very strong."),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "Don't show me anything over 800k."),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "Find full-data towns under 600k."),
    ("E_budget", "E. Budget / price constraints", "recommend_structured", "Under 700k, what are my strongest tradeoff options?"),
    # F. Commute / distance constraints
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "I need to be under 20 minutes from Boston."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Find me towns within half an hour of Boston."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Give me suburbs around 30 to 45 minutes out."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "I prefer being 45 minutes or more from Boston."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Find towns with a commute no longer than 40 minutes."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "I want farther-out towns, not inner suburbs."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Show me places where Boston commute is rough but schools are good."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Find options with commute between 25 and 35 minutes."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "I want short commute and low price."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Find places with commute under 50 minutes and price under 750k."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Which towns are close enough to Boston but still safe?"),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Give me towns beyond 50 minutes with affordability upside."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "I don't want to be too close to Boston; show me outer suburbs."),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "What towns are 40–60 minutes from Boston?"),
    ("F_commute", "F. Commute / distance constraints", "recommend_structured", "Find places where commute is not the priority."),
    # G. Coastal / region filters
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "I only want coastal towns below 950k."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Show me ocean-adjacent towns with decent safety."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Find North Shore towns that are not extremely expensive."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Give me South Shore options with family appeal."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "I want coastal, but not city-like."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Find beach-area towns under 850k."),
    ("G_coastal", "G. Coastal / region filters", "lookup_single_town", "Is Salem coastal in your system?"),
    ("G_coastal", "G. Coastal / region filters", "lookup_single_town", "Is Beverly considered coastal?"),
    ("G_coastal", "G. Coastal / region filters", "lookup_single_town", "Is Reading inland or coastal?"),
    ("G_coastal", "G. Coastal / region filters", "lookup_single_town", "Is Boxford a coast town?"),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Find coastal towns where schools are above average."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Find North Shore towns with safer profiles."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Find South Shore towns with lower prices."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "I want a town near the water but not over $1 million."),
    ("G_coastal", "G. Coastal / region filters", "recommend_structured", "Exclude inland towns from the results."),
    # H. Semantic / vibe
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "I want a calm, polished suburb with strong schools."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "Find a town with a similar feel to Concord but cheaper."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "I like Newton but want less expensive options."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "I want something like Brookline but less urban."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "Give me a town with a historic village feel."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "Find a quiet town that still feels connected."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "I want a suburb with educated-family vibes."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "Find something like Winchester but less expensive."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "I want a lower-cost version of Wellesley."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "Find towns like Westford but closer to Boston."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "I want a safe, low-drama suburb with good schools."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "Find a town that feels suburban but not isolated."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "I want a coastal-feeling town without luxury pricing."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "Find a balanced town for a family that wants value."),
    ("H_semantic", "H. Semantic / vibe", "recommend_semantic", "I want a place with good schools where price is the main compromise."),
    # I. Inverted / unusual preferences
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "Show me cheaper towns even if school quality drops."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "Find towns where safety is weak but affordability is strong."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "I only care about price and commute; ignore schools."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "Find places with higher crime but lower cost."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "I want the cheapest towns in the dataset."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "Show towns with bad safety and short commute."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "Find towns where schools are below average but homes are cheaper."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "Rank affordable towns by highest crime rate."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "I want low-price options even if they have major downsides."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "Show me places that are not top-ranked but might be practical."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "Find towns where commute is good but schools are weak."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "I want affordable towns with clear warnings."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "Show me the tradeoff-heavy options under 600k."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "Find towns with the worst safety among towns under 700k."),
    ("I_inverted", "I. Inverted / unusual preferences", "recommend_structured", "Give me cheap towns close to Boston, even if safety is poor."),
]


def main() -> None:
    cases = []
    counters: dict[str, int] = {}
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
        "description": "Holdout Set #2 — fresh 150 prompts (harder phrasing)",
        "prompt_count": len(cases),
        "cases": cases,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} cases to {OUT}")


if __name__ == "__main__":
    main()
