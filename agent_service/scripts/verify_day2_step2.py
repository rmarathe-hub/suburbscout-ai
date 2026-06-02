#!/usr/bin/env python3
"""Day 2 Step 2 verification: five core tools (no agent yet)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.config import SAVED_SEARCHES_PATH  # noqa: E402
from app.tools import (  # noqa: E402
    CORE_AGENT_TOOLS,
    compare_suburbs_tool,
    explain_results_tool,
    parse_preferences_tool,
    rank_suburbs_tool,
    save_search_tool,
)


def main() -> None:
    print("=== Day 2 Step 2: Core Tools ===\n")

    # 1. Tool registry
    print(f"1. CORE_AGENT_TOOLS count: {len(CORE_AGENT_TOOLS)} (expected 5)")
    names = [getattr(t, "name", str(t)) for t in CORE_AGENT_TOOLS]
    if len(CORE_AGENT_TOOLS) != 5:
        print("  FAIL: expected 5 tools")
        sys.exit(1)
    if any("semantic" in str(n).lower() for n in names):
        print("  FAIL: semantic tool should not be registered")
        sys.exit(1)
    print("  PASS: five core tools, no semantic tool")
    for n in names:
        print(f"       - {n}")

    # 2. parse_preferences_tool
    print("\n2. parse_preferences_tool")
    prompt = "Safe Boston suburb under 900k with good schools"
    prefs = parse_preferences_tool(prompt)
    if prefs.get("budget_max") == 900000 and prefs.get("safety_priority") == "high":
        print("  PASS: parsed budget and safety")
    else:
        print(f"  FAIL: unexpected prefs {prefs}")
        sys.exit(1)

    # 3. rank_suburbs_tool
    print("\n3. rank_suburbs_tool")
    ranked = rank_suburbs_tool(
        user_prompt="Safe suburb under $900k with good schools",
        preferences=prefs,
        top_n=5,
    )
    if len(ranked) != 5:
        print(f"  FAIL: expected 5 results, got {len(ranked)}")
        sys.exit(1)
    if all(r.get("data", {}).get("latest_home_price") is not None for r in ranked):
        print(f"  PASS: top result = {ranked[0]['name']} (score {ranked[0]['score']})")
        print("  PASS: budget query excluded towns without housing")
    else:
        print("  FAIL: budget query included town without housing price")
        sys.exit(1)

    # 4. compare_suburbs_tool
    print("\n4. compare_suburbs_tool")
    cmp_result = compare_suburbs_tool(town_a="Acton", town_b="Framingham")
    if "error" in cmp_result:
        print(f"  FAIL: {cmp_result}")
        sys.exit(1)
    if cmp_result["town_a"]["name"] == "Acton" and cmp_result["town_b"]["name"] == "Framingham":
        print("  PASS: Acton vs Framingham loaded from suburbs.json")
        print(
            f"       Acton price={cmp_result['town_a']['latest_home_price']}, "
            f"Framingham price={cmp_result['town_b']['latest_home_price']}"
        )
    else:
        print(f"  FAIL: {cmp_result}")
        sys.exit(1)

    # 5. explain_results_tool
    print("\n5. explain_results_tool")
    explained = explain_results_tool(
        results=ranked,
        user_prompt="Safe suburb under $900k with good schools",
        preferences=prefs,
    )
    if explained.get("final_recommendation") and explained.get("summary"):
        print("  PASS: explanation generated from tool data only")
    else:
        print(f"  FAIL: {explained}")
        sys.exit(1)

    # 6. save_search_tool
    print("\n6. save_search_tool")
    before = 0
    if SAVED_SEARCHES_PATH.exists():
        before = sum(1 for _ in open(SAVED_SEARCHES_PATH, encoding="utf-8"))
    saved = save_search_tool(prompt=prompt, preferences=prefs, results=ranked)
    after = sum(1 for _ in open(SAVED_SEARCHES_PATH, encoding="utf-8"))
    if saved.get("saved") and after == before + 1:
        print(f"  PASS: appended to {SAVED_SEARCHES_PATH.name} ({before} -> {after} lines)")
    else:
        print(f"  FAIL: save result {saved}, lines {before}->{after}")
        sys.exit(1)

    print("\nStep 2 verification: PASSED")
    print("Next: Step 3 — app/chat_client.py + app/real_estate_agent.py (Foundry agent)")


if __name__ == "__main__":
    main()
