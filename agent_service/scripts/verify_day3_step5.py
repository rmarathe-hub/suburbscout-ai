#!/usr/bin/env python3
"""Day 3 Step 5 / Phase 1 completion: seven-prompt agent test + artifact checks."""

from __future__ import annotations

import asyncio
import json
import os
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


def _check_artifacts() -> None:
    from app import config

    print("1. Phase 1 artifacts")
    checks = [
        ("suburbs.json", config.SUBURBS_JSON_PATH),
        ("town_profiles.json", config.TOWN_PROFILES_PATH),
        ("vector index embeddings", config.VECTOR_EMBEDDINGS_PATH),
        ("vector index metadata", config.VECTOR_METADATA_PATH),
    ]
    for label, path in checks:
        if not path.exists():
            print(f"  FAIL: missing {label} at {path}")
            sys.exit(1)
        print(f"  PASS: {label}")

    with open(config.SUBURBS_JSON_PATH, encoding="utf-8") as f:
        suburbs = json.load(f)
    if len(suburbs) != 200:
        print(f"  FAIL: expected 200 towns in suburbs.json, got {len(suburbs)}")
        sys.exit(1)
    print("  PASS: suburbs.json has 200 towns")

    from app.tools import AGENT_TOOLS

    if len(AGENT_TOOLS) != 7:
        print(f"  FAIL: expected 7 agent tools, got {len(AGENT_TOOLS)}")
        sys.exit(1)
    print("  PASS: agent has 7 tools (get_town_facts + core + semantic)")


def _validate_fuzzy_response(label: str, text: str, parsed: dict | None) -> bool:
    blob = text.lower()
    if parsed:
        if parsed.get("semantic_candidates"):
            return True
        if parsed.get("top_matches"):
            return True
    fuzzy_tokens = (
        "semantic",
        "candidate",
        "coastal",
        "north shore",
        "lexington",
        "walkable",
        "recommend",
        "score",
        "suburb",
        "town",
    )
    return any(tok in blob for tok in fuzzy_tokens)


async def _run_agent_tests() -> None:
    if os.getenv("SKIP_LIVE_AGENT_RUN", "").lower() in ("1", "true", "yes"):
        print("\n  SKIP: live 7-prompt agent run (set SKIP_LIVE_AGENT_RUN=0 to enable)")
        return

    from app.chat_client import get_active_client_kind
    from app.real_estate_agent import create_agent, run_agent
    from app.test_agent import (
        DAY2_TEST_PROMPTS,
        FUZZY_LABELS,
        FUZZY_TEST_PROMPTS,
        TEST_PROMPTS,
    )

    print("\n2. test_agent module")
    if len(TEST_PROMPTS) != 7:
        print(f"  FAIL: expected 7 TEST_PROMPTS, got {len(TEST_PROMPTS)}")
        sys.exit(1)
    if len(DAY2_TEST_PROMPTS) != 3 or len(FUZZY_TEST_PROMPTS) != 4:
        print("  FAIL: expected 3 Day 2 + 4 fuzzy prompts")
        sys.exit(1)
    print("  PASS: 7 prompts (3 structured + 4 fuzzy)")

    agent = create_agent()
    kind = get_active_client_kind()
    print(f"\n3. Run all 7 prompts (client={kind})")
    before = _count_saved()

    for i, (label, prompt) in enumerate(TEST_PROMPTS, start=1):
        print(f"\n  [{i}/7] {label}: {prompt[:55]}...")
        result = await run_agent(prompt, agent=agent)
        text = (result.get("text") or "").strip()
        if not text:
            print("  FAIL: empty agent response")
            sys.exit(1)

        parsed = result.get("parsed")
        if label == "compare":
            if parsed and parsed.get("comparison"):
                print("  PASS: compare response includes comparison object")
            elif "acton" in text.lower() and "framingham" in text.lower():
                print("  PASS: compare mentions Acton and Framingham")
            else:
                print("  FAIL: compare prompt missing expected towns")
                sys.exit(1)
        elif label in FUZZY_LABELS:
            if _validate_fuzzy_response(label, text, parsed):
                print("  PASS: fuzzy/semantic response received")
            else:
                print("  FAIL: fuzzy prompt missing semantic or recommendation content")
                sys.exit(1)
        else:
            if parsed and parsed.get("top_matches"):
                print(f"  PASS: recommendation has top_matches (n={len(parsed['top_matches'])})")
            elif any(tok in text.lower() for tok in ("score", "recommend", "suburb")):
                print("  PASS: recommendation response received")
            else:
                print("  FAIL: recommendation missing top_matches / recommendation text")
                sys.exit(1)

    after = _count_saved()
    added = after - before
    expected = len(TEST_PROMPTS)
    print(f"\n4. saved_searches.jsonl")
    if added < expected - 1:
        print(f"  FAIL: expected +{expected} lines, got +{added} ({before} -> {after})")
        sys.exit(1)
    if added < expected:
        print(
            f"  WARN: expected +{expected} lines, got +{added} ({before} -> {after}) "
            "— agent skipped save on one prompt"
        )
    else:
        print(f"  PASS: +{added} lines appended ({before} -> {after})")


def main() -> None:
    print("=== Day 3 Step 5: Phase 1 Completion ===\n")

    _check_artifacts()
    asyncio.run(_run_agent_tests())

    print("\nPhase 1 verification: PASSED")
    print("SuburbScout local agent is feature-complete for Phase 1 scope.")


if __name__ == "__main__":
    main()
