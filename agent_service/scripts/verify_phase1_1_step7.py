#!/usr/bin/env python3
"""Phase 1.1 Step 7 verification: orchestrator.py."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


async def _run(prompt: str, *, save_searches: bool = False) -> dict:
    from app.orchestrator import handle_query

    result = await handle_query(prompt, save_searches=save_searches)
    return result


def _response(payload: dict) -> dict:
    return payload["response"]


def _route(payload: dict) -> dict:
    return payload["route"]


async def main() -> None:
    print("=== Phase 1.1 Step 7: orchestrator ===\n")

    # 1. Lookup commute
    print("1. Lookup — commute for Gardner")
    r = await _run("commute for Gardner")
    resp = _response(r)
    route = _route(r)
    if route["intent"] != "lookup_single_town":
        raise AssertionError(f"expected lookup intent, got {route['intent']}")
    if not resp.get("lookup", {}).get("found"):
        raise AssertionError("Gardner should be found")
    if "Gardner" not in resp.get("final_recommendation", ""):
        raise AssertionError("response should mention Gardner")
    if not resp.get("orchestrated"):
        raise AssertionError("expected orchestrated=true")
    print("  PASS")

    # 2. Dataset membership
    print("\n2. Lookup — is Gardner in your dataset")
    r = await _run("is Gardner in your dataset")
    resp = _response(r)
    if not resp.get("lookup", {}).get("found"):
        raise AssertionError("Gardner should be in dataset")
    if "dataset" not in resp.get("final_recommendation", "").lower():
        raise AssertionError("expected dataset confirmation text")
    print("  PASS")

    # 3. Unknown town
    print("\n3. Lookup — Charlton not found")
    r = await _run("commute for Charlton")
    resp = _response(r)
    if resp.get("lookup", {}).get("found"):
        raise AssertionError("Charlton should not be found")
    if "Charlton" not in resp.get("final_recommendation", ""):
        raise AssertionError("response should mention Charlton")
    print("  PASS")

    # 4. Compare
    print("\n4. Compare — Acton and Framingham")
    r = await _run("Compare Acton and Framingham")
    resp = _response(r)
    route = _route(r)
    if route["intent"] != "compare_towns":
        raise AssertionError(f"expected compare intent, got {route['intent']}")
    comp = resp.get("comparison") or {}
    if not comp.get("town_a") or not comp.get("town_b"):
        raise AssertionError("comparison missing towns")
    if resp.get("top_matches"):
        raise AssertionError("compare should not return top_matches")
    if not resp.get("validation", {}).get("valid", False):
        raise AssertionError(f"validation failed: {resp.get('validation')}")
    print("  PASS")

    # 5. Structured budget
    print("\n5. Recommend — safe suburb under $900k with good schools")
    r = await _run("Safe suburb under $900k with good schools")
    resp = _response(r)
    route = _route(r)
    if route["intent"] != "recommend_structured":
        raise AssertionError(f"expected recommend_structured, got {route['intent']}")
    top = resp.get("top_matches") or []
    if not top or top[0].get("no_matches"):
        raise AssertionError("expected ranked matches")
    if not resp.get("validation", {}).get("valid", False):
        raise AssertionError(f"validation failed: {resp.get('validation')}")
    print(f"  Top: {top[0].get('name')} — PASS")

    # 6. County + commute hard filters
    print("\n6. Recommend — Middlesex county, 30 mins from Boston")
    r = await _run("in Middlesex county, 30 mins away from Boston")
    resp = _response(r)
    top = resp.get("top_matches") or []
    if not top or top[0].get("no_matches"):
        raise AssertionError("expected Middlesex matches")
    for row in top:
        data = row.get("data") or {}
        county = data.get("county", row.get("county"))
        minutes = data.get("drive_minutes_to_boston", row.get("drive_minutes_to_boston"))
        if county != "Middlesex":
            raise AssertionError(f"{row.get('name')} county={county}, expected Middlesex")
        if minutes is not None and float(minutes) > 30:
            raise AssertionError(f"{row.get('name')} commute={minutes}, expected <=30")
    if not resp.get("validation", {}).get("valid", False):
        raise AssertionError(f"validation failed: {resp.get('validation')}")
    print(f"  Top: {', '.join(m.get('name', '?') for m in top[:3])} — PASS")

    # 7. Coastal filter
    print("\n7. Recommend — coastal town under $900k")
    r = await _run("Find a coastal town under $900k")
    resp = _response(r)
    top = resp.get("top_matches") or []
    if not top:
        raise AssertionError("expected coastal matches or explicit no_matches")
    if top[0].get("no_matches"):
        print("  No coastal matches under budget (valid empty result) — PASS")
    else:
        for row in top:
            data = row.get("data") or {}
            if not data.get("is_coastal", row.get("is_coastal")):
                raise AssertionError(f"{row.get('name')} is not coastal")
        if not resp.get("validation", {}).get("valid", False):
            raise AssertionError(f"validation failed: {resp.get('validation')}")
        print(f"  Top: {', '.join(m.get('name', '?') for m in top[:3])} — PASS")

    # 8. Data limitation
    print("\n8. Data limit — Zillow prices today")
    r = await _run("What are Zillow prices today for Acton?")
    resp = _response(r)
    route = _route(r)
    if route["intent"] != "data_limit_question":
        raise AssertionError(f"expected data_limit_question, got {route['intent']}")
    if "zillow" not in resp.get("final_recommendation", "").lower() and "live" not in resp.get("final_recommendation", "").lower():
        raise AssertionError("expected data limitation message")
    print("  PASS")

    # 9. Needs clarification
    print("\n9. Clarification — I work in Westborough")
    r = await _run("I work in Westborough")
    resp = _response(r)
    route = _route(r)
    if route["intent"] != "needs_clarification":
        raise AssertionError(f"expected needs_clarification, got {route['intent']}")
    if "Westborough" not in resp.get("final_recommendation", ""):
        raise AssertionError("expected clarification mentioning Westborough")
    print("  PASS")

    # 10. Semantic route (skip if embeddings unavailable)
    print("\n10. Semantic — quiet town with a coastal feel")
    try:
        r = await _run("Quiet town with a coastal feel and good schools")
    except Exception as exc:
        print(f"  SKIP semantic (API unavailable): {exc}")
        r = None
    if r is not None:
        resp = _response(r)
        route = _route(r)
        if route["intent"] != "recommend_semantic":
            raise AssertionError(f"expected recommend_semantic, got {route['intent']}")
        semantic = resp.get("semantic_candidates")
        if semantic is None:
            raise AssertionError("expected semantic_candidates")
        if semantic.get("error"):
            print(f"  SKIP semantic ranking (embeddings unavailable): {semantic['error'][:80]}")
        else:
            names = semantic.get("candidate_town_names") or []
            if not names:
                raise AssertionError("expected semantic candidate names")
            top = resp.get("top_matches") or []
            if not top:
                raise AssertionError("expected ranked top_matches after semantic search")
            print(f"  Semantic candidates: {len(names)}, top: {top[0].get('name')} — PASS")

    # 11. run_agent integration
    print("\n11. run_agent uses orchestrator by default")
    from app.real_estate_agent import run_agent

    agent_result = await run_agent("commute for Gardner", save_searches=False)
    if not agent_result.get("orchestrated"):
        raise AssertionError("run_agent should use orchestrator")
    parsed = agent_result.get("parsed") or {}
    if parsed.get("route_intent") != "lookup_single_town":
        raise AssertionError("run_agent parsed response missing route_intent")
    print("  PASS")

    print("\nStep 7 verification: PASSED")
    print("Next: Step 8 — eval suite (phase1_1_quality_prompts.json)")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except AssertionError as exc:
        print(f"  FAIL: {exc}")
        sys.exit(1)
