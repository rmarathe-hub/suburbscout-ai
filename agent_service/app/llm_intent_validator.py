"""Validate LLM classify-only JSON and map to ClassifiedIntent."""

from __future__ import annotations

import logging
from typing import Any

from app.constraint_parser import parse_constraints
from app.entity_extractor import ExtractedEntities, extract_entities, is_junk_town_candidate
from app.intent_classifier import ClassifiedIntent, clean_town_label
from app.llm_intent_classifier import LlmIntentPayload
from app.town_normalizer import resolve_town_in_dataset

logger = logging.getLogger(__name__)

OUT_OF_SCOPE_TOWN_KEYS = frozenset({
    "providence", "nashua", "springfield", "amherst", "brooklyn",
})


def _dataset_town_names() -> list[str]:
    from app.entity_extractor import _dataset_towns

    return list(_dataset_towns())


def _resolve_town_list(raw_towns: list[str]) -> tuple[list[str], list[str]]:
    names = _dataset_town_names()
    valid: list[str] = []
    unknown: list[str] = []
    for raw in raw_towns:
        cleaned = clean_town_label(raw)
        if not cleaned or is_junk_town_candidate(cleaned):
            continue
        resolved = resolve_town_in_dataset(cleaned, names)
        if resolved:
            if resolved not in valid:
                valid.append(resolved)
        elif cleaned not in unknown:
            unknown.append(cleaned)
    return valid, unknown


def _constraints_dict(query: str, llm_constraints: dict[str, Any]) -> dict[str, object]:
    parsed = parse_constraints(query)
    merged: dict[str, object] = {}
    for key, value in parsed.model_dump(exclude_none=True).items():
        if value is not None:
            merged[key] = value
    for key, value in (llm_constraints or {}).items():
        if value is not None and key not in merged:
            merged[key] = value
    return merged


def validate_llm_classification(
    payload: LlmIntentPayload,
    query: str,
    *,
    entities: ExtractedEntities | None = None,
) -> ClassifiedIntent | None:
    """Return ClassifiedIntent when LLM output passes validation; else None."""
    entities = entities or extract_entities(query)
    valid, unknown = _resolve_town_list(payload.towns)
    if not valid and entities.valid_towns:
        valid = list(entities.valid_towns)
    if not unknown and entities.unknown_town_candidates:
        unknown = list(entities.unknown_town_candidates)

    intent = payload.intent
    field = payload.field
    constraints = _constraints_dict(query, payload.constraints)

    if intent == "compare_towns":
        pair = entities.compare_pair
        if pair and len(pair) == 2:
            a, b = pair[0], pair[1]
        elif len(valid) >= 2:
            a, b = valid[0], valid[1]
        else:
            logger.info("LLM compare rejected: fewer than 2 towns")
            return None
        return ClassifiedIntent(
            intent="compare_towns",
            confidence=min(0.92, float(payload.confidence)),
            compare_town_a=a,
            compare_town_b=b,
            field=field,
            named_towns=valid,
            unknown_towns=unknown,
            constraints=constraints,
            reason=f"llm: {payload.reason}",
            classification_source="llm",
        )

    if intent in ("lookup_single_town", "dataset_membership"):
        town = valid[0] if valid else (unknown[0] if unknown else None)
        if not town and intent == "lookup_single_town":
            if entities.compare_pair:
                return None
            logger.info("LLM lookup rejected: no town")
            return None
        lookup_field = field or ("dataset" if intent == "dataset_membership" else "summary")
        mapped_intent = "dataset_membership" if intent == "dataset_membership" else "lookup_single_town"
        return ClassifiedIntent(
            intent=mapped_intent,
            confidence=min(0.92, float(payload.confidence)),
            lookup_town=clean_town_label(town) if town else None,
            lookup_field=lookup_field,
            field=lookup_field,
            named_towns=valid,
            unknown_towns=unknown,
            constraints=constraints,
            reason=f"llm: {payload.reason}",
            classification_source="llm",
        )

    if intent == "refuse_out_of_scope":
        return ClassifiedIntent(
            intent="refuse_out_of_scope",
            confidence=min(0.95, float(payload.confidence)),
            named_towns=valid,
            unknown_towns=unknown,
            message="That request is outside the curated Boston-area 200-town dataset.",
            reason=f"llm: {payload.reason}",
            classification_source="llm",
        )

    if intent == "recommend_semantic":
        return ClassifiedIntent(
            intent="recommend_semantic",
            confidence=min(0.9, float(payload.confidence)),
            named_towns=valid,
            unknown_towns=unknown,
            constraints=constraints,
            reason=f"llm: {payload.reason}",
            classification_source="llm",
        )

    if intent == "recommend_structured":
        return ClassifiedIntent(
            intent="recommend_structured",
            confidence=min(0.9, float(payload.confidence)),
            named_towns=valid,
            unknown_towns=unknown,
            constraints=constraints,
            reason=f"llm: {payload.reason}",
            classification_source="llm",
        )

    if intent == "unsupported":
        return ClassifiedIntent(
            intent="unsupported",
            confidence=min(0.5, float(payload.confidence)),
            named_towns=valid,
            unknown_towns=unknown,
            reason=f"llm: {payload.reason}",
            classification_source="llm",
        )

    return None
