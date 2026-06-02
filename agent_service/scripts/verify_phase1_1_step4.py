#!/usr/bin/env python3
"""Phase 1.1 Step 4 verification: ranking hard filters."""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


def _assert_all(results: list[dict], label: str, fn) -> None:
    if not results:
        raise AssertionError(f"{label}: expected results, got empty list")
    for row in results:
        if not fn(row):
            raise AssertionError(f"{label}: failed for {row.get('name')} — {row}")


def main() -> None:
    print("=== Phase 1.1 Step 4: ranking hard filters ===\n")

    from app.constraint_parser import parse_constraints
    from app.ranking import describe_active_filters, load_suburbs, rank_suburbs

    suburbs = load_suburbs()
    lynn = next(s for s in suburbs if s["name"] == "Lynn")
    newton = next(s for s in suburbs if s["name"] == "Newton")

    print("1. Middlesex county + max 30 min commute")
    mid = parse_constraints("in Middlesex county, 30 mins away from Boston")
    mid_results = rank_suburbs(mid, top_n=5)
    _assert_all(
        mid_results,
        "middlesex+commute",
        lambda r: (r.get("data") or {}).get("county") == "Middlesex"
        and (r.get("data") or {}).get("drive_minutes_to_boston", 999) <= 30,
    )
    print(f"  PASS: top={mid_results[0]['name']}, n={len(mid_results)}")

    print("\n2. Coastal hard filter")
    coastal = parse_constraints("coastal town with good schools")
    coastal_results = rank_suburbs(coastal, top_n=5)
    _assert_all(
        coastal_results,
        "coastal",
        lambda r: (r.get("data") or {}).get("is_coastal") is True,
    )
    if any(r["name"] == "Reading" for r in coastal_results):
        print("  FAIL: Reading should not appear in coastal results")
        sys.exit(1)
    print(f"  PASS: all coastal — sample {coastal_results[0]['name']}")

    print("\n3. Min commute (over 45 min)")
    long_commute = parse_constraints("towns over 45 minutes from Boston")
    long_results = rank_suburbs(long_commute, top_n=5)
    _assert_all(
        long_results,
        "min_commute",
        lambda r: (r.get("data") or {}).get("drive_minutes_to_boston", 0) >= 45,
    )
    print(f"  PASS: min commute filter — top {long_results[0]['name']} ({long_results[0]['data']['drive_minutes_to_boston']} min)")

    print("\n4. Safer than Lynn and cheaper than Newton")
    rel = parse_constraints("safer than Lynn but cheaper than Newton")
    rel_results = rank_suburbs(rel, top_n=5)
    _assert_all(
        rel_results,
        "relative",
        lambda r: (r.get("data") or {}).get("safety_score", 0) > (lynn.get("safety_score") or 0)
        and (r.get("data") or {}).get("latest_home_price", 10**12)
        < (newton.get("latest_home_price") or 10**12),
    )
    print(f"  PASS: relative filters — top {rel_results[0]['name']}")

    print("\n5. High-crime ranking mode")
    crime = parse_constraints("high crime towns near Boston")
    crime_results = rank_suburbs(crime, top_n=5)
    if not crime_results:
        print("  FAIL: expected high-crime results")
        sys.exit(1)
    top_crime = crime_results[0]["data"].get("crime_rate_per_1000")
    if top_crime is None:
        print("  FAIL: top high-crime result missing crime rate")
        sys.exit(1)
    print(f"  PASS: high-crime mode top {crime_results[0]['name']} (crime={top_crime})")

    print("\n6. Impossible filter returns empty (no invented towns)")
    impossible = parse_constraints("coastal town in Middlesex under 10 min commute")
    impossible_results = rank_suburbs(impossible, top_n=5)
    if impossible_results:
        print(f"  FAIL: impossible query should return empty — got {impossible_results}")
        sys.exit(1)
    print("  PASS: empty list for impossible hard-filter combo")

    print("\n7. describe_active_filters helper")
    filters = describe_active_filters(mid)
    if not any("Middlesex" in f for f in filters):
        print(f"  FAIL: expected county in filter labels — {filters}")
        sys.exit(1)
    print(f"  PASS: filter labels — {', '.join(filters)}")

    print("\n8. Day 2 budget query still works")
    budget = parse_constraints("Safe suburb under $900k with good schools")
    budget_results = rank_suburbs(budget, top_n=5)
    _assert_all(
        budget_results,
        "budget",
        lambda r: (r.get("data") or {}).get("latest_home_price", 10**12) <= 900000,
    )
    print(f"  PASS: budget filter — top {budget_results[0]['name']}")

    print("\nStep 4 verification: PASSED")
    print("Next: Step 5 — query_router.py")


if __name__ == "__main__":
    try:
        main()
    except AssertionError as exc:
        print(f"  FAIL: {exc}")
        sys.exit(1)
