"""Trust gates — block silent-wrong answers before tool pipelines run."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.commute_destination import (
    CommuteDestinationResult,
    build_commute_destination_limitation,
    detect_commute_destination,
    is_non_boston_destination_query,
)
from app.constraint_parser import parse_constraints
from app.entity_extractor import ExtractedEntities, extract_entities
from app.lookup_schema import AVAILABLE_FIELDS_BLURB, extract_unsupported_attribute
from app.query_patterns import (
    MAX_MULTI_COMPARE_TOWNS,
    MAX_MULTI_LOOKUP_SPECS,
    build_too_many_compare_message,
    build_too_many_lookup_message,
)
from app.query_router import QueryRoute


@dataclass(frozen=True)
class TrustGateResult:
    """When set, orchestrator should return message instead of running tools."""

    gate_type: str
    message: str
    blocks_pipeline: bool = True


_SUPPORTED_RANK_SIGNALS = (
    "budget_max",
    "max_commute_minutes",
    "min_commute_minutes",
    "requires_coastal",
    "region_preference",
    "region_key",
    "county_preference",
    "safer_than_town",
    "cheaper_than_town",
    "quieter_than_town",
    "similar_to_town",
    "candidate_towns",
)


def _has_supported_rank_constraints(query: str) -> bool:
    prefs = parse_constraints(query)
    if prefs.budget_max is not None:
        return True
    if prefs.max_commute_minutes is not None or prefs.min_commute_minutes is not None:
        return True
    if prefs.requires_coastal:
        return True
    if prefs.region_preference or prefs.region_key or prefs.county_preference:
        return True
    if prefs.safer_than_town or prefs.cheaper_than_town or prefs.quieter_than_town:
        return True
    if prefs.similar_to_town:
        return True
    if prefs.candidate_towns:
        return True
    if re.search(r"\b(?:rank|recommend|find|show|top|best|list)\b", query, re.I):
        if re.search(r"\b(?:school|safety|crime|price|afford|coastal|budget|under \$|minutes)\b", query, re.I):
            return True
    return False


def _compare_field_is_unsupported(query: str) -> bool:
    """True when compare asks about a field outside stored schema."""
    lower = query.lower()
    if extract_unsupported_attribute(query):
        return True
    unsupported_compare_markers = (
        r"\b(?:more|less)\s+walkable\b",
        r"\bwhich is more walkable\b",
        r"\bwalkability\b",
        r"\bmore diverse\b",
        r"\bmost diverse\b",
        r"\bmbta\b",
        r"\btransit\b",
        r"\bwalkable\b",
    )
    return any(re.search(p, lower) for p in unsupported_compare_markers)


def build_unsupported_compare_message(
    town_a: str,
    town_b: str,
    requested_field: str,
    *,
    category: str = "lifestyle",
) -> str:
    if category == "demographics":
        core = (
            f"this dataset does not include demographic composition fields, "
            f"so I cannot compare {town_a} and {town_b} on {requested_field}. "
            f"I should not guess. I can compare stored fields: home price, commute to Boston, "
            f"safety, schools, coastal status, and data completeness."
        )
    else:
        core = (
            f"this dataset does not include a {requested_field} field, "
            f"so I cannot compare {town_a} and {town_b} on that attribute. "
            f"I can compare stored fields: home price, commute to Boston, safety, schools, "
            f"coastal status, and data completeness."
        )
    return f"{town_a} and {town_b} are in the dataset, but {core}"


def build_unsupported_rank_message(requested_field: str, *, category: str = "lifestyle") -> str:
    if category == "demographics":
        return (
            f"This dataset does not include demographic composition fields, "
            f"so I cannot rank towns by {requested_field}. "
            f"I should not guess. Try supported criteria like budget, Boston commute, "
            f"schools, safety, or coastal filters."
        )
    return (
        f"This dataset does not include a {requested_field} field, "
        f"so I cannot rank towns using that criterion. "
        f"Try supported filters: budget, Boston/South Station commute, schools, safety, coastal, or region."
    )


def build_multi_compare_message(towns: list[str]) -> str:
    """Legacy two-town-only message when 3+ towns hit compare without multi-table routing."""
    names = ", ".join(towns[:4])
    if len(towns) > 4:
        names += ", ..."
    return (
        f"I can compare two towns at a time on stored fields ({AVAILABLE_FIELDS_BLURB}), "
        f"or up to {MAX_MULTI_COMPARE_TOWNS} in a comparison table. "
        f"You named {len(towns)} towns ({names}). "
        f"Please ask for a table compare or pick two towns, e.g. '{towns[0]} vs {towns[1]} on commute'."
    )


def evaluate_trust_gate(
    query: str,
    route: QueryRoute,
    *,
    entities: ExtractedEntities | None = None,
) -> TrustGateResult | None:
    """Return a trust gate when pipeline would silently use wrong data."""
    entities = entities or extract_entities(query)
    dest = detect_commute_destination(query, entities)
    lower = query.lower()

    if route.intent == "lookup_multi_town" and len(route.lookup_specs) > MAX_MULTI_LOOKUP_SPECS:
        return TrustGateResult(
            gate_type="too_many_lookups",
            message=build_too_many_lookup_message(len(route.lookup_specs)),
            blocks_pipeline=True,
        )

    if len(entities.valid_towns) > MAX_MULTI_COMPARE_TOWNS and re.search(
        r"\b(?:compare|versus|vs\.?)\b", lower
    ):
        return TrustGateResult(
            gate_type="too_many_compare",
            message=build_too_many_compare_message(len(entities.valid_towns)),
            blocks_pipeline=True,
        )

    if (
        len(entities.valid_towns) > 2
        and re.search(r"\b(?:compare|versus|vs\.?)\b", lower)
        and route.intent not in ("compare_multi_town", "lookup_multi_town")
    ):
        return TrustGateResult(
            gate_type="multi_compare",
            message=build_multi_compare_message(entities.valid_towns),
            blocks_pipeline=True,
        )

    # --- Compare gates ---
    if route.intent in ("compare_towns", "compare_multi_town"):
        if _compare_field_is_unsupported(query):
            match = extract_unsupported_attribute(query)
            field = match.label if match else "that attribute"
            category = match.category if match else "lifestyle"
            a = route.compare_town_a or (entities.valid_towns[0] if entities.valid_towns else "Town A")
            b = route.compare_town_b or (entities.valid_towns[1] if len(entities.valid_towns) > 1 else "Town B")
            return TrustGateResult(
                gate_type="unsupported_compare",
                message=build_unsupported_compare_message(a, b, field, category=category),
                blocks_pipeline=True,
            )
        return None

    # --- Lookup: wrong destination (e.g. Shrewsbury from Worcester) ---
    if route.intent == "lookup_single_town" and not route.unsupported_field:
        lower = query.lower()
        if is_non_boston_destination_query(query, entities) and re.search(
            r"\b(?:how far|distance|commute|drive|from .+ to|to .+ from)\b",
            lower,
        ):
            if not dest.data_available:
                return TrustGateResult(
                    gate_type="commute_destination_lookup",
                    message=build_commute_destination_limitation(dest, context="lookup"),
                    blocks_pipeline=True,
                )

    # --- Recommend / semantic rank gates ---
    if route.intent in ("recommend_structured", "recommend_semantic"):
        unsupported = extract_unsupported_attribute(query)
        if unsupported and not _has_supported_rank_constraints(query):
            return TrustGateResult(
                gate_type="unsupported_rank",
                message=build_unsupported_rank_message(
                    unsupported.label,
                    category=unsupported.category,
                ),
                blocks_pipeline=True,
            )

        if is_non_boston_destination_query(query, entities) and not dest.data_available:
            if re.search(
                r"\b(?:within|under|less than|minutes|commute|work in|work at|near)\b",
                query.lower(),
            ):
                return TrustGateResult(
                    gate_type="commute_destination_rank",
                    message=build_commute_destination_limitation(dest, context="recommend"),
                    blocks_pipeline=True,
                )

        if unsupported and _has_supported_rank_constraints(query):
            return TrustGateResult(
                gate_type="unsupported_rank_partial",
                message=(
                    f"Note: this dataset does not include a {unsupported.label} field, "
                    f"so ranking uses only supported constraints (budget, Boston commute, schools, safety, etc.), "
                    f"not {unsupported.label}."
                ),
                blocks_pipeline=False,
            )

    return None
