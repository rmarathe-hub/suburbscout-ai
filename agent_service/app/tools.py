"""Microsoft Agent Framework tools for suburb recommendations."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from difflib import get_close_matches
from typing import Annotated, Any

from agent_framework import tool
from pydantic import Field

from app.ranking import (
    describe_active_filters,
    load_suburbs,
    parse_preferences_from_query,
    rank_suburbs,
)
from app.suburb_store import suburbs_data_source
from app.schemas import Preferences
from app.town_normalizer import canonical_town_name, normalize_key, resolve_town_in_dataset
from app.vector_store import search_towns_by_text

SCORE_DISCLAIMER = (
    "Scores are 0-10 percentile ranks within the 200-town dataset, "
    "not official government ratings."
)


def _coerce_preferences(preferences: Any, user_prompt: str) -> Preferences:
    """Build Preferences from tool dict and/or the original user prompt."""
    if isinstance(preferences, str):
        preferences = json.loads(preferences)
    if isinstance(preferences, dict) and preferences:
        cleaned = {k: v for k, v in preferences.items() if v is not None}
        return Preferences(**cleaned)
    return parse_preferences_from_query(user_prompt)


def _find_town(name: str, suburbs: list[dict[str, Any]]) -> dict[str, Any] | None:
    canonical = canonical_town_name(name)
    for candidate in (name, canonical):
        key = normalize_key(candidate)
        for suburb in suburbs:
            if normalize_key(suburb["name"]) == key:
                return suburb
    return None


def _resolve_compare_town(name: str, suburbs: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, str]:
    """Exact match first; high-confidence fuzzy typo correction for comparisons."""
    queried = (name or "").strip()
    match = _find_town(queried, suburbs)
    if match is not None:
        return match, queried
    names = [s["name"] for s in suburbs]
    resolved_name = resolve_town_in_dataset(queried, names)
    if resolved_name:
        return _find_town(resolved_name, suburbs), resolved_name
    return None, queried


def _public_suburb_record(suburb: dict[str, Any]) -> dict[str, Any]:
    """Return suburb fields safe to expose to the agent (no internal-only keys)."""
    return {
        "name": suburb.get("name"),
        "region": suburb.get("region"),
        "county": suburb.get("county"),
        "population": suburb.get("population"),
        "latest_home_price": suburb.get("latest_home_price"),
        "home_price_year": suburb.get("home_price_year"),
        "dor_income_per_capita": suburb.get("dor_income_per_capita"),
        "eqv_per_capita": suburb.get("eqv_per_capita"),
        "economic_score": suburb.get("economic_score"),
        "crime_rate_per_1000": suburb.get("crime_rate_per_1000"),
        "safety_score": suburb.get("safety_score"),
        "drive_minutes_to_boston": suburb.get("drive_minutes_to_boston"),
        "drive_distance_miles_to_boston": suburb.get("drive_distance_miles_to_boston"),
        "commute_score": suburb.get("commute_score"),
        "school_score": suburb.get("school_score"),
        "affordability_score": suburb.get("affordability_score"),
        "family_score": suburb.get("family_score"),
        "missing_fields": suburb.get("missing_fields", []),
        "data_quality_tier": suburb.get("data_quality_tier"),
        "data_sources": suburb.get("data_sources", []),
        "tags": suburb.get("tags", []),
        "is_coastal": suburb.get("is_coastal"),
        "is_coastal_source": suburb.get("is_coastal_source"),
        "region_key": suburb.get("region_key"),
        "score_disclaimer": SCORE_DISCLAIMER,
    }


def _close_town_matches(
    query: str,
    suburbs: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[str]:
    """Suggest similar town names from the dataset (never used as silent substitution)."""
    key = normalize_key(query)
    if not key:
        return []

    names = [s["name"] for s in suburbs]
    keys = [normalize_key(n) for n in names]
    key_to_name = dict(zip(keys, names))

    matches: list[str] = []
    seen: set[str] = set()

    for candidate_key in get_close_matches(key, keys, n=limit, cutoff=0.6):
        name = key_to_name[candidate_key]
        if name not in seen:
            matches.append(name)
            seen.add(name)

    # Prefix match helps short typos like "Actn" -> Acton
    if len(matches) < limit:
        for town_key, name in key_to_name.items():
            if town_key.startswith(key[:3]) or key.startswith(town_key[:3]):
                if name not in seen:
                    matches.append(name)
                    seen.add(name)
                if len(matches) >= limit:
                    break

    return matches[:limit]


def get_town_facts(town_name: str, *, suburbs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Look up one town from suburbs.json. No ranking; no silent substitution."""
    queried = (town_name or "").strip()
    if not queried:
        return {
            "found": False,
            "queried_name": queried,
            "town": None,
            "close_matches": [],
            "in_dataset": False,
            "message": "Town name is required.",
            "score_disclaimer": SCORE_DISCLAIMER,
            "data_source": suburbs_data_source(),
            "usage_note": (
                "Direct town lookup only. Use for single-town facts or dataset membership checks. "
                "Do not rank or answer about a different town when found=false."
            ),
        }

    active = suburbs if suburbs is not None else load_suburbs()
    canonical_query = canonical_town_name(queried)
    match = _find_town(canonical_query, active)

    base = {
        "queried_name": queried,
        "score_disclaimer": SCORE_DISCLAIMER,
        "data_source": suburbs_data_source(),
        "usage_note": (
            "Direct town lookup only. Use for single-town facts or dataset membership checks. "
            "Do not rank or substitute another town when found=false."
        ),
    }

    if match is not None:
        return {
            **base,
            "found": True,
            "town": _public_suburb_record(match),
            "close_matches": [],
            "in_dataset": True,
            "message": None,
        }

    close = _close_town_matches(queried, active)
    return {
        **base,
        "found": False,
        "town": None,
        "close_matches": close,
        "in_dataset": False,
        "message": (
            f"'{queried}' is not in the curated 200-town suburbs.json dataset."
        ),
    }


@tool(approval_mode="never_require")
def get_town_facts_tool(
    town_name: Annotated[
        str,
        Field(description="Massachusetts town name to look up in suburbs.json."),
    ],
) -> dict[str, Any]:
    """Return factual data for one town from suburbs.json. Never ranks or substitutes another town."""
    return get_town_facts(town_name)


@tool(approval_mode="never_require")
def parse_preferences_tool(
    prompt: Annotated[str, Field(description="User's natural-language suburb search request.")],
) -> dict[str, Any]:
    """Parse a user prompt into structured ranking preferences (rule-based, no LLM)."""
    prefs = parse_preferences_from_query(prompt)
    return prefs.model_dump(exclude_none=True)


@tool(approval_mode="never_require")
def rank_suburbs_tool(
    user_prompt: Annotated[
        str,
        Field(description="Original user search prompt (always pass the full user message)."),
    ],
    preferences: Annotated[
        dict[str, Any] | None,
        Field(
            description="Optional: full JSON object returned by parse_preferences_tool. "
            "If omitted, preferences are parsed from user_prompt."
        ),
    ] = None,
    top_n: Annotated[int, Field(description="Number of top suburbs to return.", ge=1, le=20)] = 5,
    candidate_towns: Annotated[
        list[str] | None,
        Field(
            description="Optional town names from semantic_town_search_tool to limit ranking scope."
        ),
    ] = None,
) -> list[dict[str, Any]]:
    """Rank suburbs deterministically using suburbs.json only. Never invents towns or scores."""
    prefs = _coerce_preferences(preferences, user_prompt)
    if candidate_towns:
        prefs.candidate_towns = candidate_towns
    results = rank_suburbs(prefs, top_n=top_n)
    if not results:
        filters = describe_active_filters(prefs)
        return [{
            "name": None,
            "score": None,
            "matched_factors": [],
            "reasons": [],
            "tradeoffs": [],
            "data": {},
            "no_matches": True,
            "message": "No towns matched the hard filters for this query.",
            "filters_applied": filters,
            "score_disclaimer": SCORE_DISCLAIMER,
        }]
    for row in results:
        row["score_disclaimer"] = SCORE_DISCLAIMER
    return results


@tool(approval_mode="never_require")
def compare_suburbs_tool(
    town_a: Annotated[str, Field(description="First Massachusetts town name.")],
    town_b: Annotated[str, Field(description="Second Massachusetts town name.")],
) -> dict[str, Any]:
    """Compare two towns using only data from suburbs.json."""
    suburbs = load_suburbs()
    a, resolved_a = _resolve_compare_town(town_a, suburbs)
    b, resolved_b = _resolve_compare_town(town_b, suburbs)

    if a is None:
        return {
            "error": f"Town '{town_a}' is not in suburbs.json.",
            "available_towns_hint": "Use only towns from the curated 200-town list.",
            "queried_town_a": town_a,
            "queried_town_b": town_b,
        }
    if b is None:
        return {
            "error": f"Town '{town_b}' is not in suburbs.json.",
            "available_towns_hint": "Use only towns from the curated 200-town list.",
            "queried_town_a": town_a,
            "queried_town_b": town_b,
        }

    payload: dict[str, Any] = {
        "town_a": _public_suburb_record(a),
        "town_b": _public_suburb_record(b),
        "score_disclaimer": SCORE_DISCLAIMER,
        "data_source": suburbs_data_source(),
    }
    if resolved_a != town_a:
        payload["resolved_town_a"] = resolved_a
    if resolved_b != town_b:
        payload["resolved_town_b"] = resolved_b
    return payload


def compare_suburbs_multi_tool(
    towns: list[str],
    *,
    columns: list[str] | None = None,
) -> dict[str, Any]:
    """Compare up to 20 towns — returns a structured comparison table from suburbs.json."""
    from app.query_patterns import COMPARE_TABLE_COLUMNS, MAX_MULTI_COMPARE_TOWNS

    if not towns:
        return {"error": "No towns provided for comparison."}
    if len(towns) > MAX_MULTI_COMPARE_TOWNS:
        return {
            "error": f"At most {MAX_MULTI_COMPARE_TOWNS} towns can be compared at once.",
            "town_count": len(towns),
        }

    col_keys = columns or [
        "latest_home_price",
        "drive_minutes_to_boston",
        "safety_score",
        "school_score",
    ]
    label_by_key = {src: label for src, _, label in COMPARE_TABLE_COLUMNS}
    col_defs = [(src, alias, label_by_key.get(src, alias)) for src, alias, label in COMPARE_TABLE_COLUMNS if src in col_keys]

    suburbs = load_suburbs()
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    resolved_order: list[str] = []

    for raw_name in towns:
        suburb, resolved = _resolve_compare_town(raw_name.strip(), suburbs)
        display = resolved or raw_name
        if suburb is None:
            errors.append(f"'{raw_name}' is not in suburbs.json.")
            continue
        row: dict[str, Any] = {"town": suburb["name"]}
        if resolved != raw_name.strip():
            row["queried_as"] = raw_name.strip()
        for src_key, alias, _label in col_defs:
            row[alias] = suburb.get(src_key)
        rows.append(row)
        resolved_order.append(suburb["name"])

    return {
        "comparison_table": rows,
        "columns": [{"key": alias, "label": label} for _src, alias, label in col_defs],
        "towns": resolved_order,
        "errors": errors,
        "town_count": len(rows),
        "score_disclaimer": SCORE_DISCLAIMER,
        "data_source": suburbs_data_source(),
    }


@tool(approval_mode="never_require")
def explain_results_tool(
    user_prompt: Annotated[
        str,
        Field(description="Original user search prompt."),
    ],
    results: Annotated[
        list[dict[str, Any]] | None,
        Field(description="Ranked results from rank_suburbs_tool (pass the full list)."),
    ] = None,
    top_matches: Annotated[
        list[dict[str, Any]] | None,
        Field(description="Alias for results when passing rank_suburbs_tool output."),
    ] = None,
    preferences: Annotated[
        dict[str, Any] | None,
        Field(description="Optional preferences from parse_preferences_tool."),
    ] = None,
) -> dict[str, Any]:
    """Explain ranked results using only provided tool data. Does not invent statistics."""
    results = results if results is not None else top_matches
    if not results:
        return {
            "summary": "No ranked results were provided to explain.",
            "tradeoff_warning": None,
            "final_recommendation": None,
            "score_disclaimer": SCORE_DISCLAIMER,
        }

    prefs = _coerce_preferences(preferences, user_prompt)
    top = results[0]
    name = top.get("name", "Unknown")
    score = top.get("score")
    reasons = top.get("reasons") or []
    tradeoffs = top.get("tradeoffs") or []

    preference_bits = []
    if prefs.budget_max:
        preference_bits.append(f"budget around ${prefs.budget_max:,}")
    if prefs.safety_priority == "high":
        preference_bits.append("strong safety")
    if prefs.school_priority == "high":
        preference_bits.append("good schools")
    if prefs.commute_priority == "high":
        preference_bits.append("reasonable commute")
    if prefs.affordability_priority == "high":
        preference_bits.append("affordability")

    pref_text = ", ".join(preference_bits) if preference_bits else "your stated priorities"

    summary_lines = [
        f"Top match: {name} (score {score}/10).",
        f"Matched priorities: {pref_text}.",
    ]
    if reasons:
        summary_lines.append("Key reasons: " + "; ".join(reasons[:4]))

    tradeoff_warning = None
    partial = [r for r in results if (r.get("data") or {}).get("data_quality_tier") == "partial"]
    if partial:
        tradeoff_warning = (
            f"{len(partial)} of {len(results)} top results have partial data "
            f"(missing_fields noted per town)."
        )
    if any("budget" in t.lower() for t in tradeoffs for r in results for t in (r.get("tradeoffs") or [])):
        tradeoff_warning = (tradeoff_warning or "") + " Some options may be above budget."

    housing_missing = [
        r["name"]
        for r in results
        if "latest_home_price" in (r.get("data") or {}).get("missing_fields", [])
    ]
    if housing_missing:
        note = (
            " Housing price data was unavailable for: "
            + ", ".join(housing_missing[:3])
            + "."
        )
        tradeoff_warning = (tradeoff_warning or "") + note

    final = (
        f"I recommend {name} based on your preferences ({pref_text}). "
        f"It ranked highest with a score of {score}/10."
    )
    if tradeoffs:
        final += f" Note: {tradeoffs[0]}."

    return {
        "summary": " ".join(summary_lines),
        "tradeoff_warning": tradeoff_warning.strip() if tradeoff_warning else None,
        "final_recommendation": final,
        "top_matches": results,
        "score_disclaimer": SCORE_DISCLAIMER,
    }


@tool(approval_mode="never_require")
def save_search_tool(
    prompt: Annotated[str, Field(description="Original user prompt.")],
    results: Annotated[
        list[dict[str, Any]] | None,
        Field(description="Ranked or compare results to log."),
    ] = None,
    top_matches: Annotated[
        list[dict[str, Any]] | None,
        Field(description="Alias for results from rank_suburbs_tool."),
    ] = None,
    preferences: Annotated[
        dict[str, Any] | None,
        Field(description="Optional parsed preferences from parse_preferences_tool."),
    ] = None,
) -> dict[str, Any]:
    """Append this search to Postgres (or saved_searches.jsonl fallback)."""
    results = results if results is not None else top_matches
    if results is None:
        results = []
    prefs_dict = (
        preferences
        if isinstance(preferences, dict) and preferences
        else _coerce_preferences(None, prompt).model_dump(exclude_none=True)
    )
    from app.repositories import persist_legacy_search

    return persist_legacy_search(
        prompt,
        results=results,
        preferences=prefs_dict,
    )


async def run_semantic_town_search(query: str, *, top_k: int = 15) -> dict[str, Any]:
    """Core semantic search logic (also used by the agent tool)."""
    try:
        matches = await search_towns_by_text(query, top_k=top_k)
    except FileNotFoundError as exc:
        return {
            "query": query,
            "error": str(exc),
            "candidates": [],
            "candidate_town_names": [],
            "usage_note": "Run scripts/build_vector_index.py before semantic search.",
        }

    candidates = []
    for match in matches:
        candidates.append({
            "name": match.name,
            "similarity_score": match.score,
            "region": match.region,
            "tags": match.tags,
            "snippet": match.snippet,
        })

    names = [c["name"] for c in candidates]
    return {
        "query": query,
        "candidates": candidates,
        "candidate_town_names": names,
        "usage_note": (
            "Semantic search returns candidate towns only. "
            "Pass candidate_town_names to rank_suburbs_tool as candidate_towns, "
            "then rank deterministically — do not treat similarity_score as final ranking."
        ),
        "score_disclaimer": SCORE_DISCLAIMER,
        "data_source": "town_profiles.json + local vector index",
    }


@tool(approval_mode="never_require")
async def semantic_town_search_tool(
    query: Annotated[
        str,
        Field(description="Fuzzy or vibe-based suburb search text from the user."),
    ],
    top_k: Annotated[
        int,
        Field(description="Number of semantic candidates to return.", ge=1, le=30),
    ] = 15,
) -> dict[str, Any]:
    """Find candidate towns via local vector search on town profiles. Does not rank or invent data."""
    return await run_semantic_town_search(query, top_k=top_k)


# Day 2 core tools (unchanged for step 2 verification).
CORE_AGENT_TOOLS = [
    parse_preferences_tool,
    rank_suburbs_tool,
    compare_suburbs_tool,
    explain_results_tool,
    save_search_tool,
]

# Full Phase 1 agent toolset (Day 3+; Phase 1.1 adds get_town_facts_tool).
AGENT_TOOLS = [
    get_town_facts_tool,
    *CORE_AGENT_TOOLS,
    semantic_town_search_tool,
]

# Interactive CLI: same tools minus save (avoids growing saved_searches.jsonl every turn).
INTERACTIVE_AGENT_TOOLS = [
    get_town_facts_tool,
    parse_preferences_tool,
    rank_suburbs_tool,
    compare_suburbs_tool,
    explain_results_tool,
    semantic_town_search_tool,
]
