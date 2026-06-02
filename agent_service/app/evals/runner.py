#!/usr/bin/env python3
"""Evaluate orchestrator responses against property-based quality checks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.town_normalizer import canonical_town_name, normalize_key

EVALS_DIR = Path(__file__).resolve().parent
DEFAULT_PROMPTS_PATH = EVALS_DIR / "phase1_1_quality_prompts.json"


def load_eval_cases(path: Path | None = None) -> list[dict[str, Any]]:
    target = path or DEFAULT_PROMPTS_PATH
    with open(target, encoding="utf-8") as f:
        payload = json.load(f)
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        raise ValueError(f"Invalid eval file: {target}")
    return cases


def _row_data(row: dict[str, Any]) -> dict[str, Any]:
    data = row.get("data")
    return data if isinstance(data, dict) else row


def _ranked_rows(response: dict[str, Any]) -> list[dict[str, Any]]:
    top = response.get("top_matches") or []
    return [row for row in top if isinstance(row, dict) and not row.get("no_matches")]


def _text_blob(response: dict[str, Any]) -> str:
    return json.dumps(response) + " " + str(response.get("final_recommendation") or "")


def evaluate_case(case: dict[str, Any], result: dict[str, Any]) -> tuple[bool, list[str]]:
    """Return (passed, failure_reasons) for one eval case."""
    response = result.get("response") or {}
    route = result.get("route") or {}
    failures: list[str] = []

    expect_intent = case.get("expect_intent")
    if expect_intent and route.get("intent") != expect_intent:
        failures.append(f"intent expected {expect_intent!r}, got {route.get('intent')!r}")

    expect_any = case.get("expect_any_intent")
    if expect_any and route.get("intent") not in expect_any:
        failures.append(f"intent expected one of {expect_any!r}, got {route.get('intent')!r}")

    checks = case.get("must_satisfy") or {}

    if checks.get("orchestrated") and not response.get("orchestrated"):
        failures.append("expected orchestrated=true")

    if "validation_valid" in checks:
        valid = (response.get("validation") or {}).get("valid")
        if valid is not checks["validation_valid"]:
            failures.append(f"validation.valid expected {checks['validation_valid']}, got {valid}")

    lookup = response.get("lookup") or {}
    if "lookup_found" in checks and lookup.get("found") is not checks["lookup_found"]:
        failures.append(f"lookup.found expected {checks['lookup_found']}, got {lookup.get('found')}")

    if town := checks.get("mentions_town"):
        blob = _text_blob(response).lower()
        if canonical_town_name(town).lower() not in blob:
            failures.append(f"expected mention of town {town!r}")

    top = response.get("top_matches") or []
    ranked = _ranked_rows(response)
    has_no_match_only = bool(top) and len(top) == 1 and top[0].get("no_matches")

    if checks.get("no_top_matches") and top:
        failures.append("expected empty top_matches")

    if checks.get("has_top_matches") and not ranked:
        failures.append("expected ranked top_matches")

    if checks.get("no_matches_ok"):
        pass
    elif checks.get("require_matches") and not ranked:
        failures.append("expected at least one ranked match")

    if checks.get("no_matches_only") and not has_no_match_only:
        failures.append("expected explicit no_matches result")

    if checks.get("has_final_recommendation") and not response.get("final_recommendation"):
        failures.append("expected final_recommendation text")

    for fragment in checks.get("message_contains") or []:
        if fragment.lower() not in _text_blob(response).lower():
            failures.append(f"expected text containing {fragment!r}")

    comp = response.get("comparison")
    if checks.get("has_comparison") and not comp:
        failures.append("expected comparison object")

    if compare_towns := checks.get("compare_towns"):
        if not comp:
            failures.append("expected comparison for compare_towns check")
        elif comp.get("error"):
            failures.append(str(comp["error"]))
        else:
            a = (comp.get("town_a") or {}).get("name")
            b = (comp.get("town_b") or {}).get("name")
            expected = {normalize_key(t) for t in compare_towns}
            actual = {normalize_key(n) for n in (a, b) if n}
            if actual != expected:
                failures.append(f"compare towns expected {compare_towns}, got [{a}, {b}]")

    semantic = response.get("semantic_candidates")
    if checks.get("semantic_attempted") and semantic is None:
        failures.append("expected semantic_candidates (semantic route)")

    if checks.get("semantic_candidates_or_error"):
        if semantic is None:
            failures.append("expected semantic_candidates or graceful semantic error")
        elif not semantic.get("candidate_town_names") and not semantic.get("error"):
            failures.append("semantic search returned empty without error")

    if checks.get("all_coastal"):
        for row in ranked:
            data = _row_data(row)
            if not data.get("is_coastal"):
                failures.append(f"{row.get('name')} is not coastal")

    if price_lte := checks.get("all_price_lte"):
        for row in ranked:
            data = _row_data(row)
            price = data.get("latest_home_price")
            if price is None:
                failures.append(f"{row.get('name')} missing price for budget check")
            elif float(price) > float(price_lte):
                failures.append(f"{row.get('name')} price {price} > {price_lte}")

    if commute_lte := checks.get("all_commute_lte"):
        for row in ranked:
            data = _row_data(row)
            minutes = data.get("drive_minutes_to_boston")
            if minutes is None:
                failures.append(f"{row.get('name')} missing commute for max check")
            elif float(minutes) > float(commute_lte):
                failures.append(f"{row.get('name')} commute {minutes} > {commute_lte}")

    if commute_gte := checks.get("all_commute_gte"):
        for row in ranked:
            data = _row_data(row)
            minutes = data.get("drive_minutes_to_boston")
            if minutes is None:
                failures.append(f"{row.get('name')} missing commute for min check")
            elif float(minutes) < float(commute_gte):
                failures.append(f"{row.get('name')} commute {minutes} < {commute_gte}")

    if county := checks.get("all_county"):
        for row in ranked:
            data = _row_data(row)
            if (data.get("county") or "").lower() != county.lower():
                failures.append(f"{row.get('name')} county {data.get('county')!r} != {county!r}")

    if region := checks.get("all_region"):
        for row in ranked:
            data = _row_data(row)
            if data.get("region") != region:
                failures.append(f"{row.get('name')} region {data.get('region')!r} != {region!r}")

    return (not failures, failures)
