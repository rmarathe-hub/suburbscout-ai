#!/usr/bin/env python3
"""Validate suburbs.json and print a QA report."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import COASTAL_TOWNS_PATH, CORE_FIELDS, SUBURBS_JSON_PATH  # noqa: E402
from app.geo_enrichment import NON_COASTAL_SPOT_CHECKS, REGION_KEY_MAP  # noqa: E402

SCORE_FIELDS = (
    "economic_score",
    "safety_score",
    "commute_score",
    "school_score",
    "affordability_score",
    "family_score",
)

MAX_MISSING_FOR_WARN = 3


def main() -> None:
    if not SUBURBS_JSON_PATH.exists():
        raise SystemExit(f"Missing {SUBURBS_JSON_PATH}. Run build_suburbs_dataset.py first.")

    with open(SUBURBS_JSON_PATH, encoding="utf-8") as f:
        suburbs = json.load(f)

    names = [s["name"] for s in suburbs]
    dupes = [n for n, c in Counter(names).items() if c > 1]

    print("=== SuburbScout Dataset Validation ===\n")
    print(f"Towns: {len(suburbs)}")
    print(f"Duplicate towns: {dupes if dupes else 'none'}")

    tiers = Counter(s.get("data_quality_tier", "unknown") for s in suburbs)
    print(f"Data quality tiers: {dict(tiers)}")

    # Missing field counts
    missing_counter: Counter = Counter()
    for s in suburbs:
        for field in s.get("missing_fields") or []:
            missing_counter[field] += 1
    print("\nMissing field counts (towns missing each field):")
    for field, count in missing_counter.most_common():
        print(f"  {field}: {count}")

    # Invalid scores
    invalid_scores = []
    for s in suburbs:
        for field in SCORE_FIELDS:
            val = s.get(field)
            if val is not None and (val < 0 or val > 10):
                invalid_scores.append((s["name"], field, val))
    print(f"\nInvalid scores outside 0-10: {len(invalid_scores)}")
    for item in invalid_scores[:10]:
        print(f"  {item}")

    # Towns missing too many fields
    thin = []
    for s in suburbs:
        n_missing = len(s.get("missing_fields") or [])
        if n_missing >= MAX_MISSING_FOR_WARN:
            thin.append((s["name"], n_missing, s.get("data_quality_tier")))
    print(f"\nTowns with >={MAX_MISSING_FOR_WARN} missing fields: {len(thin)}")
    for name, n, tier in thin[:15]:
        print(f"  {name}: {n} missing ({tier})")

    # Core field coverage
    print("\nCore field coverage:")
    for field in CORE_FIELDS:
        have = sum(1 for s in suburbs if s.get(field) is not None)
        print(f"  {field}: {have}/{len(suburbs)}")

    # Phase 1.1 geo enrichment
    coastal = [s for s in suburbs if s.get("is_coastal")]
    missing_coastal_field = [s["name"] for s in suburbs if "is_coastal" not in s]
    missing_region_key = [s["name"] for s in suburbs if not s.get("region_key")]
    print("\nGeo enrichment (Phase 1.1):")
    print(f"  coastal_towns.csv present: {COASTAL_TOWNS_PATH.exists()}")
    print(f"  is_coastal=true: {len(coastal)}")
    print(f"  missing is_coastal field: {len(missing_coastal_field)}")
    print(f"  missing region_key: {len(missing_region_key)}")
    if coastal:
        sample = ", ".join(s["name"] for s in coastal[:8])
        print(f"  coastal sample: {sample}...")
    spot_failures = [name for name in NON_COASTAL_SPOT_CHECKS if any(s["name"] == name and s.get("is_coastal") for s in suburbs)]
    if spot_failures:
        print(f"  WARN: inland towns incorrectly tagged coastal: {spot_failures}")
    else:
        print(f"  spot-check inland towns not coastal: OK ({', '.join(NON_COASTAL_SPOT_CHECKS[:3])}...)")
    unmapped_regions = sorted({s.get("region") for s in suburbs if s.get("region") and s.get("region") not in REGION_KEY_MAP})
    if unmapped_regions:
        print(f"  WARN: regions without region_key mapping: {unmapped_regions}")

    print("\nSample rows (first 3):")
    for s in suburbs[:3]:
        print(
            f"  {s['name']}: tier={s.get('data_quality_tier')}, "
            f"price={s.get('latest_home_price')}, safety={s.get('safety_score')}, "
            f"school={s.get('school_score')}, commute={s.get('drive_minutes_to_boston')} min"
        )


if __name__ == "__main__":
    main()
