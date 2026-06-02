"""Deterministic query orchestrator (Phase 1.1) — router-driven tool pipelines."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.intent_rules import infer_strict_intent
from app.hybrid_intent_router import classify_query_hybrid
from app.query_router import QueryRoute
from app.lookup_schema import build_unsupported_field_message
from app.query_patterns import infer_lookup_fields, is_multi_field_lookup
from app.trust_gates import TrustGateResult, evaluate_trust_gate
from app.response_validator import ValidationResult, validate_agent_response, validate_lookup_response
from app.tools import (
    SCORE_DISCLAIMER,
    compare_suburbs_multi_tool,
    compare_suburbs_tool,
    explain_results_tool,
    get_town_facts,
    parse_preferences_tool,
    rank_suburbs_tool,
    run_semantic_town_search,
    save_search_tool,
)

logger = logging.getLogger(__name__)


def _effective_pipeline(route: QueryRoute, *, save_searches: bool) -> list[str]:
    pipeline = list(route.pipeline)
    if not save_searches:
        pipeline = [step for step in pipeline if step != "save_search_tool"]
    return pipeline


def _format_price(value: float | int | None) -> str:
    if value is None:
        return "unavailable"
    return f"${int(value):,}"


def _default_town_summary(town: dict[str, Any]) -> str:
    name = town.get("name", "Unknown")
    bits = [
        f"{name} facts from suburbs.json:",
        f"median home price {_format_price(town.get('latest_home_price'))}",
        f"commute {town.get('drive_minutes_to_boston', 'n/a')} min to Boston",
        f"safety score {town.get('safety_score', 'n/a')}/10",
        f"school score {town.get('school_score', 'n/a')}/10",
    ]
    if town.get("is_coastal"):
        bits.append("coastal town")
    return ". ".join(str(b) for b in bits) + "."


def _lookup_field_snippet(name: str, town: dict[str, Any], field: str) -> str:
    if field == "commute":
        minutes = town.get("drive_minutes_to_boston")
        miles = town.get("drive_distance_miles_to_boston")
        if minutes is not None:
            return (
                f"{name} is {miles or 'n/a'} miles from South Station, Boston "
                f"({minutes} minute drive commute according to suburbs.json)."
            )
        return f"Commute data is unavailable for {name}."
    if field == "price":
        price = town.get("latest_home_price")
        year = town.get("home_price_year")
        if price is not None:
            suffix = f" ({year} data)" if year else ""
            return f"{name} latest median home price is {_format_price(price)}{suffix}."
        return f"Housing price data is unavailable for {name}."
    if field == "school":
        score = town.get("school_score")
        if score is not None:
            return f"{name} has a school score of {score}/10 (percentile within dataset)."
        return f"School score data is unavailable for {name}."
    if field == "safety":
        rate = town.get("crime_rate_per_1000")
        score = town.get("safety_score")
        if rate is not None:
            return f"{name} has a crime rate of {rate} per 1,000 residents (safety score {score}/10)."
        return f"Crime data is unavailable for {name}."
    if field == "coastal":
        if town.get("is_coastal"):
            return f"Yes, {name} is a coastal town in the dataset."
        return f"No, {name} is not a coastal town in the dataset."
    return _default_town_summary(town)


def _build_lookup_narrative(query: str, lookup: dict[str, Any]) -> str:
    if not lookup.get("found"):
        message = lookup.get("message") or "Town not found in the curated dataset."
        close = lookup.get("close_matches") or []
        if "closest matches" in query.lower() and close:
            return f"Closest matches to your query: {', '.join(close[:5])}."
        if close:
            message += f" Did you mean: {', '.join(close[:5])}?"
        return message

    town = lookup["town"] or {}
    name = town.get("name", "Unknown")
    lower = query.lower()

    if is_multi_field_lookup(query):
        fields = infer_lookup_fields(lower)
        if len(fields) >= 2:
            return " ".join(_lookup_field_snippet(name, town, field) for field in fields)

    if re.search(r"\bexcluded\b", lower) and re.search(r"\bis\s+.+\s+excluded\b", lower):
        return f"No, {name} is included in the curated 200-town suburbs.json dataset."

    if "dataset" in lower or "in your" in lower or "in the list" in lower or "included" in lower or "do you cover" in lower or "do you have" in lower or "supported" in lower:
        return f"Yes, {name} is in the curated 200-town suburbs.json dataset."

    if re.search(r"\bis\s+.+\s+coastal\b", lower) or "marked coastal" in lower or "actually coastal" in lower:
        if town.get("is_coastal"):
            return f"Yes, {name} is a coastal town in the dataset."
        return f"No, {name} is not a coastal town in the dataset."

    if "region" in lower:
        region = town.get("region")
        return f"{name} is in the {region} region." if region else f"Region data is unavailable for {name}."

    if "county" in lower:
        county = town.get("county")
        return f"{name} is in {county} county." if county else f"County data is unavailable for {name}."

    if "missing" in lower:
        missing = town.get("missing_fields") or []
        if missing:
            return f"Missing fields for {name}: {', '.join(missing)}."
        return f"No missing fields recorded for {name}."

    if "quality tier" in lower or "data quality" in lower:
        tier = town.get("data_quality_tier")
        return f"{name} data quality tier is '{tier}'."

    if "partial" in lower:
        tier = town.get("data_quality_tier")
        missing = town.get("missing_fields") or []
        if tier == "partial":
            return (
                f"{name} has partial data quality tier because fields are missing: "
                f"{', '.join(missing) if missing else 'unspecified fields'}."
            )
        return f"{name} is not marked partial (tier='{tier}')."

    if "affordability score" in lower:
        score = town.get("affordability_score")
        if score is not None:
            return f"{name} affordability score is {score}/10 (percentile within dataset)."
        return f"Affordability score is unavailable for {name}."

    if "commute" in lower or "how far" in lower or "distance" in lower:
        minutes = town.get("drive_minutes_to_boston")
        miles = town.get("drive_distance_miles_to_boston")
        if minutes is not None:
            return (
                f"{name} is {miles or 'n/a'} miles from South Station, Boston "
                f"({minutes} minute drive commute according to suburbs.json)."
            )
        return f"Commute data is unavailable for {name}."

    if "expensive" in lower or "how expensive" in lower:
        price = town.get("latest_home_price")
        if price is not None:
            return f"{name} latest median home price is {_format_price(price)} in the dataset."
        return f"Housing price data is unavailable for {name}."

    if "full-data" in lower or "partial-data" in lower or "partial data" in lower or "full data" in lower:
        tier = town.get("data_quality_tier")
        if tier == "full":
            return f"Yes, {name} is a full-data town (tier='full')."
        if tier == "partial":
            missing = town.get("missing_fields") or []
            return f"{name} is partial-data (tier='partial'). Missing: {', '.join(missing) if missing else 'unspecified'}."
        return f"{name} data quality tier is '{tier}'."

    if "basic stats" in lower or "commute data" in lower:
        return _default_town_summary(town)

    if "crime" in lower or "safety" in lower:
        rate = town.get("crime_rate_per_1000")
        score = town.get("safety_score")
        if rate is not None:
            return f"{name} has a crime rate of {rate} per 1,000 residents (safety score {score}/10)."
        return f"Crime data is unavailable for {name}."

    if "price" in lower or "afford" in lower or "$" in lower:
        price = town.get("latest_home_price")
        year = town.get("home_price_year")
        if price is not None:
            suffix = f" ({year} data)" if year else ""
            return f"{name} latest median home price is {_format_price(price)}{suffix}."
        return f"Housing price data is unavailable for {name}."

    if "school" in lower:
        score = town.get("school_score")
        if score is not None:
            return f"{name} has a school score of {score}/10 (percentile within dataset)."
        return f"School score data is unavailable for {name}."

    if "population" in lower:
        pop = town.get("population")
        if pop is not None:
            return f"{name} population is {int(pop):,}."
        return f"Population data is unavailable for {name}."

    return _default_town_summary(town)


def _build_compare_narrative(comparison: dict[str, Any]) -> str:
    if comparison.get("error"):
        return str(comparison["error"])

    a = comparison.get("town_a") or {}
    b = comparison.get("town_b") or {}
    name_a = a.get("name", "Town A")
    name_b = b.get("name", "Town B")

    def line(label: str, key: str, *, suffix: str = "") -> str:
        va = a.get(key)
        vb = b.get(key)
        if va is None and vb is None:
            return f"{label}: unavailable for both"
        return f"{label}: {name_a} {va}{suffix} vs {name_b} {vb}{suffix}"

    lines = [
        f"Comparison: {name_a} vs {name_b}.",
        line("Home price", "latest_home_price"),
        line("Commute to Boston (min)", "drive_minutes_to_boston"),
        line("Safety score", "safety_score", suffix="/10"),
        line("School score", "school_score", suffix="/10"),
        line("Crime rate per 1k", "crime_rate_per_1000"),
    ]
    return " ".join(lines)


def _build_multi_lookup_narrative(lookups: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for item in lookups:
        spec = item.get("spec") or {}
        town_name = spec.get("town", "")
        field = spec.get("field", "summary")
        lookup = item.get("lookup") or {}
        if not lookup.get("found"):
            msg = lookup.get("message") or f"{town_name} is not in the curated dataset."
            parts.append(msg)
            continue
        town = lookup.get("town") or {}
        name = town.get("name", town_name)
        parts.append(_lookup_field_snippet(name, town, field))
    return " ".join(parts)


def _format_table_cell(key: str, value: Any) -> str:
    if value is None:
        return "n/a"
    if key == "home_price":
        return _format_price(value)
    if key == "coastal":
        return "yes" if value else "no"
    return str(value)


def _build_multi_compare_narrative(comparison: dict[str, Any]) -> str:
    if comparison.get("error"):
        return str(comparison["error"])
    rows = comparison.get("comparison_table") or []
    cols = comparison.get("columns") or []
    errors = comparison.get("errors") or []
    if not rows:
        base = "No towns could be compared."
        if errors:
            base += " " + " ".join(errors)
        return base
    lines = [f"Comparison table for {len(rows)} towns (from suburbs.json):"]
    header = "Town | " + " | ".join(c["label"] for c in cols)
    lines.append(header)
    for row in rows:
        cells = [row.get("town", "?")]
        for col in cols:
            cells.append(_format_table_cell(col["key"], row.get(col["key"])))
        lines.append(" | ".join(cells))
    if errors:
        lines.append("Skipped: " + "; ".join(errors))
    lines.append(SCORE_DISCLAIMER)
    return "\n".join(lines)


def _static_response(
    query: str,
    *,
    route: QueryRoute,
    message: str,
) -> dict[str, Any]:
    return {
        "query": query,
        "preferences": None,
        "semantic_candidates": None,
        "top_matches": [],
        "comparison": None,
        "lookup": None,
        "tradeoff_warning": None,
        "final_recommendation": message,
        "score_disclaimer": SCORE_DISCLAIMER,
        "route_intent": route.intent,
        "orchestrated": True,
    }


def _apply_validation(
    response: dict[str, Any],
    *,
    query: str,
    route: QueryRoute,
) -> tuple[dict[str, Any], ValidationResult]:
    validation = validate_agent_response(response, query=query, route=route)
    response["validation"] = validation.model_dump()
    if not validation.valid:
        response["final_recommendation"] = (
            "I couldn't verify this answer against your constraints. "
            + "; ".join(validation.errors[:5])
        )
        if route.intent in (
            "recommend_structured",
            "recommend_semantic",
            "explain_ranking",
            "lookup_single_town",
            "compare_towns",
        ):
            response["top_matches"] = []
            response["tradeoff_warning"] = "Validation failed; ranked results withheld."
    return response, validation


async def _run_recommendation_pipeline(
    query: str,
    route: QueryRoute,
    *,
    save_searches: bool,
) -> dict[str, Any]:
    semantic_candidates: dict[str, Any] | None = None
    candidate_towns: list[str] | None = None

    if route.use_semantic:
        try:
            semantic_candidates = await run_semantic_town_search(query)
        except Exception as exc:
            logger.warning("Semantic search failed: %s", exc)
            semantic_candidates = {
                "query": query,
                "error": str(exc),
                "candidates": [],
                "candidate_town_names": [],
                "usage_note": "Semantic search unavailable; try a structured budget/region query.",
            }
        candidate_towns = semantic_candidates.get("candidate_town_names") or []
        if not candidate_towns:
            return {
                "query": query,
                "preferences": parse_preferences_tool(query),
                "semantic_candidates": semantic_candidates,
                "top_matches": [{
                    "no_matches": True,
                    "message": "Semantic search returned no candidate towns.",
                    "filters_applied": [],
                }],
                "comparison": None,
                "lookup": None,
                "tradeoff_warning": semantic_candidates.get("error"),
                "final_recommendation": (
                    "No semantic candidates were found for this query. "
                    "Try a more specific budget, region, or town name."
                ),
                "score_disclaimer": SCORE_DISCLAIMER,
                "route_intent": route.intent,
                "orchestrated": True,
            }

    preferences = parse_preferences_tool(query)
    top_matches = rank_suburbs_tool(
        user_prompt=query,
        preferences=preferences,
        candidate_towns=candidate_towns,
    )
    explained = explain_results_tool(
        user_prompt=query,
        results=top_matches,
        preferences=preferences,
    )

    if save_searches and "save_search_tool" in _effective_pipeline(route, save_searches=save_searches):
        save_search_tool(prompt=query, results=top_matches, preferences=preferences)

    if top_matches and top_matches[0].get("no_matches"):
        final = top_matches[0].get("message") or "No towns matched the hard filters for this query."
        filters = top_matches[0].get("filters_applied") or []
        if filters:
            final += f" Active filters: {', '.join(filters)}."
    else:
        final = explained.get("final_recommendation") or explained.get("summary")

    return {
        "query": query,
        "preferences": preferences,
        "semantic_candidates": semantic_candidates,
        "top_matches": top_matches,
        "comparison": None,
        "lookup": None,
        "tradeoff_warning": explained.get("tradeoff_warning"),
        "final_recommendation": final,
        "score_disclaimer": SCORE_DISCLAIMER,
        "route_intent": route.intent,
        "orchestrated": True,
    }


def _trust_gate_payload(
    query: str,
    route: QueryRoute,
    gate: TrustGateResult,
) -> dict[str, Any]:
    response = _static_response(query, route=route, message=gate.message)
    response["trust_gate"] = gate.gate_type
    response["validation"] = {"valid": True, "errors": [], "warnings": [f"trust_gate:{gate.gate_type}"]}
    return {
        "response": response,
        "route": route.model_dump(),
        "used_llm_fallback": False,
        "llm_classify_used": route.llm_fallback_used,
        "trust_gate": gate.gate_type,
    }


async def handle_query(
    prompt: str,
    *,
    save_searches: bool = True,
) -> dict[str, Any]:
    """Run the deterministic router → tools → validator pipeline."""
    query = prompt.strip()
    route = await classify_query_hybrid(query)
    trust_gate = evaluate_trust_gate(query, route)
    if trust_gate and trust_gate.blocks_pipeline:
        return _trust_gate_payload(query, route, trust_gate)

    if route.intent == "lookup_multi_town":
        lookup_results: list[dict[str, Any]] = []
        for spec in route.lookup_specs:
            town_name = spec.get("town", "")
            field = spec.get("field", "summary")
            lookup = get_town_facts(town_name)
            lookup_results.append({"spec": spec, "lookup": lookup, "field": field})
        final = _build_multi_lookup_narrative(lookup_results)
        response = {
            "query": query,
            "preferences": None,
            "semantic_candidates": None,
            "top_matches": [],
            "comparison": None,
            "lookup": {"multi": lookup_results},
            "tradeoff_warning": None,
            "final_recommendation": final,
            "score_disclaimer": SCORE_DISCLAIMER,
            "route_intent": route.intent,
            "orchestrated": True,
        }
        response, _ = _apply_validation(response, query=query, route=route)
        return {
            "response": response,
            "route": route.model_dump(),
            "used_llm_fallback": False,
            "llm_classify_used": route.llm_fallback_used,
        }

    if route.intent == "lookup_single_town":
        town_name = route.lookup_town or (route.named_towns[0] if route.named_towns else "")
        lookup = get_town_facts(town_name)
        if route.unsupported_field and route.requested_field:
            lookup = {
                **lookup,
                "unsupported_field": True,
                "requested_field": route.requested_field,
                "requested_field_category": route.requested_field_category,
            }
            final = build_unsupported_field_message(
                lookup.get("town", {}).get("name") or town_name,
                route.requested_field,
                in_dataset=bool(lookup.get("found")),
                category=route.requested_field_category or "lifestyle",
                query=query,
            )
        else:
            final = _build_lookup_narrative(query, lookup)
        response = {
            "query": query,
            "preferences": None,
            "semantic_candidates": None,
            "top_matches": [],
            "comparison": None,
            "lookup": lookup,
            "tradeoff_warning": None,
            "final_recommendation": final,
            "score_disclaimer": SCORE_DISCLAIMER,
            "route_intent": route.intent,
            "orchestrated": True,
        }
        response, _ = _apply_validation(response, query=query, route=route)
        return {
            "response": response,
            "route": route.model_dump(),
            "used_llm_fallback": False,
            "llm_classify_used": route.llm_fallback_used,
        }

    if route.intent == "compare_multi_town":
        towns = route.compare_towns or route.named_towns
        columns = route.compare_columns or None
        comparison = compare_suburbs_multi_tool(towns, columns=columns or None)
        response = {
            "query": query,
            "preferences": None,
            "semantic_candidates": None,
            "top_matches": [],
            "comparison": comparison,
            "lookup": None,
            "tradeoff_warning": None,
            "final_recommendation": _build_multi_compare_narrative(comparison),
            "score_disclaimer": SCORE_DISCLAIMER,
            "route_intent": route.intent,
            "orchestrated": True,
        }
        if save_searches and "save_search_tool" in _effective_pipeline(route, save_searches=save_searches):
            save_search_tool(prompt=query, results=[comparison], preferences=None)
        response, _ = _apply_validation(response, query=query, route=route)
        return {
            "response": response,
            "route": route.model_dump(),
            "used_llm_fallback": False,
            "llm_classify_used": route.llm_fallback_used,
        }

    if route.intent == "compare_towns":
        town_a = route.compare_town_a or (route.named_towns[0] if route.named_towns else "")
        town_b = route.compare_town_b or (route.named_towns[1] if len(route.named_towns) > 1 else "")
        comparison = compare_suburbs_tool(town_a, town_b)
        response = {
            "query": query,
            "preferences": None,
            "semantic_candidates": None,
            "top_matches": [],
            "comparison": comparison,
            "lookup": None,
            "tradeoff_warning": None,
            "final_recommendation": _build_compare_narrative(comparison),
            "score_disclaimer": SCORE_DISCLAIMER,
            "route_intent": route.intent,
            "orchestrated": True,
        }
        if save_searches and "save_search_tool" in _effective_pipeline(route, save_searches=save_searches):
            save_search_tool(prompt=query, results=[comparison], preferences=None)
        response, _ = _apply_validation(response, query=query, route=route)
        return {
            "response": response,
            "route": route.model_dump(),
            "used_llm_fallback": False,
            "llm_classify_used": route.llm_fallback_used,
        }

    if route.intent in ("recommend_structured", "recommend_semantic", "explain_ranking"):
        response = await _run_recommendation_pipeline(query, route, save_searches=save_searches)
        if trust_gate and not trust_gate.blocks_pipeline:
            response["trust_warning"] = trust_gate.message
            response["final_recommendation"] = f"{trust_gate.message} {response.get('final_recommendation', '')}".strip()
        response, _ = _apply_validation(response, query=query, route=route)
        return {
            "response": response,
            "route": route.model_dump(),
            "used_llm_fallback": False,
            "llm_classify_used": route.llm_fallback_used,
        }

    if route.intent == "data_limit_question":
        message = route.message or (
            "Live listing feeds are not available. "
            "SuburbScout uses curated local dataset snapshots in suburbs.json."
        )
        response = _static_response(query, route=route, message=message)
        response, _ = _apply_validation(response, query=query, route=route)
        return {
            "response": response,
            "route": route.model_dump(),
            "used_llm_fallback": False,
            "llm_classify_used": route.llm_fallback_used,
        }

    if route.intent == "needs_clarification":
        message = route.message or "Please share your budget, school/safety priorities, or towns to compare."
        response = _static_response(query, route=route, message=message)
        response, _ = _apply_validation(response, query=query, route=route)
        return {
            "response": response,
            "route": route.model_dump(),
            "used_llm_fallback": False,
            "llm_classify_used": route.llm_fallback_used,
        }

    message = route.message or (
        "I can help with Massachusetts Boston-area suburb lookup, comparison, and recommendations "
        "using the curated 200-town dataset."
    )
    response = _static_response(query, route=route, message=message)
    response, _ = _apply_validation(response, query=query, route=route)
    response["used_llm_fallback_recommended"] = True
    return {
        "response": response,
        "route": route.model_dump(),
        "used_llm_fallback": True,
        "llm_classify_used": route.llm_fallback_used,
    }
