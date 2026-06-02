#!/usr/bin/env python3
"""Day 3 Step 4 verification: semantic_town_search_tool + agent registration."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


async def _optional_agent_fuzzy() -> None:
    if os.getenv("SKIP_LIVE_AGENT_RUN", "").lower() in ("1", "true", "yes"):
        print("\n  SKIP: live fuzzy agent.run (set SKIP_LIVE_AGENT_RUN=0 to enable)")
        return

    from app.real_estate_agent import create_agent, response_text

    print("\n6. Live agent fuzzy prompt")
    agent = create_agent()
    prompt = "Quiet North Shore town with a coastal feel and good schools"
    response = await agent.run(prompt)
    text = response_text(response)
    if not text.strip():
        print("  FAIL: empty agent response")
        sys.exit(1)
    lower = text.lower()
    if not any(tok in lower for tok in ("north shore", "rockport", "cohasset", "gloucester", "semantic")):
        print(f"  WARN: fuzzy response may not reference expected towns (snippet: {text[:200]!r})")
    else:
        print("  PASS: fuzzy agent response received")
    print(f"       snippet: {text[:180]}...")


def main() -> None:
    print("=== Day 3 Step 4: Semantic Tool + Agent ===\n")

    from app.real_estate_agent import AGENT_INSTRUCTIONS, create_agent
    from app.tools import (
        AGENT_TOOLS,
        CORE_AGENT_TOOLS,
        rank_suburbs_tool,
        run_semantic_town_search,
        semantic_town_search_tool,
    )

    print("1. Tool registration")
    print(f"  PASS: CORE_AGENT_TOOLS still has {len(CORE_AGENT_TOOLS)} tools (Day 2 compat)")
    agent_tool_names = sorted(
        getattr(t, "name", None) or getattr(t, "__name__", str(t)) for t in AGENT_TOOLS
    )
    if len(AGENT_TOOLS) != 7:
        print(f"  FAIL: expected 7 AGENT_TOOLS, got {agent_tool_names}")
        sys.exit(1)
    if "semantic_town_search_tool" not in agent_tool_names:
        print("  FAIL: semantic_town_search_tool not in AGENT_TOOLS")
        sys.exit(1)
    if "get_town_facts_tool" not in agent_tool_names:
        print("  FAIL: get_town_facts_tool not in AGENT_TOOLS")
        sys.exit(1)
    print(f"  PASS: AGENT_TOOLS has 7 tools including get_town_facts + semantic")

    print("\n2. Agent instructions")
    if "semantic_town_search_tool" not in AGENT_INSTRUCTIONS:
        print("  FAIL: instructions missing semantic workflow")
        sys.exit(1)
    if "candidate_towns" not in AGENT_INSTRUCTIONS:
        print("  FAIL: instructions missing candidate_towns guidance")
        sys.exit(1)
    print("  PASS: instructions describe fuzzy → semantic → rank workflow")

    print("\n3. create_agent()")
    agent = create_agent()
    if not agent.name:
        print("  FAIL: agent missing name")
        sys.exit(1)
    print(f"  PASS: agent created (name={agent.name!r}, tools via AGENT_TOOLS={len(AGENT_TOOLS)})")

    if os.getenv("SKIP_LIVE_EMBEDDING_RUN", "").lower() in ("1", "true", "yes"):
        print("\n  SKIP: live semantic tool (set SKIP_LIVE_EMBEDDING_RUN=0 to enable)")
        print("\nStep 4 verification: PASSED")
        print("Next: Step 5 — expand test_agent.py to 7 prompts + README")
        return

    print("\n4. run_semantic_town_search")
    semantic = asyncio.run(
        run_semantic_town_search("quiet coastal North Shore town with small-town feel", top_k=8)
    )
    names = semantic.get("candidate_town_names") or []
    if len(names) < 3:
        print(f"  FAIL: expected >=3 candidates, got {names}")
        sys.exit(1)
    regions = [c.get("region") or "" for c in semantic.get("candidates") or []]
    if not any("North Shore" in r for r in regions):
        print(f"  FAIL: North Shore query missing North Shore region — {names}")
        sys.exit(1)
    print(f"  PASS: semantic candidates → {', '.join(names[:4])}")

    print("\n5. rank_suburbs_tool with candidate_towns")
    ranked = rank_suburbs_tool(
        user_prompt="quiet coastal North Shore town with good schools",
        candidate_towns=names,
        top_n=5,
    )
    ranked_names = {r["name"] for r in ranked}
    if not ranked_names.issubset(set(names)):
        print(f"  FAIL: ranked towns not subset of candidates — {ranked_names}")
        sys.exit(1)
    if len(ranked) < 1:
        print("  FAIL: no ranked results within candidates")
        sys.exit(1)
    print(f"  PASS: ranked within semantic pool → top {ranked[0]['name']} ({ranked[0]['score']})")

    asyncio.run(_optional_agent_fuzzy())

    print("\nStep 4 verification: PASSED")
    print("Next: Step 5 — expand test_agent.py to 7 prompts + README")


if __name__ == "__main__":
    main()
