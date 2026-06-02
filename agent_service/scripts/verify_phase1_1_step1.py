#!/usr/bin/env python3
"""Phase 1.1 Step 1 verification: coastal + region_key geo enrichment."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


def main() -> None:
    print("=== Phase 1.1 Step 1: Geo Enrichment ===\n")

    from app import config
    from app.geo_enrichment import (
        NON_COASTAL_SPOT_CHECKS,
        REGION_KEY_MAP,
        coastal_enrichment_for_town,
        load_coastal_town_keys,
        region_key_for_label,
    )

    print("1. Source files")
    if not config.COASTAL_TOWNS_PATH.exists():
        print(f"  FAIL: missing {config.COASTAL_TOWNS_PATH}")
        sys.exit(1)
    print(f"  PASS: coastal_towns.csv exists")

    keys = load_coastal_town_keys()
    if len(keys) < 25:
        print(f"  FAIL: expected >=25 curated coastal towns, got {len(keys)}")
        sys.exit(1)
    print(f"  PASS: {len(keys)} coastal towns in curated list")

    print("\n2. region_key mapping")
    if len(REGION_KEY_MAP) < 7:
        print(f"  FAIL: expected 7 region mappings, got {len(REGION_KEY_MAP)}")
        sys.exit(1)
    sample_key = region_key_for_label("North Shore / northeast suburbs")
    if sample_key != "north_shore":
        print(f"  FAIL: north_shore mapping got {sample_key!r}")
        sys.exit(1)
    print("  PASS: region_key slugs defined for all product regions")

    print("\n3. suburbs.json fields")
    if not config.SUBURBS_JSON_PATH.exists():
        print(f"  FAIL: missing {config.SUBURBS_JSON_PATH} — run build_suburbs_dataset.py")
        sys.exit(1)

    with open(config.SUBURBS_JSON_PATH, encoding="utf-8") as f:
        suburbs = json.load(f)

    if len(suburbs) != 200:
        print(f"  FAIL: expected 200 towns, got {len(suburbs)}")
        sys.exit(1)

    required_fields = ("is_coastal", "region_key")
    for field in required_fields:
        missing = [s["name"] for s in suburbs if field not in s]
        if missing:
            print(f"  FAIL: {len(missing)} towns missing {field}")
            sys.exit(1)
    print("  PASS: all 200 towns have is_coastal + region_key")

    coastal = [s for s in suburbs if s.get("is_coastal")]
    if len(coastal) < 25:
        print(f"  FAIL: expected >=25 is_coastal=true in suburbs.json, got {len(coastal)}")
        sys.exit(1)
    print(f"  PASS: {len(coastal)} towns marked is_coastal=true")

    print("\n4. Spot checks")
    must_be_coastal = ("Rockport", "Gloucester", "Cohasset", "Newburyport", "Hull")
    for name in must_be_coastal:
        row = next(s for s in suburbs if s["name"] == name)
        if not row.get("is_coastal"):
            print(f"  FAIL: {name} should be coastal")
            sys.exit(1)
    print(f"  PASS: known coastal towns tagged ({', '.join(must_be_coastal)})")

    for name in NON_COASTAL_SPOT_CHECKS:
        row = next((s for s in suburbs if s["name"] == name), None)
        if row is None:
            print(f"  FAIL: spot-check town missing from dataset: {name}")
            sys.exit(1)
        if row.get("is_coastal"):
            print(f"  FAIL: inland town incorrectly coastal: {name}")
            sys.exit(1)
    print(f"  PASS: inland spot-checks not coastal ({', '.join(NON_COASTAL_SPOT_CHECKS[:3])}...)")

    if "coastal" not in next(s for s in suburbs if s["name"] == "Rockport").get("tags", []):
        print("  FAIL: Rockport tags should include 'coastal'")
        sys.exit(1)
    print("  PASS: coastal tag added to town tags")

    enrich = coastal_enrichment_for_town("Reading")
    if enrich.get("is_coastal"):
        print("  FAIL: coastal_enrichment_for_town(Reading) should be false")
        sys.exit(1)
    print("  PASS: geo_enrichment helper returns expected flags")

    print("\nStep 1 verification: PASSED")
    print("Next: Step 2 — get_town_facts_tool")


if __name__ == "__main__":
    main()
