#!/usr/bin/env python3
"""Day 3 Step 2 verification: town_profiles.json from suburbs.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


def main() -> None:
    print("=== Day 3 Step 2: Town Profiles ===\n")

    from app.config import SUBURBS_JSON_PATH, TOWN_PROFILES_PATH
    from app.town_profiles import build_profile_record
    from app.ranking import load_suburbs

    # 1. Build profiles
    print("1. build_town_profiles.py")
    import subprocess

    result = subprocess.run(
        [sys.executable, str(SERVICE_ROOT / "scripts" / "build_town_profiles.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"  FAIL: build script exited {result.returncode}")
        print(result.stderr or result.stdout)
        sys.exit(1)
    print("  PASS: build_town_profiles.py completed")
    if result.stdout.strip():
        for line in result.stdout.strip().splitlines():
            print(f"       {line}")

    # 2. File exists
    print("\n2. town_profiles.json")
    if not TOWN_PROFILES_PATH.exists():
        print(f"  FAIL: missing {TOWN_PROFILES_PATH}")
        sys.exit(1)

    with open(TOWN_PROFILES_PATH, encoding="utf-8") as f:
        profiles = json.load(f)

    with open(SUBURBS_JSON_PATH, encoding="utf-8") as f:
        suburbs = json.load(f)

    if len(profiles) != len(suburbs):
        print(f"  FAIL: expected {len(suburbs)} profiles, got {len(profiles)}")
        sys.exit(1)
    if len(profiles) != 200:
        print(f"  FAIL: expected 200 profiles, got {len(profiles)}")
        sys.exit(1)
    print(f"  PASS: {len(profiles)} profiles (matches suburbs.json)")

    # 3. Required fields
    print("\n3. Profile structure")
    required = ("name", "search_text", "keywords", "tags", "data_quality_tier", "snapshot")
    for p in profiles[:5]:
        for key in required:
            if key not in p:
                print(f"  FAIL: {p.get('name')} missing key {key!r}")
                sys.exit(1)
    print("  PASS: required keys present (name, search_text, keywords, tags, snapshot)")

    empty = [p["name"] for p in profiles if not (p.get("search_text") or "").strip()]
    if empty:
        print(f"  FAIL: empty search_text for {empty[:3]}")
        sys.exit(1)
    print("  PASS: all profiles have non-empty search_text")

    # 4. Grounded in suburbs.json (no invented town names)
    suburb_names = {s["name"] for s in suburbs}
    profile_names = {p["name"] for p in profiles}
    if profile_names != suburb_names:
        print("  FAIL: profile town names do not match suburbs.json")
        sys.exit(1)
    print("  PASS: profile names match suburbs.json exactly")

    # 5. Sample content checks
    print("\n4. Content sanity")
    sharon = next((p for p in profiles if p["name"] == "Sharon"), None)
    if not sharon or "Sharon" not in sharon["search_text"]:
        print("  FAIL: Sharon profile missing or invalid")
        sys.exit(1)
    if "strong schools" not in sharon["search_text"].lower() and "school" not in sharon["search_text"].lower():
        print("  FAIL: Sharon profile missing school context")
        sys.exit(1)
    print("  PASS: Sharon profile mentions schools and town name")

    worcester = next((p for p in profiles if p["name"] == "Worcester"), None)
    suburb_w = next((s for s in suburbs if s["name"] == "Worcester"), None)
    if worcester and suburb_w and suburb_w.get("latest_home_price") is None:
        if "unavailable" not in worcester["search_text"].lower():
            print("  FAIL: Worcester should note unavailable housing")
            sys.exit(1)
        print("  PASS: Worcester notes unavailable housing (no invented price)")

    # 6. Deterministic rebuild
    print("\n5. Deterministic template build")
    rebuilt = build_profile_record(next(s for s in suburbs if s["name"] == "Acton"))
    if rebuilt["search_text"] != next(p for p in profiles if p["name"] == "Acton")["search_text"]:
        print("  FAIL: Acton profile not deterministic vs build_profile_record")
        sys.exit(1)
    print("  PASS: build_profile_record matches saved Acton profile")

    print("\nStep 2 verification: PASSED")
    print("Next: Step 3 — embed profiles + build_vector_index.py + vector_store.py")


if __name__ == "__main__":
    main()
