#!/usr/bin/env python3
"""Build town_profiles.json from suburbs.json (template text for embeddings)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import SUBURBS_JSON_PATH, TOWN_PROFILES_PATH  # noqa: E402
from app.ranking import load_suburbs  # noqa: E402
from app.town_profiles import build_all_profiles  # noqa: E402


def main() -> None:
    if not SUBURBS_JSON_PATH.exists():
        raise SystemExit(f"Missing {SUBURBS_JSON_PATH}. Run build_suburbs_dataset.py first.")

    suburbs = load_suburbs()
    profiles = build_all_profiles(suburbs)

    TOWN_PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TOWN_PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(profiles, f, indent=2)
        f.write("\n")

    full = sum(1 for p in profiles if p.get("data_quality_tier") == "full")
    partial = len(profiles) - full
    avg_len = sum(len(p["search_text"]) for p in profiles) // max(len(profiles), 1)

    print(f"Wrote {len(profiles)} town profiles → {TOWN_PROFILES_PATH}")
    print(f"  full tier: {full}, partial tier: {partial}")
    print(f"  avg search_text length: {avg_len} chars")
    print(f"  example: {profiles[0]['name']} ({len(profiles[0]['search_text'])} chars)")


if __name__ == "__main__":
    main()
