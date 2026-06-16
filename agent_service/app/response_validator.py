"""Validate agent and tool responses against hard constraints (Phase 1.1)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

from app.constraint_parser import parse_constraints
from app.intent_classifier import classify_user_intent, route_intent_matches
from app.intent_rules import infer_strict_intent
from app.query_router import QueryRoute, classify_query
from app.ranking import load_suburbs
from app.schemas import Preferences
from app.town_normalizer import canonical_town_name, normalize_key, towns_equivalent


class ValidationResult(BaseModel):
    """Outcome of response validation."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    def merge(self, other: ValidationResult) -> ValidationResult:
        return ValidationResult(
            valid=self.valid and other.valid,
            errors=[*self.errors, *other.errors],
            warnings=[*self.warnings, *other.warnings],
        )


@lru_cache(maxsize=1)
def _known_town_keys() -> frozenset[str]:
    return frozenset(normalize_key(s["name"]) for s in load_suburbs())


def _town_key(name: str | None) -> str:
    return normalize_key(canonical_town_name(name or ""))


def _coerce_preferences(preferences: Preferences | dict[str, Any] | None, query: str) -> Preferences:
    if isinstance(preferences, Preferences):
        return preferences
    if isinstance(preferences, dict) and preferences:
        return Preferences(**preferences)
    return parse_constraints(query)


def _match_data(row: dict[str, Any]) -> dict[str, Any]:
    if row.get("no_matches"):
        return {}
    data = row.get("data")
    if isinstance(data, dict):
        return data
    return row


def _match_name(row: dict[str, Any]) -> str | None:
    if row.get("no_matches"):
        return None
    name = row.get("name")
    return str(name) if name else None


def validate_town_in_dataset(name: str | None) -> ValidationResult:
    if not name:
        return ValidationResult(valid=True)
    key = _town_key(name)
    if key not in _known_town_keys():
        return ValidationResult(
            valid=False,
            errors=[f"Town '{name}' is not in the 200-town suburbs.json dataset."],
        )
    return ValidationResult(valid=True)


def validate_ranked_results(
    results: list[dict[str, Any]],
    preferences: Preferences | dict[str, Any] | None,
    *,
    query: str = "",
) -> ValidationResult:
    """Validate rank_suburbs_tool / top_matches rows against parsed constraints."""
    prefs = _coerce_preferences(preferences, query)
    errors: list[str] = []
    warnings: list[str] = []

    if not results:
        return ValidationResult(valid=True, warnings=["No ranked results to validate."])

    if len(results) == 1 and results[0].get("no_matches"):
        return ValidationResult(valid=True, warnings=[results[0].get("message") or "No matches."])

    for row in results:
        name = _match_name(row)
        if not name:
            continue

        dataset_check = validate_town_in_dataset(name)
        if not dataset_check.valid:
            errors.extend(dataset_check.errors)
            continue

        data = _match_data(row)
        price = data.get("latest_home_price", row.get("latest_home_price"))
        minutes = data.get("drive_minutes_to_boston", row.get("drive_minutes_to_boston"))
        if prefs.commute_destination_town:
            minutes = data.get("drive_minutes_to_destination", row.get("drive_minutes_to_destination"))
        county = data.get("county", row.get("county"))
        region = data.get("region", row.get("region"))
        is_coastal = data.get("is_coastal", row.get("is_coastal"))

        if prefs.budget_max is not None and prefs.require_housing_for_budget:
            if price is None:
                errors.append(f"{name}: missing price for budget query (max ${prefs.budget_max:,}).")
            elif float(price) > prefs.budget_max:
                errors.append(f"{name}: price ${float(price):,.0f} exceeds budget ${prefs.budget_max:,}.")

        if prefs.requires_coastal and not is_coastal:
            errors.append(f"{name}: marked non-coastal but coastal filter was requested.")

        if prefs.county_preference and (county or "").lower() != prefs.county_preference.lower():
            errors.append(
                f"{name}: county '{county}' does not match requested {prefs.county_preference}."
            )

        if prefs.region_preference and region != prefs.region_preference:
            errors.append(
                f"{name}: region '{region}' does not match requested {prefs.region_preference}."
            )

        if prefs.max_commute_minutes is not None:
            if minutes is None:
                errors.append(f"{name}: missing commute minutes for max {prefs.max_commute_minutes}.")
            elif float(minutes) > prefs.max_commute_minutes:
                errors.append(
                    f"{name}: commute {minutes} min exceeds max {prefs.max_commute_minutes} min."
                )

        if prefs.min_commute_minutes is not None:
            if minutes is None:
                errors.append(f"{name}: missing commute minutes for min {prefs.min_commute_minutes}.")
            elif float(minutes) < prefs.min_commute_minutes:
                errors.append(
                    f"{name}: commute {minutes} min below min {prefs.min_commute_minutes} min."
                )

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)


def validate_lookup_response(
    lookup: dict[str, Any],
    *,
    requested_town: str | None = None,
) -> ValidationResult:
    """Validate get_town_facts_tool output."""
    errors: list[str] = []
    warnings: list[str] = []
    queried = requested_town or lookup.get("queried_name")
    found = lookup.get("found")
    town = lookup.get("town") or {}

    if found:
        town_name = town.get("name")
        if not town_name:
            errors.append("Lookup marked found=true but town payload is missing.")
        else:
            if queried and _town_key(town_name) != _town_key(queried):
                errors.append(
                    f"Lookup substituted town '{town_name}' for requested '{queried}'."
                )
            dataset_check = validate_town_in_dataset(town_name)
            if not dataset_check.valid:
                errors.extend(dataset_check.errors)
    else:
        if town:
            errors.append("Lookup marked found=false but town payload is present.")
        if not lookup.get("message"):
            warnings.append("Lookup not found without explanatory message.")

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)


def validate_comparison(
    comparison: dict[str, Any] | None,
    *,
    town_a: str | None = None,
    town_b: str | None = None,
) -> ValidationResult:
    """Validate compare_suburbs_tool / comparison object."""
    if not comparison:
        return ValidationResult(valid=False, errors=["Missing comparison object."])
    if comparison.get("error"):
        msg = str(comparison["error"])
        requested = [t for t in (town_a, town_b) if t]
        if requested and any(t.lower() in msg.lower() for t in requested):
            return ValidationResult(valid=True, warnings=[msg])
        return ValidationResult(valid=False, errors=[msg])

    errors: list[str] = []
    a = (comparison.get("town_a") or {}).get("name")
    b = (comparison.get("town_b") or {}).get("name")
    if not a or not b:
        errors.append("Comparison missing town_a or town_b.")
    else:
        for name in (a, b):
            check = validate_town_in_dataset(name)
            if not check.valid:
                errors.extend(check.errors)

    if town_a and a and not towns_equivalent(town_a, a):
        errors.append(f"Comparison town_a expected '{town_a}', got '{a}'.")
    if town_b and b and not towns_equivalent(town_b, b):
        errors.append(f"Comparison town_b expected '{town_b}', got '{b}'.")

    return ValidationResult(valid=not errors, errors=errors)


def validate_lookup_mentions(response_text: str, requested_town: str) -> ValidationResult:
    """Ensure final text mentions the requested town for direct lookup answers."""
    if not requested_town:
        return ValidationResult(valid=True)
    blob = response_text.lower()
    if canonical_town_name(requested_town).lower() not in blob and normalize_key(requested_town) not in blob:
        return ValidationResult(
            valid=False,
            errors=[f"Response text does not mention requested town '{requested_town}'."],
        )
    return ValidationResult(valid=True)


def _ranked_names(response: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for row in response.get("top_matches") or []:
        if isinstance(row, dict) and row.get("name") and not row.get("no_matches"):
            names.append(str(row["name"]))
    return names


def validate_budget_parse(query: str, preferences: Preferences | dict[str, Any] | None) -> ValidationResult:
    """Fail when money parsing is obviously wrong for the query."""
    prefs = _coerce_preferences(preferences, query)
    lower = query.lower()
    errors: list[str] = []
    if prefs.budget_max is not None:
        if ("million" in lower or "1m" in lower or "one million" in lower) and prefs.budget_max < 100_000:
            errors.append(
                f"Budget parsed as ${prefs.budget_max:,} but query mentions million "
                f"(expected ~$1,000,000)."
            )
    return ValidationResult(valid=not errors, errors=errors)


def validate_strict_intent_alignment(
    query: str,
    response: dict[str, Any],
    *,
    route: QueryRoute,
) -> ValidationResult:
    """Phase 1.2/1.3: fail when response does not match what the user actually asked."""
    classified = classify_user_intent(query)
    errors: list[str] = []
    warnings: list[str] = []

    route_authoritative = bool(
        route.llm_fallback_used or route.classification_source == "llm"
    )
    effective_intent = route.intent if route_authoritative else classified.intent

    if not route_intent_matches(classified, route.intent):
        if route_authoritative:
            warnings.append(
                f"Python classified '{classified.intent}' but route '{route.intent}' "
                f"is authoritative ({route.classification_source})."
            )
        elif route.intent == "lookup_single_town" and response.get("lookup") and not response.get("top_matches"):
            warnings.append(
                f"Classified intent '{classified.intent}' differs from route '{route.intent}' "
                f"but lookup payload is present."
            )
        elif route.intent in ("compare_towns", "compare_multi_town") and response.get("comparison") and not response.get("top_matches"):
            warnings.append(
                f"Classified intent '{classified.intent}' differs from route '{route.intent}' "
                f"but comparison payload is present."
            )
        elif route.intent == "lookup_multi_town" and response.get("lookup") and not response.get("top_matches"):
            warnings.append(
                f"Classified intent '{classified.intent}' differs from route '{route.intent}' "
                f"but multi-lookup payload is present."
            )
        else:
            errors.append(
                f"Route intent '{route.intent}' does not match expected '{classified.intent}' for this query."
            )

    final = str(response.get("final_recommendation") or "")
    ranked = _ranked_names(response)

    lookup_intents = ("lookup_single_town", "lookup_multi_town", "dataset_membership")
    if effective_intent in lookup_intents or route.intent in ("lookup_single_town", "lookup_multi_town"):
        if ranked:
            errors.append(
                f"Lookup question returned ranked recommendations {ranked[:3]} instead of town facts."
            )
        if re.search(r"\bi recommend\b", final, re.IGNORECASE) and classified.lookup_town:
            if canonical_town_name(classified.lookup_town).lower() not in final.lower():
                errors.append(
                    f"Lookup answered with a recommendation that does not mention '{classified.lookup_town}'."
                )
        lookup_town = classified.lookup_town or route.lookup_town
        if lookup_town:
            mention = validate_lookup_mentions(
                json.dumps(response) + " " + final,
                lookup_town,
            )
            if not mention.valid:
                errors.extend(mention.errors)
        lookup = response.get("lookup")
        if lookup is None and lookup_town:
            warnings.append("Lookup response missing lookup payload.")

    if effective_intent == "compare_towns" or route.intent == "compare_towns":
        if ranked:
            errors.append("Comparison question returned ranked recommendations instead of a comparison.")
        if re.search(r"\bi recommend\b", final, re.IGNORECASE):
            errors.append("Comparison question returned a single-town recommendation.")
        comp = response.get("comparison")
        comp_check = validate_comparison(
            comp,
            town_a=classified.compare_town_a,
            town_b=classified.compare_town_b,
        )
        if not comp_check.valid:
            errors.extend(comp_check.errors)

    if effective_intent == "refuse_out_of_scope":
        if ranked:
            errors.append("Out-of-scope request returned ranked town recommendations.")

    if effective_intent in ("recommend_structured", "recommend_semantic"):
        prefs = _coerce_preferences(response.get("preferences"), query)
        if prefs.prefer_high_crime and ranked:
            # Top results should not all be ultra-safe suburbs when high-crime was requested
            top = (response.get("top_matches") or [None])[0]
            if isinstance(top, dict):
                data = _match_data(top)
                safety = data.get("safety_score")
                crime = data.get("crime_rate_per_1000")
                if safety is not None and float(safety) >= 9.0 and (crime or 0) < 5:
                    errors.append(
                        f"High-crime request but top match '{top.get('name')}' has very high safety "
                        f"(score {safety})."
                    )

    return ValidationResult(valid=not errors, errors=errors, warnings=warnings)


def validate_agent_response(
    response: dict[str, Any],
    *,
    query: str,
    route: QueryRoute | None = None,
) -> ValidationResult:
    """Validate a structured agent JSON response before returning to the user."""
    active_route = route or classify_query(query)
    prefs = _coerce_preferences(response.get("preferences"), query)
    result = ValidationResult(valid=True)

    strict_check = validate_strict_intent_alignment(query, response, route=active_route)
    result = result.merge(strict_check)
    result = result.merge(validate_budget_parse(query, response.get("preferences")))

    if active_route.intent in ("data_limit_question", "needs_clarification", "unsupported"):
        if not response.get("final_recommendation") and not response.get("message"):
            result = result.merge(
                ValidationResult(
                    valid=True,
                    warnings=["Non-recommendation intent without final_recommendation text."],
                )
            )
        return result

    if active_route.intent == "lookup_single_town":
        lookup_town = active_route.lookup_town or (prefs.named_towns or [None])[0]
        text_blob = json.dumps(response)
        if response.get("top_matches"):
            result = result.merge(
                ValidationResult(
                    valid=False,
                    errors=["Lookup query should not include ranked top_matches."],
                )
            )
        mention = validate_lookup_mentions(
            text_blob + " " + str(response.get("final_recommendation") or ""),
            lookup_town or "",
        )
        if lookup_town:
            result = result.merge(mention)
        return result

    if active_route.intent == "lookup_multi_town":
        if response.get("top_matches"):
            result = result.merge(
                ValidationResult(
                    valid=False,
                    errors=["Multi-lookup query should not include ranked top_matches."],
                )
            )
        return result

    if active_route.intent == "compare_towns":
        comp = response.get("comparison")
        result = result.merge(
            validate_comparison(
                comp,
                town_a=active_route.compare_town_a,
                town_b=active_route.compare_town_b,
            )
        )
        top = response.get("top_matches") or []
        if top:
            result = result.merge(
                ValidationResult(
                    valid=False,
                    errors=["Compare query should not include recommendation top_matches."],
                )
            )
        return result

    if active_route.intent == "compare_multi_town":
        comp = response.get("comparison") or {}
        if comp.get("error"):
            result = result.merge(
                ValidationResult(valid=False, errors=[str(comp["error"])])
            )
        elif not comp.get("comparison_table"):
            result = result.merge(
                ValidationResult(valid=False, errors=["Multi-compare missing comparison_table."])
            )
        top = response.get("top_matches") or []
        if top:
            result = result.merge(
                ValidationResult(
                    valid=False,
                    errors=["Multi-compare query should not include recommendation top_matches."],
                )
            )
        return result

    top_matches = response.get("top_matches") or []
    rank_check = validate_ranked_results(top_matches, prefs, query=query)
    result = result.merge(rank_check)

    if active_route.use_semantic and not response.get("semantic_candidates"):
        result = result.merge(
            ValidationResult(
                valid=True,
                warnings=["Semantic route without semantic_candidates in response."],
            )
        )

    return result
