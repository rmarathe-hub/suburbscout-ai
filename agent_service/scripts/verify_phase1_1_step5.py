#!/usr/bin/env python3
"""Phase 1.1 Step 5 verification: query_router.py."""

from __future__ import annotations

import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


def _expect(label: str, query: str, **checks) -> None:
    from app.query_router import classify_query

    route = classify_query(query)
    data = route.model_dump()
    for key, expected in checks.items():
        actual = data.get(key)
        if actual != expected:
            raise AssertionError(
                f"{label}: expected {key}={expected!r}, got {actual!r} (route={data})"
            )


def main() -> None:
    print("=== Phase 1.1 Step 5: query_router ===\n")

    cases: list[tuple[str, str, dict]] = [
        (
            "lookup commute",
            "commute for Gardner",
            {"intent": "lookup_single_town", "lookup_town": "Gardner"},
        ),
        (
            "dataset membership",
            "is Gardner in your dataset",
            {"intent": "lookup_single_town", "lookup_town": "Gardner"},
        ),
        (
            "crime fact lookup",
            "crime rate in Shrewsbury",
            {"intent": "lookup_single_town", "lookup_town": "Shrewsbury"},
        ),
        (
            "compare and",
            "Compare Acton and Framingham",
            {
                "intent": "compare_towns",
                "compare_town_a": "Acton",
                "compare_town_b": "Framingham",
            },
        ),
        (
            "compare vs",
            "Walpole vs Sharon",
            {"intent": "compare_towns", "compare_town_a": "Walpole", "compare_town_b": "Sharon"},
        ),
        (
            "structured budget",
            "Safe suburb under $900k with good schools",
            {"intent": "recommend_structured", "use_semantic": False},
        ),
        (
            "structured county commute",
            "in Middlesex county, 30 mins away from Boston",
            {"intent": "recommend_structured", "use_semantic": False},
        ),
        (
            "semantic vibe",
            "Quiet town with a coastal feel and good schools",
            {"intent": "recommend_semantic", "use_semantic": True},
        ),
        (
            "semantic like town",
            "towns like Wellesley but I only have 650k",
            {"intent": "recommend_semantic", "use_semantic": True},
        ),
        (
            "semantic walkable",
            "Walkable downtown feel under $800k",
            {"intent": "recommend_semantic", "use_semantic": True},
        ),
        (
            "relative structured",
            "safer than Lynn but cheaper than Newton",
            {"intent": "recommend_structured", "use_semantic": False},
        ),
        (
            "explain ranking",
            "why did Sharon beat Westford",
            {"intent": "explain_ranking"},
        ),
        (
            "data limit zillow",
            "do you have Zillow prices today",
            {"intent": "data_limit_question"},
        ),
        (
            "data limit redfin",
            "show me live Redfin listings",
            {"intent": "data_limit_question"},
        ),
        (
            "work context clarification",
            "I work in Westborough",
            {"intent": "needs_clarification"},
        ),
        (
            "unsupported off-topic",
            "write me a recipe for pasta",
            {"intent": "unsupported"},
        ),
        (
            "north shore structured",
            "North Shore family-friendly suburb with strong schools",
            {"intent": "recommend_structured", "use_semantic": False},
        ),
        (
            "coastal structured hard filter",
            "coastal town under 900k with good schools",
            {"intent": "recommend_structured", "use_semantic": False},
        ),
        (
            "affordable structured",
            "Affordable suburb with strong schools and decent commute",
            {"intent": "recommend_structured", "use_semantic": False},
        ),
        (
            "high crime structured",
            "high crime towns near Boston",
            {"intent": "recommend_structured", "use_semantic": False},
        ),
    ]

    print(f"1. Intent routing cases ({len(cases)})")
    for label, query, expected in cases:
        try:
            _expect(label, query, **expected)
            print(f"  PASS: {label}")
        except AssertionError as exc:
            print(f"  FAIL: {exc}")
            sys.exit(1)

    from app.query_router import classify_query

    print("\n2. Pipeline checks")
    lookup = classify_query("commute for Gardner")
    if lookup.pipeline != ["get_town_facts_tool"]:
        print(f"  FAIL: lookup pipeline — {lookup.pipeline}")
        sys.exit(1)
    print("  PASS: lookup pipeline")

    semantic = classify_query("something like Lexington but cheaper")
    if "semantic_town_search_tool" not in semantic.pipeline:
        print(f"  FAIL: semantic pipeline — {semantic.pipeline}")
        sys.exit(1)
    print("  PASS: semantic pipeline")

    structured = classify_query("safe suburb under 900k")
    if structured.pipeline[0] != "parse_preferences_tool":
        print(f"  FAIL: structured pipeline — {structured.pipeline}")
        sys.exit(1)
    print("  PASS: structured pipeline")

    compare = classify_query("Compare Acton and Framingham")
    if compare.pipeline[0] != "compare_suburbs_tool":
        print(f"  FAIL: compare pipeline — {compare.pipeline}")
        sys.exit(1)
    print("  PASS: compare pipeline")

    print("\n3. Unknown town preserved")
    route = classify_query("is Charlton in your dataset")
    if "Charlton" not in (route.unknown_towns or []):
        print(f"  FAIL: expected Charlton unknown — {route.unknown_towns}")
        sys.exit(1)
    print("  PASS: Charlton flagged unknown on membership query")

    print("\nStep 5 verification: PASSED")
    print("Next: Step 6 — response_validator.py")


if __name__ == "__main__":
    main()
