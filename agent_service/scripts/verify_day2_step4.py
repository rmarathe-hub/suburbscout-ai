#!/usr/bin/env python3
"""Day 2 Step 4 verification: run three agent prompts and check outcomes."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


def _count_saved() -> int:
    from app.config import SAVED_SEARCHES_PATH

    if not SAVED_SEARCHES_PATH.exists():
        return 0
    with open(SAVED_SEARCHES_PATH, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


async def _run_checks() -> None:
    from app.chat_client import get_active_client_kind
    from app.real_estate_agent import create_agent, run_agent
    from app.test_agent import DAY2_TEST_PROMPTS

    print("=== Day 2 Step 4: Agent Test Prompts ===\n")

    print("1. test_agent module")
    print(f"  PASS: {len(DAY2_TEST_PROMPTS)} prompts defined")

    agent = create_agent()
    kind = get_active_client_kind()
    if kind not in ("foundry", "openai_fallback"):
        print(f"  FAIL: unknown client kind {kind!r}")
        sys.exit(1)
    print(f"  PASS: agent created (client={kind}, name={agent.name!r})")

    before = _count_saved()
    print(f"\n2. Run prompts (saved_searches before={before})")

    results = []
    for i, (label, prompt) in enumerate(DAY2_TEST_PROMPTS, start=1):
        print(f"\n  [{i}/3] {label}: {prompt[:60]}...")
        result = await run_agent(prompt, agent=agent)
        text = (result.get("text") or "").strip()
        if not text:
            print("  FAIL: empty agent response")
            sys.exit(1)
        parsed = result.get("parsed")
        if label == "compare":
            blob = text.lower()
            if parsed and parsed.get("comparison"):
                print("  PASS: compare response includes comparison object")
            elif "acton" in blob and "framingham" in blob:
                print("  PASS: compare response mentions Acton and Framingham")
            else:
                print("  FAIL: compare prompt missing Acton/Framingham in response")
                sys.exit(1)
        else:
            if parsed and parsed.get("top_matches"):
                top = parsed["top_matches"]
                print(f"  PASS: recommendation has top_matches (n={len(top)})")
            elif any(tok in text.lower() for tok in ("score", "recommend", "sharon", "suburb")):
                print("  PASS: recommendation response received (unparsed JSON)")
            else:
                print("  FAIL: recommendation missing top_matches / recommendation text")
                sys.exit(1)
        results.append(result)

    after = _count_saved()
    added = after - before
    print(f"\n3. saved_searches.jsonl")
    if added < 3:
        print(f"  FAIL: expected +3 lines, got +{added} ({before} -> {after})")
        sys.exit(1)
    print(f"  PASS: +{added} lines appended ({before} -> {after})")

    print("\nStep 4 verification: PASSED")
    print("Next: Step 5 — README updates for Day 2")


def main() -> None:
    asyncio.run(_run_checks())


if __name__ == "__main__":
    main()
