#!/usr/bin/env python3
"""Phase 1.1 Step 2 verification: get_town_facts_tool."""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


def main() -> None:
    print("=== Phase 1.1 Step 2: get_town_facts_tool ===\n")

    from app.tools import (
        AGENT_TOOLS,
        CORE_AGENT_TOOLS,
        get_town_facts,
        get_town_facts_tool,
    )

    print("1. Tool registration")
    agent_names = sorted(getattr(t, "name", str(t)) for t in AGENT_TOOLS)
    if "get_town_facts_tool" not in agent_names:
        print(f"  FAIL: get_town_facts_tool not in AGENT_TOOLS: {agent_names}")
        sys.exit(1)
    if len(CORE_AGENT_TOOLS) != 5:
        print(f"  FAIL: CORE_AGENT_TOOLS should stay at 5 for Day 2 compat, got {len(CORE_AGENT_TOOLS)}")
        sys.exit(1)
    print("  PASS: get_town_facts_tool registered; CORE_AGENT_TOOLS still 5")

    print("\n2. Gardner lookup (in dataset)")
    gardner = get_town_facts("Gardner")
    if not gardner.get("found"):
        print(f"  FAIL: Gardner should be found — {gardner}")
        sys.exit(1)
    town = gardner.get("town") or {}
    if town.get("name") != "Gardner":
        print(f"  FAIL: expected Gardner, got {town.get('name')}")
        sys.exit(1)
    if town.get("drive_minutes_to_boston") is None:
        print("  FAIL: Gardner should include commute minutes")
        sys.exit(1)
    print(f"  PASS: Gardner found — {town.get('drive_minutes_to_boston')} min to Boston")

    print("\n3. Charlton lookup (not in dataset)")
    charlton = get_town_facts("Charlton")
    if charlton.get("found"):
        print("  FAIL: Charlton should not be found")
        sys.exit(1)
    if charlton.get("town") is not None:
        print("  FAIL: Charlton town payload should be null")
        sys.exit(1)
    if "not in" not in (charlton.get("message") or "").lower():
        print(f"  FAIL: expected not-in-dataset message — {charlton.get('message')}")
        sys.exit(1)
    print("  PASS: Charlton not found with explicit message")

    print("\n4. Typo close match (Actn -> Acton)")
    typo = get_town_facts("Actn")
    if typo.get("found"):
        print("  FAIL: Actn should not exact-match")
        sys.exit(1)
    if "Acton" not in (typo.get("close_matches") or []):
        print(f"  FAIL: expected Acton in close_matches — {typo.get('close_matches')}")
        sys.exit(1)
    print(f"  PASS: close_matches suggest Acton — {typo.get('close_matches')[:3]}")

    print("\n5. Alias lookup (Manchester -> Manchester-by-the-Sea)")
    mbt = get_town_facts("Manchester")
    if not mbt.get("found") or (mbt.get("town") or {}).get("name") != "Manchester-by-the-Sea":
        print(f"  FAIL: Manchester alias lookup — {mbt}")
        sys.exit(1)
    print("  PASS: Manchester alias resolves to Manchester-by-the-Sea")

    print("\n6. Coastal + region_key on town record")
    cohasset = get_town_facts("Cohasset")
    record = cohasset.get("town") or {}
    if not record.get("is_coastal"):
        print("  FAIL: Cohasset should have is_coastal=true")
        sys.exit(1)
    if record.get("region_key") != "south_shore":
        print(f"  FAIL: Cohasset region_key — {record.get('region_key')}")
        sys.exit(1)
    reading = get_town_facts("Reading")
    if (reading.get("town") or {}).get("is_coastal"):
        print("  FAIL: Reading should not be coastal")
        sys.exit(1)
    print("  PASS: is_coastal + region_key exposed on town facts")

    print("\n7. @tool wrapper")
    wrapped = get_town_facts_tool("Shrewsbury")
    if not wrapped.get("found") or (wrapped.get("town") or {}).get("name") != "Shrewsbury":
        print(f"  FAIL: tool wrapper — {wrapped}")
        sys.exit(1)
    print("  PASS: get_town_facts_tool callable")

    print("\nStep 2 verification: PASSED")
    print("Next: Step 3 — constraint_parser.py")


if __name__ == "__main__":
    main()
