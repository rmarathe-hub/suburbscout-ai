#!/usr/bin/env python3
"""Estimate Holdout v6 intent routing (Phase 1.5 hybrid, no full orchestrator)."""

from __future__ import annotations

import asyncio
import sys
from collections import defaultdict
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.hybrid_intent_router import classify_query_hybrid, should_use_llm_intent_fallback
from app.intent_classifier import classify_user_intent
from app.llm_intent_classifier import llm_fallback_available

CASES: list[tuple[str, str, str]] = [
    ("A_lookup", "lookup_single_town", "What does your suburb file say about Gardner?"),
    ("A_lookup", "lookup_single_town", "Give me the data card for Shrewsbury."),
    ("A_lookup", "lookup_single_town", "What are Acton's commute and school numbers?"),
    ("A_lookup", "lookup_single_town", "Does Burlington sit on the expensive side?"),
    ("A_lookup", "lookup_single_town", "Check Worcester's record for missing values."),
    ("A_lookup", "lookup_single_town", "What are Westford's main suburb stats?"),
    ("A_lookup", "lookup_single_town", "Is Salem flagged as high-crime or low-crime?"),
    ("A_lookup", "lookup_single_town", "What housing price do you have saved for Quincy?"),
    ("A_lookup", "lookup_single_town", "Does Framingham have a complete row?"),
    ("A_lookup", "lookup_single_town", "How far is Rockport from the Boston destination point?"),
    ("A_lookup", "lookup_single_town", "Is Newton's school data present?"),
    ("A_lookup", "lookup_single_town", "What crime/safety information do you have for Chelsea?"),
    ("A_lookup", "lookup_single_town", "Summarize the Lynn entry."),
    ("A_lookup", "lookup_single_town", "What commute time is listed for Plymouth?"),
    ("A_lookup", "lookup_single_town", "Show Ipswich's housing, school, and safety info."),
    ("A_lookup", "lookup_single_town", "Is Lowell a partial-data town?"),
    ("A_lookup", "lookup_single_town", "What school number is listed for North Reading?"),
    ("A_lookup", "lookup_single_town", "Does Beverly have the coastal marker?"),
    ("A_lookup", "lookup_single_town", "What is Concord's listed median price?"),
    ("A_lookup", "lookup_single_town", "Is Peabody classified as not coastal?"),
    ("B_membership", "dataset_membership", "If I type Westboro, will the app understand it?"),
    ("B_membership", "dataset_membership", "Is Foxboro recognized by the system?"),
    ("B_membership", "dataset_membership", "Does Foxborough exist in your dataset?"),
    ("B_membership", "dataset_membership", "Are there records for Marlborough?"),
    ("B_membership", "dataset_membership", "Does the app know Marlboro means Marlborough?"),
    ("B_membership", "dataset_membership", "Is Northboro a valid alias?"),
    ("B_membership", "dataset_membership", "Can I use Northborough as a town name?"),
    ("B_membership", "dataset_membership", "Did Dover make the town list?"),
    ("B_membership", "dataset_membership", "Is Stow included?"),
    ("B_membership", "dataset_membership", "Are recommendations available for Maynard?"),
    ("B_membership", "dataset_membership", "Can Hudson be ranked by this tool?"),
    ("B_membership", "refuse_out_of_scope", "Would Providence be outside the supported geography?"),
    ("B_membership", "refuse_out_of_scope", "Is Nashua rejected because it is not Massachusetts?"),
    ("B_membership", "refuse_out_of_scope", "Do you exclude Springfield from this suburb project?"),
    ("B_membership", "refuse_out_of_scope", "Would Amherst be unavailable here?"),
    ("B_membership", "refuse_out_of_scope", "Are Cape communities part of your supported towns?"),
    ("B_membership", "refuse_out_of_scope", "Does this cover anything outside MA?"),
    ("B_membership", "dataset_membership", "Is Worcester loaded into the 200-town dataset?"),
    ("B_membership", "dataset_membership", "Is Manchester by the Sea matched to Manchester-by-the-Sea?"),
    ("B_membership", "refuse_out_of_scope", "How do you handle a place that is absent from the dataset?"),
    ("C_typo", "lookup_single_town", "Search for Shrewsbry."),
    ("C_typo", "dataset_membership", "Is Worecester supported?"),
    ("C_typo", "lookup_single_town", "What is Burlignton's commute?"),
    ("C_typo", "compare_towns", "Compare Framinghan and Natick."),
    ("C_typo", "dataset_membership", "Can you recognize Westfird?"),
    ("C_typo", "lookup_single_town", "Show Marlborugh's home price."),
    ("C_typo", "compare_towns", "Lexinton and Winchester — which is better for safety?"),
    ("C_typo", "lookup_single_town", "Pull up Manchestr-by-the-Sea."),
    ("C_typo", "lookup_single_town", "Is Swampscotte coastal?"),
    ("C_typo", "lookup_single_town", "Does Wellesely have strong schools?"),
    ("C_typo", "compare_towns", "Needam and Dedham: compare price."),
    ("C_typo", "lookup_single_town", "Is Brokkline loaded?"),
    ("C_typo", "lookup_single_town", "What is Chelsa's crime number?"),
    ("C_typo", "lookup_single_town", "Somervile to Boston commute?"),
    ("C_typo", "compare_towns", "North Readin versus Reading for safety."),
    ("D_compare", "compare_towns", "Acton compared to Concord — which has lower crime?"),
    ("D_compare", "compare_towns", "Lynn or Revere: where is safety worse?"),
    ("D_compare", "compare_towns", "For a family with kids, Westford or Sharon?"),
    ("D_compare", "compare_towns", "Is Burlington safer or less safe than Waltham?"),
    ("D_compare", "compare_towns", "Quincy and Milton — which has the lower home price?"),
    ("D_compare", "compare_towns", "Which town is more expensive: Newton or Needham?"),
    ("D_compare", "compare_towns", "Rockport compared with Gloucester: which is farther?"),
    ("D_compare", "compare_towns", "Salem or Beverly for safety?"),
    ("D_compare", "compare_towns", "Is Cambridge more affordable than Brookline?"),
    ("D_compare", "compare_towns", "Which would cost less, Marblehead or Swampscott?"),
    ("D_compare", "compare_towns", "Reading compared with Stoneham for schools."),
    ("D_compare", "compare_towns", "Safety-wise, Worcester or Shrewsbury?"),
    ("D_compare", "compare_towns", "Lexington and Arlington: who has the better school score?"),
    ("D_compare", "compare_towns", "Is Milton more expensive than Quincy?"),
    ("D_compare", "compare_towns", "Braintree or Weymouth for overall value?"),
    ("D_compare", "compare_towns", "Which has the easier Boston commute, Malden or Medford?"),
    ("D_compare", "compare_towns", "Everett versus Chelsea on crime."),
    ("D_compare", "compare_towns", "For affordability, should I look at Framingham or Wellesley?"),
    ("D_compare", "compare_towns", "Which is coastal: Peabody or Salem?"),
    ("D_compare", "compare_towns", "Family fit: Lynn or Beverly?"),
    ("E_budget", "recommend_structured", "Find safe-enough towns with prices at 650k or less."),
    ("E_budget", "recommend_structured", "Only include towns under 850k with known home values."),
    ("E_budget", "recommend_structured", "Show options capped at seven hundred thousand."),
    ("E_budget", "recommend_structured", "I can spend about 950k and want strong school quality."),
    ("E_budget", "recommend_structured", "Search below 575k with a commute that is not awful."),
    ("E_budget", "recommend_structured", "What towns are possible with a 450k budget?"),
    ("E_budget", "recommend_structured", "Give me school-focused towns below 1.2 million."),
    ("E_budget", "recommend_structured", "Keep results under one million dollars and avoid missing housing."),
    ("E_budget", "recommend_structured", "I want cheap first, but safety cannot be terrible."),
    ("E_budget", "recommend_structured", "Under 725k, show towns with okay-or-better schools."),
    ("E_budget", "recommend_structured", "What looks best with a hard 550k limit?"),
    ("E_budget", "recommend_structured", "Up to 900k is fine only if the town scores well."),
    ("E_budget", "recommend_structured", "Filter away anything above $800,000."),
    ("E_budget", "recommend_structured", "Only complete rows under $600k."),
    ("E_budget", "recommend_structured", "Show me realistic value picks under 700k."),
    ("F_commute", "recommend_structured", "I want towns inside 20 minutes to Boston."),
    ("F_commute", "recommend_structured", "Which towns are no more than 30 minutes out?"),
    ("F_commute", "recommend_structured", "Show suburbs in the 30-to-45-minute zone."),
    ("F_commute", "recommend_structured", "I want to be at least 45 minutes away."),
    ("F_commute", "recommend_structured", "Keep Boston drive time under 40 minutes."),
    ("F_commute", "recommend_structured", "Prefer far-out suburbs over close suburbs."),
    ("F_commute", "recommend_structured", "I can tolerate a long commute if schools are great."),
    ("F_commute", "recommend_structured", "Find towns from 25 minutes to 35 minutes."),
    ("F_commute", "recommend_structured", "Quick Boston access plus affordability."),
    ("F_commute", "recommend_structured", "Under 50 minutes and below 750k."),
    ("F_commute", "recommend_structured", "Close to Boston while still having decent safety."),
    ("F_commute", "recommend_structured", "Cheaper towns past the 50-minute mark."),
    ("F_commute", "recommend_structured", "I want to avoid inner suburbs."),
    ("F_commute", "recommend_structured", "Give me towns around 40–60 minutes from Boston."),
    ("F_commute", "recommend_structured", "Commute can be bad if the price is better."),
    ("G_coastal", "recommend_structured", "Coastal results only, under 950k."),
    ("G_coastal", "recommend_structured", "Water-side towns with decent safety."),
    ("G_coastal", "recommend_structured", "North Shore options that are not luxury-priced."),
    ("G_coastal", "recommend_structured", "South Shore towns suitable for families."),
    ("G_coastal", "recommend_structured", "I want a coast town, but not an urban one."),
    ("G_coastal", "recommend_structured", "Beach-like suburbs below 850k."),
    ("G_coastal", "lookup_single_town", "Does Salem count as coastal in your tags?"),
    ("G_coastal", "lookup_single_town", "Beverly has a coastal label, right?"),
    ("G_coastal", "lookup_single_town", "Is Reading considered inland?"),
    ("G_coastal", "lookup_single_town", "Is Boxford away from the coast?"),
    ("G_coastal", "recommend_structured", "Coastal places with solid schools."),
    ("G_coastal", "recommend_structured", "Safer options on the North Shore."),
    ("G_coastal", "recommend_structured", "Budget-friendlier South Shore towns."),
    ("G_coastal", "recommend_structured", "Near water and below $1,000,000."),
    ("G_coastal", "recommend_structured", "Do not include inland towns."),
    ("H_semantic", "recommend_semantic", "I want a quiet affluent suburb with good schools."),
    ("H_semantic", "recommend_semantic", "Give me something that feels like Concord but costs less."),
    ("H_semantic", "recommend_semantic", "Newton is too pricey; find a similar-feeling alternative."),
    ("H_semantic", "recommend_semantic", "I like Brookline's access, but want more suburb feel."),
    ("H_semantic", "recommend_semantic", "Find towns with classic New England character."),
    ("H_semantic", "recommend_semantic", "Calm town, connected enough, not remote."),
    ("H_semantic", "recommend_semantic", "Educated parent community with strong schools."),
    ("H_semantic", "recommend_semantic", "A cheaper town with some Winchester feel."),
    ("H_semantic", "recommend_semantic", "Wellesley-type suburb without Wellesley prices."),
    ("H_semantic", "recommend_semantic", "Similar to Westford, but with less commute pain."),
    ("H_semantic", "recommend_semantic", "Safe, predictable, family-centered town."),
    ("H_semantic", "recommend_semantic", "Suburban but still close to useful amenities."),
    ("H_semantic", "recommend_semantic", "Coastal-ish feel without elite pricing."),
    ("H_semantic", "recommend_semantic", "Family value pick with balanced strengths."),
    ("H_semantic", "recommend_semantic", "I'll pay more if the schools are worth it."),
    ("I_inverted", "recommend_structured", "Find cheaper towns where I can accept weaker schools."),
    ("I_inverted", "recommend_structured", "Affordable places where safety is clearly a drawback."),
    ("I_inverted", "recommend_structured", "Do not care about schools; price and commute matter."),
    ("I_inverted", "recommend_structured", "Lower cost even if crime is higher."),
    ("I_inverted", "recommend_structured", "Show the bottom-priced towns in the dataset."),
    ("I_inverted", "recommend_structured", "Short drive to Boston, safety can be poor."),
    ("I_inverted", "recommend_structured", "Cheaper homes with below-average schools."),
    ("I_inverted", "recommend_structured", "Rank low-cost towns by worst crime."),
    ("I_inverted", "recommend_structured", "Give me cheap towns and be honest about problems."),
    ("I_inverted", "recommend_structured", "Practical but imperfect towns, not prestige picks."),
    ("I_inverted", "recommend_structured", "Good commute and cheap price, even with weak schools."),
    ("I_inverted", "recommend_structured", "Affordable options with warnings included."),
    ("I_inverted", "recommend_structured", "Below 600k, show towns with major compromises."),
    ("I_inverted", "recommend_structured", "Under 700k, which towns have the lowest safety scores?"),
    ("I_inverted", "recommend_structured", "Cheap plus close to Boston, even if risky."),
]


def compatible(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    if expected in ("lookup_single_town", "dataset_membership") and actual == "lookup_single_town":
        return True
    if expected == "recommend_structured" and actual == "recommend_semantic":
        return True
    if expected == "recommend_semantic" and actual == "recommend_structured":
        return True
    if expected == "refuse_out_of_scope" and actual in (
        "unsupported",
        "needs_clarification",
        "data_limit_question",
    ):
        return True
    return False


def route_matches_expected(expected: str, route_intent: str) -> bool:
    return compatible(expected, route_intent)


async def main() -> None:
    py_ok = hy_ok = 0
    llm_calls = 0
    unsupported = 0
    by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # py, hy, n
    fails: list[tuple[str, str, str, str, str]] = []

    for cat, expected, prompt in CASES:
        py = classify_user_intent(prompt)
        py_match = compatible(expected, py.intent)
        if py_match:
            py_ok += 1

        route = await classify_query_hybrid(prompt)
        if route.llm_fallback_used:
            llm_calls += 1
        if route.intent == "unsupported":
            unsupported += 1
        hy_match = route_matches_expected(expected, route.intent)
        if hy_match:
            hy_ok += 1
        else:
            fails.append((cat, expected, py.intent, route.intent, prompt[:55]))

        by_cat[cat][1] += 1
        if py_match:
            by_cat[cat][0] += 1
        if hy_match:
            by_cat[cat][2] += 1

    n = len(CASES)
    print(f"Python-only intent: {py_ok}/{n} ({100*py_ok/n:.1f}%)")
    print(f"Hybrid route intent (1.5): {hy_ok}/{n} ({100*hy_ok/n:.1f}%)")
    print(f"LLM fallback would run: {llm_calls}/{n}")
    print(f"Unsupported routes: {unsupported}/{n}")
    print(f"LLM available: {llm_fallback_available()}")
    print("\nBy category (python / hybrid):")
    labels = {
        "A_lookup": "A Lookup",
        "B_membership": "B Membership",
        "C_typo": "C Typo",
        "D_compare": "D Compare",
        "E_budget": "E Budget",
        "F_commute": "F Commute",
        "G_coastal": "G Coastal",
        "H_semantic": "H Semantic",
        "I_inverted": "I Inverted",
    }
    for cat in sorted(by_cat):
        p, total, h = by_cat[cat]
        print(f"  {labels.get(cat, cat)}: {p}/{total} python, {h}/{total} hybrid")

    print(f"\nHybrid failures ({len(fails)}):")
    for cat, exp, py_i, act, pr in fails[:20]:
        print(f"  [{cat}] exp={exp} py={py_i} route={act} | {pr}")
    if len(fails) > 20:
        print(f"  ... +{len(fails)-20} more")

    # Rough full-eval pass estimate
    strict_penalty = 3  # semantic validator quirks from v5
    est_pass = int(hy_ok * 0.97) - strict_penalty
    print(f"\nEstimated full holdout PASS (intent+validator): ~{est_pass}-{min(n, hy_ok + 5)}/150")


if __name__ == "__main__":
    asyncio.run(main())
