#!/usr/bin/env python3
"""Phase 1.1 Step 3 verification: constraint_parser.py."""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


def _check(label: str, query: str, **expected) -> None:
    from app.constraint_parser import parse_constraints

    prefs = parse_constraints(query)
    data = prefs.model_dump(exclude_none=True)
    for key, value in expected.items():
        if data.get(key) != value:
            raise AssertionError(
                f"{label}: expected {key}={value!r}, got {data.get(key)!r} (full={data})"
            )


def main() -> None:
    print("=== Phase 1.1 Step 3: constraint_parser ===\n")

    cases = [
        (
            "budget + safety + schools",
            "Safe suburb under $900k with good schools",
            {
                "budget_max": 900000,
                "safety_priority": "high",
                "school_priority": "high",
                "require_housing_for_budget": True,
            },
        ),
        (
            "county + commute max",
            "in Middlesex county, 30 mins away from Boston",
            {
                "county_preference": "Middlesex",
                "max_commute_minutes": 30,
            },
        ),
        (
            "coastal + affordability",
            "near ocean but not expensive",
            {
                "requires_coastal": True,
                "affordability_priority": "high",
            },
        ),
        (
            "min commute",
            "towns over 45 minutes from Boston",
            {
                "min_commute_minutes": 45,
            },
        ),
        (
            "north shore region",
            "North Shore family-friendly suburb with strong schools",
            {
                "region_preference": "North Shore / northeast suburbs",
                "region_key": "north_shore",
                "school_priority": "high",
            },
        ),
        (
            "like town + budget",
            "towns like Wellesley but I only have 650k",
            {
                "similar_to_town": "Wellesley",
                "budget_max": 650000,
            },
        ),
        (
            "relative safety + price",
            "safer than Lynn but cheaper than Newton",
            {
                "safer_than_town": "Lynn",
                "cheaper_than_town": "Newton",
            },
        ),
        (
            "quieter than reference",
            "not too far from Boston but quieter than Cambridge",
            {
                "max_commute_minutes": 50,
                "quieter_than_town": "Cambridge",
                "commute_priority": "high",
            },
        ),
        (
            "high crime mode",
            "high crime towns near Boston",
            {
                "prefer_high_crime": True,
                "commute_priority": "high",
            },
        ),
        (
            "affordable commute schools",
            "Affordable suburb with strong schools and decent commute",
            {
                "affordability_priority": "high",
                "school_priority": "high",
                "commute_priority": "high",
            },
        ),
        (
            "max commute under phrasing",
            "under 30 min commute to Boston",
            {
                "max_commute_minutes": 30,
            },
        ),
        (
            "south shore region",
            "South Shore town with good schools",
            {
                "region_preference": "South Shore",
                "region_key": "south_shore",
                "school_priority": "high",
            },
        ),
        (
            "metrowest region",
            "MetroWest suburb under 800k",
            {
                "region_preference": "MetroWest",
                "region_key": "metrowest",
                "budget_max": 800000,
            },
        ),
        (
            "coastal phrasing beach",
            "quiet beach town with good schools",
            {
                "requires_coastal": True,
                "school_priority": "high",
            },
        ),
        (
            "essex county",
            "Essex county town under 700k",
            {
                "county_preference": "Essex",
                "budget_max": 700000,
            },
        ),
        (
            "650k bare k",
            "strong schools 650k max",
            {
                "budget_max": 650000,
                "school_priority": "high",
            },
        ),
    ]

    print(f"1. Structured parse cases ({len(cases)})")
    for label, query, expected in cases:
        try:
            _check(label, query, **expected)
            print(f"  PASS: {label}")
        except AssertionError as exc:
            print(f"  FAIL: {exc}")
            sys.exit(1)

    from app.constraint_parser import extract_town_mentions, parse_constraints

    print("\n2. Town extraction")
    known, unknown = extract_town_mentions("Compare Acton and Framingham")
    if "Acton" not in known or "Framingham" not in known:
        print(f"  FAIL: compare towns — known={known}")
        sys.exit(1)
    print("  PASS: named towns extracted for compare")

    known2, unknown2 = extract_town_mentions("is Charlton in your dataset")
    if "Charlton" not in unknown2:
        print(f"  FAIL: Charlton should be unknown — {unknown2}")
        sys.exit(1)
    print("  PASS: unknown town Charlton detected")

    gardner = parse_constraints("commute for Gardner")
    if gardner.named_towns != ["Gardner"]:
        print(f"  FAIL: Gardner named town — {gardner.named_towns}")
        sys.exit(1)
    print("  PASS: Gardner in named_towns")

    print("\n3. ranking.parse_preferences_from_query delegation")
    from app.ranking import parse_preferences_from_query

    legacy = parse_preferences_from_query("Safe Boston suburb under 900k with good schools")
    if legacy.budget_max != 900000 or legacy.safety_priority != "high":
        print(f"  FAIL: legacy wrapper — {legacy.model_dump()}")
        sys.exit(1)
    print("  PASS: ranking.parse_preferences_from_query uses constraint parser")

    print("\n4. parse_preferences_tool")
    from app.tools import parse_preferences_tool

    tool_out = parse_preferences_tool("in Middlesex county, 30 mins away from Boston")
    if tool_out.get("county_preference") != "Middlesex" or tool_out.get("max_commute_minutes") != 30:
        print(f"  FAIL: tool output — {tool_out}")
        sys.exit(1)
    print("  PASS: parse_preferences_tool returns new constraint fields")

    print("\nStep 3 verification: PASSED")
    print("Next: Step 4 — ranking.py hard filters")


if __name__ == "__main__":
    main()
