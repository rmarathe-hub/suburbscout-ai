#!/usr/bin/env python3
"""Phase 1.1 Step 6 verification: response_validator.py."""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


def _assert_valid(label: str, result) -> None:
    if not result.valid:
        raise AssertionError(f"{label}: expected valid, errors={result.errors}")


def _assert_invalid(label: str, result, *, contains: str) -> None:
    if result.valid:
        raise AssertionError(f"{label}: expected invalid")
    if contains not in " ".join(result.errors).lower():
        raise AssertionError(f"{label}: expected error containing {contains!r}, got {result.errors}")


def main() -> None:
    print("=== Phase 1.1 Step 6: response_validator ===\n")

    from app.constraint_parser import parse_constraints
    from app.query_router import classify_query
    from app.ranking import rank_suburbs
    from app.response_validator import (
        validate_agent_response,
        validate_comparison,
        validate_lookup_response,
        validate_ranked_results,
    )
    from app.tools import compare_suburbs_tool, get_town_facts

    print("1. Valid ranked results (Middlesex + 30 min)")
    prefs = parse_constraints("in Middlesex county, 30 mins away from Boston")
    good = rank_suburbs(prefs, top_n=5)
    _assert_valid("middlesex rank", validate_ranked_results(good, prefs, query=prefs.raw_query or ""))
    print("  PASS: valid Middlesex + commute results")

    print("\n2. Invalid budget violation (synthetic)")
    bad_budget = [
        {
            "name": "Newton",
            "score": 8.0,
            "data": {
                "latest_home_price": 1_525_000,
                "county": "Middlesex",
                "drive_minutes_to_boston": 17.5,
                "is_coastal": False,
            },
        }
    ]
    budget_prefs = parse_constraints("safe suburb under $900k")
    _assert_invalid(
        "budget violation",
        validate_ranked_results(bad_budget, budget_prefs, query="under 900k"),
        contains="exceeds budget",
    )
    print("  PASS: budget violation detected")

    print("\n3. Invalid coastal violation (synthetic)")
    bad_coastal = [
        {
            "name": "Reading",
            "score": 7.0,
            "data": {
                "latest_home_price": 600_000,
                "county": "Middlesex",
                "drive_minutes_to_boston": 21.8,
                "is_coastal": False,
            },
        }
    ]
    coastal_prefs = parse_constraints("coastal town under 900k")
    _assert_invalid(
        "coastal violation",
        validate_ranked_results(bad_coastal, coastal_prefs, query="coastal"),
        contains="non-coastal",
    )
    print("  PASS: coastal violation detected")

    print("\n4. Lookup response — Gardner found")
    gardner = get_town_facts("Gardner")
    _assert_valid("gardner lookup", validate_lookup_response(gardner, requested_town="Gardner"))
    print("  PASS: Gardner lookup valid")

    print("\n5. Lookup response — Charlton not found")
    charlton = get_town_facts("Charlton")
    _assert_valid("charlton lookup", validate_lookup_response(charlton, requested_town="Charlton"))
    if charlton.get("found"):
        print("  FAIL: Charlton should not be found")
        sys.exit(1)
    print("  PASS: Charlton not-found lookup valid")

    print("\n6. Compare response")
    comp = compare_suburbs_tool("Acton", "Framingham")
    _assert_valid(
        "compare",
        validate_comparison(comp, town_a="Acton", town_b="Framingham"),
    )
    print("  PASS: Acton vs Framingham comparison valid")

    print("\n7. Agent response — structured recommend")
    budget_query = "Safe suburb under $900k with good schools"
    budget_prefs = parse_constraints(budget_query)
    route = classify_query(budget_query)
    agent_ok = {
        "query": budget_query,
        "preferences": budget_prefs.model_dump(),
        "semantic_candidates": None,
        "top_matches": rank_suburbs(budget_prefs, top_n=3),
        "comparison": None,
        "final_recommendation": "Sharon is the top match.",
        "score_disclaimer": "Scores are 0-10 percentile ranks within the 200-town dataset, not official government ratings.",
    }
    _assert_valid("agent structured", validate_agent_response(agent_ok, query=agent_ok["query"], route=route))
    print("  PASS: structured agent response valid")

    print("\n8. Agent response — compare")
    compare_route = classify_query("Compare Acton and Framingham")
    agent_compare = {
        "query": "Compare Acton and Framingham",
        "preferences": None,
        "top_matches": [],
        "comparison": comp,
        "final_recommendation": "Acton vs Framingham summary",
        "score_disclaimer": "Scores are 0-10 percentile ranks within the 200-town dataset, not official government ratings.",
    }
    _assert_valid(
        "agent compare",
        validate_agent_response(agent_compare, query=agent_compare["query"], route=compare_route),
    )
    print("  PASS: compare agent response valid")

    print("\n9. Agent response — lookup mentions town")
    lookup_route = classify_query("commute for Gardner")
    agent_lookup = {
        "query": "commute for Gardner",
        "preferences": None,
        "top_matches": [],
        "comparison": None,
        "final_recommendation": "Gardner has a 69.5 minute drive commute to Boston.",
        "score_disclaimer": "Scores are 0-10 percentile ranks within the 200-town dataset, not official government ratings.",
    }
    _assert_valid(
        "agent lookup",
        validate_agent_response(agent_lookup, query=agent_lookup["query"], route=lookup_route),
    )
    print("  PASS: lookup agent response mentions Gardner")

    print("\n10. no_matches ranked payload")
    empty_rank = [{"no_matches": True, "message": "No towns matched.", "filters_applied": ["coastal"]}]
    no_match = validate_ranked_results(empty_rank, parse_constraints("coastal under 10 min"), query="x")
    if not no_match.valid:
        print(f"  FAIL: no_matches should validate — {no_match.errors}")
        sys.exit(1)
    print("  PASS: no_matches payload validates")

    print("\nStep 6 verification: PASSED")
    print("Next: Step 7 — orchestrator.py")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"  FAIL: {exc}")
        sys.exit(1)
