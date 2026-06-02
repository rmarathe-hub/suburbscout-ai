#!/usr/bin/env python3
"""Phase 1 agent smoke tests — seven prompts (3 structured + 4 fuzzy/semantic)."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

from app.chat_client import get_active_client_kind
from app.config import SAVED_SEARCHES_PATH
from app.real_estate_agent import create_agent, run_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)

# Day 2 structured / compare prompts (unchanged)
DAY2_TEST_PROMPTS: list[tuple[str, str]] = [
    (
        "recommendation",
        "Safe suburb under $900k with good schools",
    ),
    (
        "compare",
        "Compare Acton and Framingham",
    ),
    (
        "recommendation",
        "Affordable suburb with strong schools and decent commute",
    ),
]

# Day 3 fuzzy / semantic prompts — agent should use semantic_town_search_tool first
FUZZY_TEST_PROMPTS: list[tuple[str, str]] = [
    (
        "fuzzy_vibe",
        "Quiet town with a coastal feel and good schools",
    ),
    (
        "fuzzy_like_cheaper",
        "Something like Lexington but cheaper with good schools",
    ),
    (
        "fuzzy_region",
        "North Shore family-friendly suburb with strong schools",
    ),
    (
        "fuzzy_mixed",
        "Walkable downtown feel under $800k with decent commute",
    ),
]

TEST_PROMPTS: list[tuple[str, str]] = DAY2_TEST_PROMPTS + FUZZY_TEST_PROMPTS

FUZZY_LABELS = frozenset(label for label, _ in FUZZY_TEST_PROMPTS)


def _count_saved_searches() -> int:
    if not SAVED_SEARCHES_PATH.exists():
        return 0
    with open(SAVED_SEARCHES_PATH, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def _print_result(label: str, prompt: str, result: dict[str, Any]) -> None:
    print(f"\n{'=' * 72}")
    print(f"Prompt [{label}]: {prompt}")
    print(f"Client: {result.get('client_kind') or get_active_client_kind()}")
    print("-" * 72)

    parsed = result.get("parsed")
    if parsed:
        print(json.dumps(parsed, indent=2))
    else:
        print(result.get("text", ""))

    if parsed:
        semantic = parsed.get("semantic_candidates")
        if semantic and isinstance(semantic, dict):
            names = semantic.get("candidate_town_names") or []
            if names:
                print(f"\nSemantic candidates (up to 5): {', '.join(names[:5])}")

        top = parsed.get("top_matches") or []
        if top and isinstance(top[0], dict):
            names = [m.get("name") for m in top[:3] if isinstance(m, dict)]
            print(f"\nTop matches (up to 3): {', '.join(n for n in names if n)}")
        comp = parsed.get("comparison")
        if comp and isinstance(comp, dict):
            a = (comp.get("town_a") or {}).get("name")
            b = (comp.get("town_b") or {}).get("name")
            if a and b:
                print(f"Compared: {a} vs {b}")


async def run_all_tests(*, prompts: list[tuple[str, str]] | None = None) -> list[dict[str, Any]]:
    """Run test prompts; reuse one agent instance."""
    active_prompts = prompts or TEST_PROMPTS
    agent = create_agent()
    client_kind = get_active_client_kind()
    print("=== SuburbScout Phase 1 Agent Tests ===")
    print(f"Agent: {agent.name}")
    print(f"Chat client: {client_kind}")
    print(f"Prompts: {len(active_prompts)} ({len(DAY2_TEST_PROMPTS)} structured + {len(FUZZY_TEST_PROMPTS)} fuzzy)")

    before_saved = _count_saved_searches()
    print(f"saved_searches.jsonl lines before: {before_saved}")

    results: list[dict[str, Any]] = []
    for label, prompt in active_prompts:
        result = await run_agent(prompt, agent=agent)
        result["label"] = label
        result["prompt"] = prompt
        results.append(result)
        _print_result(label, prompt, result)

    after_saved = _count_saved_searches()
    added = after_saved - before_saved
    print(f"\n{'=' * 72}")
    print(f"saved_searches.jsonl: {before_saved} -> {after_saved} (+{added} lines)")
    print(f"Expected at least +{len(active_prompts)} new lines (one save per prompt).")

    return results


def main() -> None:
    try:
        asyncio.run(run_all_tests())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(f"\nAgent test failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
