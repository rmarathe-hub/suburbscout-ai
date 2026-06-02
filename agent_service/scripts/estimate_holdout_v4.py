#!/usr/bin/env python3
"""Estimate Holdout v4 intent routing (no full orchestrator)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.intent_classifier import classify_user_intent

CASES: list[tuple[str, str, str]] = [
    # A Lookup
    ("A_lookup", "lookup_single_town", "Open Gardner's suburb entry."),
    ("A_lookup", "lookup_single_town", "What numbers do you have saved for Shrewsbury?"),
    ("A_lookup", "lookup_single_town", "Give me Acton's safety and commute snapshot."),
    ("A_lookup", "lookup_single_town", "Is Burlington expensive compared to the dataset?"),
    ("A_lookup", "lookup_single_town", "Which data points are missing for Worcester?"),
    ("A_lookup", "lookup_single_town", "Show Westford's stored housing, commute, and school data."),
    ("A_lookup", "lookup_single_town", "Based on your records, is Salem a safer or riskier town?"),
    ("A_lookup", "lookup_single_town", "What home price is listed for Quincy?"),
    ("A_lookup", "lookup_single_town", "Is Framingham missing anything important in the dataset?"),
    ("A_lookup", "lookup_single_town", "How far out is Rockport from South Station?"),
    ("A_lookup", "lookup_single_town", "Does Newton have a recorded school metric?"),
    ("A_lookup", "lookup_single_town", "What safety score is assigned to Chelsea?"),
    ("A_lookup", "lookup_single_town", "Give me Lynn's full town summary."),
    ("A_lookup", "lookup_single_town", "How long is the Boston commute from Plymouth?"),
    ("A_lookup", "lookup_single_town", "What are Ipswich's strongest and weakest numbers?"),
    ("A_lookup", "lookup_single_town", "Is Lowell classified as complete data?"),
    ("A_lookup", "lookup_single_town", "What school score do you store for North Reading?"),
    ("A_lookup", "lookup_single_town", "Is Beverly labeled waterfront/coastal?"),
    ("A_lookup", "lookup_single_town", "What does Concord cost in your housing data?"),
    ("A_lookup", "lookup_single_town", "Does Peabody count as inland?"),
    # B Membership
    ("B_membership", "dataset_membership", "Will Westboro work as a search term?"),
    ("B_membership", "dataset_membership", "Does the system translate Foxboro into Foxborough?"),
    ("B_membership", "dataset_membership", "Is Foxborough actually loaded?"),
    ("B_membership", "dataset_membership", "Are Marlborough results available?"),
    ("B_membership", "dataset_membership", "Would Marlboro be accepted as an alternate spelling?"),
    ("B_membership", "dataset_membership", "Does Northboro redirect to Northborough?"),
    ("B_membership", "dataset_membership", "Can Northborough be queried directly?"),
    ("B_membership", "dataset_membership", "Is Dover inside the project's town universe?"),
    ("B_membership", "dataset_membership", "Do you have Stow in the loaded towns?"),
    ("B_membership", "dataset_membership", "Is Maynard searchable?"),
    ("B_membership", "dataset_membership", "Can Hudson be used in recommendations?"),
    ("B_membership", "refuse_out_of_scope", "Would Providence be rejected as outside scope?"),
    ("B_membership", "refuse_out_of_scope", "Is Nashua unsupported because it is outside MA?"),
    ("B_membership", "refuse_out_of_scope", "Does Springfield fall outside this Boston-suburb dataset?"),
    ("B_membership", "refuse_out_of_scope", "Would Amherst be excluded from this app?"),
    ("B_membership", "refuse_out_of_scope", "Are Cape Cod towns part of the project?"),
    ("B_membership", "refuse_out_of_scope", "Can I ask about towns outside Massachusetts?"),
    ("B_membership", "dataset_membership", "Did Worcester make it into the loaded 200 towns?"),
    ("B_membership", "dataset_membership", "Do you store Manchester-by-the-Sea under that exact name?"),
    ("B_membership", "refuse_out_of_scope", "How does the app respond when the town is not loaded?"),
    # C Typo
    ("C_typo", "lookup_single_town", "Look up Shrewsbary."),
    ("C_typo", "lookup_single_town", "Can you find Worscester?"),
    ("C_typo", "lookup_single_town", "Show Burllngton's school data."),
    ("C_typo", "compare_towns", "Framinghm vs Natick for safety."),
    ("C_typo", "dataset_membership", "Is Westfrod in scope?"),
    ("C_typo", "lookup_single_town", "Give me Marlborugh's price."),
    ("C_typo", "compare_towns", "Compare Lexinton and Winchester."),
    ("C_typo", "lookup_single_town", "What do you know about Manchstr by the Sea?"),
    ("C_typo", "lookup_single_town", "Is Swampscutt near the coast?"),
    ("C_typo", "lookup_single_town", "Does Welsley look expensive?"),
    ("C_typo", "compare_towns", "Needhm versus Dedham for commute."),
    ("C_typo", "lookup_single_town", "Is Brooklne in your database?"),
    ("C_typo", "lookup_single_town", "Chelsa crime score?"),
    ("C_typo", "lookup_single_town", "Somervill commute time?"),
    ("C_typo", "compare_towns", "North Readng vs Readng for schools."),
    # D Compare
    ("D_compare", "compare_towns", "Acton or Concord — which has the safer profile?"),
    ("D_compare", "compare_towns", "Lynn compared with Revere: which one has more crime?"),
    ("D_compare", "compare_towns", "For a family, Sharon or Westford?"),
    ("D_compare", "compare_towns", "Is Burlington worse than Waltham on crime?"),
    ("D_compare", "compare_towns", "Between Quincy and Milton, which is cheaper?"),
    ("D_compare", "compare_towns", "Needham or Newton — which has the higher price?"),
    ("D_compare", "compare_towns", "Is Rockport farther from Boston than Gloucester?"),
    ("D_compare", "compare_towns", "Beverly and Salem: which one has better safety?"),
    ("D_compare", "compare_towns", "Compare Cambridge and Brookline on affordability."),
    ("D_compare", "compare_towns", "Would Marblehead or Swampscott cost less?"),
    ("D_compare", "compare_towns", "Reading against Stoneham: who has stronger schools?"),
    ("D_compare", "compare_towns", "Is Worcester's safety profile worse than Shrewsbury's?"),
    ("D_compare", "compare_towns", "Lexington vs Arlington for school quality."),
    ("D_compare", "compare_towns", "Does Milton lose to Quincy on price?"),
    ("D_compare", "compare_towns", "Weymouth or Braintree if I care about value?"),
    ("D_compare", "compare_towns", "Malden or Medford for getting into Boston faster?"),
    ("D_compare", "compare_towns", "Chelsea compared to Everett — which is more dangerous?"),
    ("D_compare", "compare_towns", "If I want the cheaper town, Wellesley or Framingham?"),
    ("D_compare", "compare_towns", "Peabody and Salem: which one is actually coastal?"),
    ("D_compare", "compare_towns", "Lynn or Beverly for family livability?"),
    # E Budget
    ("E_budget", "recommend_structured", "Recommend places no higher than 650k with decent safety."),
    ("E_budget", "recommend_structured", "Show only towns below 850k that have housing data."),
    ("E_budget", "recommend_structured", "Find options with a $700k ceiling."),
    ("E_budget", "recommend_structured", "I have 950k to spend and want the best schools possible."),
    ("E_budget", "recommend_structured", "Suggest towns under 575k where the commute is still usable."),
    ("E_budget", "recommend_structured", "What towns fit a 450k limit?"),
    ("E_budget", "recommend_structured", "Below 1.2M, which towns have the best school upside?"),
    ("E_budget", "recommend_structured", "Keep the search below $1M and avoid incomplete records."),
    ("E_budget", "recommend_structured", "Prioritize cheap towns, but don't give me extremely unsafe places."),
    ("E_budget", "recommend_structured", "Under 725k, find towns with respectable schools."),
    ("E_budget", "recommend_structured", "What are the best choices if my cap is 550k?"),
    ("E_budget", "recommend_structured", "I could afford 900k, but only for a very strong suburb."),
    ("E_budget", "recommend_structured", "Exclude any result above 800k."),
    ("E_budget", "recommend_structured", "I only want complete-data towns under 600k."),
    ("E_budget", "recommend_structured", "What are the best compromise towns under 700k?"),
    # F Commute
    ("F_commute", "recommend_structured", "Find towns less than a 20-minute drive to Boston."),
    ("F_commute", "recommend_structured", "Which suburbs are within 30 minutes?"),
    ("F_commute", "recommend_structured", "I want the 30–45 minute suburbs."),
    ("F_commute", "recommend_structured", "Show towns at least 45 minutes away from Boston."),
    ("F_commute", "recommend_structured", "Keep the commute capped at 40 minutes."),
    ("F_commute", "recommend_structured", "Give me outer-ring suburbs instead of inner-ring ones."),
    ("F_commute", "recommend_structured", "Which towns have long commutes but strong schools?"),
    ("F_commute", "recommend_structured", "Find towns in the 25–35 minute commute range."),
    ("F_commute", "recommend_structured", "Low price and quick commute are my main goals."),
    ("F_commute", "recommend_structured", "Give me places under 50 minutes and under 750k."),
    ("F_commute", "recommend_structured", "Which towns are close to Boston without being too unsafe?"),
    ("F_commute", "recommend_structured", "Show cheaper options more than 50 minutes out."),
    ("F_commute", "recommend_structured", "Avoid the closest-in suburbs."),
    ("F_commute", "recommend_structured", "Which towns sit roughly 40 to 60 minutes from Boston?"),
    ("F_commute", "recommend_structured", "I am willing to trade commute time for better value."),
    # G Coastal
    ("G_coastal", "recommend_structured", "Find coastal options below 950k."),
    ("G_coastal", "recommend_structured", "Show seaside towns with reasonable safety."),
    ("G_coastal", "recommend_structured", "North Shore but not ultra-pricey."),
    ("G_coastal", "recommend_structured", "South Shore family-friendly picks."),
    ("G_coastal", "recommend_structured", "I want a coastal suburb that does not feel like a city."),
    ("G_coastal", "recommend_structured", "Beach-town options under 850k."),
    ("G_coastal", "lookup_single_town", "Does Salem have the coastal flag?"),
    ("G_coastal", "lookup_single_town", "Is Beverly marked as a coastal town?"),
    ("G_coastal", "lookup_single_town", "Does Reading have an inland label?"),
    ("G_coastal", "lookup_single_town", "Is Boxford classified inland?"),
    ("G_coastal", "recommend_structured", "Coastal towns with good school scores."),
    ("G_coastal", "recommend_structured", "North Shore places with better safety."),
    ("G_coastal", "recommend_structured", "South Shore towns that are relatively affordable."),
    ("G_coastal", "recommend_structured", "Near the ocean, but below one million."),
    ("G_coastal", "recommend_structured", "Filter out every non-coastal town."),
    # H Semantic
    ("H_semantic", "recommend_semantic", "Recommend a refined, quiet suburb with strong schools."),
    ("H_semantic", "recommend_semantic", "I want Concord energy without Concord pricing."),
    ("H_semantic", "recommend_semantic", "Newton is too expensive; what feels somewhat similar?"),
    ("H_semantic", "recommend_semantic", "Brookline feel, but more suburban."),
    ("H_semantic", "recommend_semantic", "Find a town with an old New England center."),
    ("H_semantic", "recommend_semantic", "Quiet suburb, but not cut off from everything."),
    ("H_semantic", "recommend_semantic", "I want a high-education family suburb."),
    ("H_semantic", "recommend_semantic", "Winchester alternative with a lower price tag."),
    ("H_semantic", "recommend_semantic", "Wellesley-style, but more affordable."),
    ("H_semantic", "recommend_semantic", "Westford vibe, shorter Boston drive."),
    ("H_semantic", "recommend_semantic", "Safe, calm, stable, and good for families."),
    ("H_semantic", "recommend_semantic", "Suburban feel without being remote."),
    ("H_semantic", "recommend_semantic", "Coastal atmosphere without the luxury price."),
    ("H_semantic", "recommend_semantic", "Balanced place for a family trying to maximize value."),
    ("H_semantic", "recommend_semantic", "Great schools, but I accept that the house price may hurt."),
    # I Inverted
    ("I_inverted", "recommend_structured", "Show cheaper towns even if the school score is not great."),
    ("I_inverted", "recommend_structured", "I'll accept weaker safety if the town is affordable."),
    ("I_inverted", "recommend_structured", "Ignore school quality and focus on price plus commute."),
    ("I_inverted", "recommend_structured", "Show lower-cost towns with higher crime."),
    ("I_inverted", "recommend_structured", "List the lowest-priced towns available."),
    ("I_inverted", "recommend_structured", "Short commute, even if safety is bad."),
    ("I_inverted", "recommend_structured", "Cheaper homes where schools are not a strength."),
    ("I_inverted", "recommend_structured", "For affordable towns, put the highest-crime ones first."),
    ("I_inverted", "recommend_structured", "Give me low-cost towns but warn me about the drawbacks."),
    ("I_inverted", "recommend_structured", "Show practical options that would not normally rank at the top."),
    ("I_inverted", "recommend_structured", "Good commute, weak schools, lower price."),
    ("I_inverted", "recommend_structured", "Affordable towns with obvious red flags included."),
    ("I_inverted", "recommend_structured", "Under 600k, show the most tradeoff-heavy places."),
    ("I_inverted", "recommend_structured", "Among towns below 700k, which have the weakest safety?"),
    ("I_inverted", "recommend_structured", "Cheap, close to Boston, and I can tolerate poor safety"),
]


def compatible(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    if expected == "dataset_membership" and actual == "lookup_single_town":
        return True
    if expected == "recommend_structured" and actual == "recommend_semantic":
        return True
    if expected == "recommend_semantic" and actual == "recommend_structured":
        return True
    if expected == "refuse_out_of_scope" and actual in ("unsupported", "needs_clarification"):
        return True
    return False


def main() -> None:
    from collections import defaultdict

    fails: list[tuple[str, str, str, str]] = []
    by_cat: dict[str, list[int]] = defaultdict(lambda: [0, 0])

    for cat, expected, prompt in CASES:
        actual = classify_user_intent(prompt).intent
        ok = compatible(expected, actual)
        by_cat[cat][1] += 1
        if ok:
            by_cat[cat][0] += 1
        else:
            fails.append((cat, prompt, expected, actual))

    total = len(CASES)
    passed = total - len(fails)
    print(f"INTENT ROUTING ESTIMATE: {passed}/{total} ({100*passed/total:.1f}%)")
    print()
    for cat in sorted(by_cat):
        p, t = by_cat[cat]
        print(f"  {cat}: {p}/{t} ({100*p/t:.0f}%)")
    print(f"\nFAILURES ({len(fails)}):")
    for cat, prompt, exp, act in fails:
        print(f"  [{cat}] {exp} -> {act}")
        print(f"    {prompt[:78]}")


if __name__ == "__main__":
    main()
