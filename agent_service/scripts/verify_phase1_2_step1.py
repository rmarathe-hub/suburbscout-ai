#!/usr/bin/env python3
"""Phase 1.2 Step 1 verification: strict response validator."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


def _assert_invalid(label: str, result, *, contains: str) -> None:
    if result.valid:
        raise AssertionError(f"{label}: expected invalid, got valid")
    blob = " ".join(result.errors).lower()
    if contains.lower() not in blob:
        raise AssertionError(f"{label}: expected {contains!r} in {result.errors}")


def _assert_valid(label: str, result) -> None:
    if not result.valid:
        raise AssertionError(f"{label}: expected valid, errors={result.errors}")


async def main() -> None:
    print("=== Phase 1.2 Step 1: strict validator ===\n")

    from app.intent_rules import infer_strict_intent
    from app.orchestrator import handle_query
    from app.query_router import classify_query
    from app.response_validator import validate_agent_response, validate_strict_intent_alignment

    print("1. Strict intent inference")
    cases = [
        ("What is the commute from Gardner to Boston?", "lookup_single_town", "Gardner"),
        ("Which is safer, Burlington or Framingham?", "compare_towns", None),
        ("Is Reading coastal?", "lookup_single_town", "Reading"),
        ("Recommend towns outside your 200-town list", "refuse_out_of_scope", None),
    ]
    for prompt, intent, town in cases:
        strict = infer_strict_intent(prompt)
        if strict.intent != intent:
            raise AssertionError(f"{prompt!r} -> {strict.intent}, expected {intent}")
        if town and strict.lookup_town and strict.lookup_town != town:
            # allow canonical variants
            if town.lower() not in strict.lookup_town.lower():
                raise AssertionError(f"{prompt!r} lookup_town={strict.lookup_town}, expected {town}")
        print(f"  PASS: {intent} — {prompt[:50]}")

    print("\n2. Bad legacy-style response must fail strict validation")
    bad = {
        "query": "What is the commute from Gardner to Boston?",
        "preferences": None,
        "top_matches": [{"name": "Sharon", "score": 8.0, "data": {}}],
        "comparison": None,
        "final_recommendation": "I recommend Sharon based on your preferences.",
        "orchestrated": True,
    }
    route = classify_query(bad["query"])
    check = validate_strict_intent_alignment(bad["query"], bad, route=route)
    _assert_invalid("gardner sharon", check, contains="lookup")
    print("  PASS: Gardner→Sharon recommendation fails")

    print("\n3. Budget parse sanity")
    from app.constraint_parser import parse_constraints
    from app.response_validator import validate_budget_parse

    prefs = parse_constraints("Find me towns under $1 million with elite schools")
    if prefs.budget_max != 1_000_000:
        raise AssertionError(f"expected 1M budget, got {prefs.budget_max}")
    bad_budget_resp = {"preferences": prefs.model_dump()}
    _assert_invalid(
        "million parse",
        validate_budget_parse("under $1 million", {"budget_max": 1000}),
        contains="million",
    )
    _assert_valid("million ok", validate_budget_parse("under $1 million", prefs.model_dump()))
    print("  PASS: $1 million parsing + validation")

    print("\n4. Live orchestrator spot checks (routing + validation)")
    live_cases = [
        ("What is the commute from Gardner to Boston?", True),
        ("Which is safer, Burlington or Framingham?", True),
        ("Is Reading coastal?", True),
        ("Recommend towns outside your 200-town list if they are better.", True),
        ("Find me towns under $1 million with elite schools.", True),
        ("Find me a high-crime suburb that is affordable and close to Boston.", True),
    ]
    for prompt, should_pass in live_cases:
        payload = await handle_query(prompt, save_searches=False)
        resp = payload["response"]
        valid = (resp.get("validation") or {}).get("valid")
        if should_pass and not valid:
            raise AssertionError(f"expected pass for {prompt!r}: {resp.get('validation')}")
        print(f"  PASS: {prompt[:55]}… valid={valid} route={payload['route']['intent']}")

    print("\nStep 1 verification: PASSED")
    print("Next: Step 2 — rerun 150-prompt quality check for real score")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print(f"  FAIL: {exc}")
        sys.exit(1)
