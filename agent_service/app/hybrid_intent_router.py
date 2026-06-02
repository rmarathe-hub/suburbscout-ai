"""Phase 1.5 — Python-first routing with optional LLM classify-only fallback."""

from __future__ import annotations

import logging
import re

from app import config
from app.entity_extractor import extract_entities, is_junk_town_candidate
from app.intent_classifier import ClassifiedIntent, classify_user_intent
from app.llm_intent_classifier import classify_intent_with_llm, llm_fallback_available
from app.llm_intent_validator import validate_llm_classification
from app.query_router import (
    EXPLAIN_RE,
    UNSUPPORTED_PHRASES,
    QueryRoute,
    _pipeline_for_intent,
    classify_query_python,
    route_from_classified,
)

logger = logging.getLogger(__name__)


def should_use_llm_intent_fallback(classified: ClassifiedIntent) -> bool:
    if not llm_fallback_available():
        return False
    if classified.intent == "unsupported":
        return True
    if classified.confidence < config.LLM_INTENT_CONFIDENCE_THRESHOLD:
        return True
    if classified.intent == "lookup_single_town" and classified.lookup_town:
        if is_junk_town_candidate(classified.lookup_town):
            return True
    return False


def _repair_after_llm(
    query: str,
    validated: ClassifiedIntent,
    entities,
) -> ClassifiedIntent:
    """Prefer Python structural signals when LLM returns unsupported incorrectly."""
    from app.constraint_parser import parse_constraints
    from app.intent_classifier import (
        _has_membership_relation,
        _has_recommendation_ask,
        _is_lookup_query,
        _membership_intent,
        _recommend_intent,
    )

    lower = query.lower()
    if validated.intent != "unsupported":
        return validated

    from app.lookup_schema import detect_unknown_field_lookup

    unknown_field = detect_unknown_field_lookup(query, entities)
    if unknown_field:
        from app.intent_classifier import _unsupported_field_lookup_intent

        town, match = unknown_field
        return _unsupported_field_lookup_intent(
            town,
            match.label,
            entities=entities,
            category=match.category,
            confidence=0.88,
            reason="repair: unsupported attribute lookup after llm unsupported",
        )

    if _has_membership_relation(lower) or re.search(
        r"\b(?:searchable|recognized|valid result|accepted alias|canonical spelling|"
        r"200[- ]town load|usable in this app)\b",
        lower,
    ):
        from app.intent_classifier import _membership_town

        town = _membership_town(query, entities)
        return _membership_intent(
            town,
            entities=entities,
            confidence=0.88,
            reason="repair: membership after llm unsupported",
        )

    if _is_lookup_query(query, entities):
        from app.intent_classifier import _infer_lookup_field, primary_town

        town = primary_town(entities)
        if town:
            from app.intent_classifier import _lookup_intent

            return _lookup_intent(
                town,
                _infer_lookup_field(lower),
                entities=entities,
                confidence=0.88,
                reason="repair: lookup after llm unsupported",
            )

    if _has_recommendation_ask(query):
        constraints = parse_constraints(query)
        semantic = bool(
            re.search(r"\b(?:feel|vibe|ish|style|energy|similar|like)\b", lower)
        )
        return _recommend_intent(
            entities=entities,
            semantic=semantic,
            confidence=0.88,
            reason="repair: recommend after llm unsupported",
        )

    if re.search(r"\b(?:towns|places|suburbs|options)\b", lower) and re.search(
        r"\b(?:commute|drive time).*(?:under|within|over|between|capped|at least|or more|sacrifice)\b",
        lower,
    ):
        return _recommend_intent(
            entities=entities,
            semantic=False,
            confidence=0.88,
            reason="repair: commute list after llm unsupported",
        )

    return validated


def _adjust_python_confidence(classified: ClassifiedIntent, query: str) -> ClassifiedIntent:
    lower = query.lower()
    if classified.intent == "unsupported":
        classified.confidence = min(classified.confidence, 0.4)
        return classified
    if classified.intent == "lookup_single_town":
        if classified.lookup_town and is_junk_town_candidate(classified.lookup_town):
            classified.confidence = 0.55
        elif re.search(r"\bdrive time to boston\b", lower) and not re.search(
            r"\b(?:towns|places|suburbs)\b", lower
        ):
            classified.confidence = min(classified.confidence, 0.6)
    if classified.intent == "dataset_membership" and not classified.lookup_town:
        classified.confidence = min(classified.confidence, 0.75)
    return classified


async def classify_query_hybrid(query: str) -> QueryRoute:
    """Python classify first; LLM classify-only when confidence is low."""
    text = query.strip()
    lower = text.lower()
    if not text:
        return QueryRoute(
            intent="unsupported",
            confidence=0.0,
            query=text,
            message="Empty query.",
            pipeline=[],
            classification_source="python",
        )

    if EXPLAIN_RE.search(text):
        from app.constraint_parser import extract_town_mentions

        known, unknown = extract_town_mentions(text)
        return QueryRoute(
            intent="explain_ranking",
            confidence=0.9,
            query=text,
            named_towns=known,
            unknown_towns=unknown,
            pipeline=_pipeline_for_intent("explain_ranking", use_semantic=False),
            classification_source="python",
        )

    if any(p in lower for p in UNSUPPORTED_PHRASES):
        return QueryRoute(
            intent="unsupported",
            confidence=0.95,
            query=text,
            message="This request is outside suburb recommendation scope.",
            pipeline=[],
            classification_source="python",
        )

    python_raw = classify_user_intent(text)
    python_raw.python_intent = python_raw.intent
    python_raw.python_confidence = python_raw.confidence
    python_raw.classification_source = "python"

    python = _adjust_python_confidence(python_raw.model_copy(deep=True), text)
    python.python_intent = python_raw.intent
    python.python_confidence = python_raw.confidence

    if not should_use_llm_intent_fallback(python):
        return route_from_classified(
            text, python, llm_fallback_used=False, python_snapshot=python_raw
        )

    try:
        entities = extract_entities(text)
        llm_payload = await classify_intent_with_llm(
            text, entities=entities, python_hint=python_raw
        )
        validated = validate_llm_classification(llm_payload, text, entities=entities)
        if validated:
            validated = _repair_after_llm(text, validated, entities)
            validated.python_intent = python_raw.intent
            validated.python_confidence = python_raw.confidence
            validated.classification_source = "llm"
            logger.info(
                "LLM intent fallback: %s -> %s (conf=%.2f)",
                python_raw.intent,
                validated.intent,
                validated.confidence,
            )
            return route_from_classified(
                text,
                validated,
                llm_fallback_used=True,
                python_snapshot=python_raw,
            )
        logger.warning("LLM classification failed validation")
    except Exception as exc:
        logger.warning("LLM intent fallback unavailable: %s", exc)

    return route_from_classified(
        text, python, llm_fallback_used=False, python_snapshot=python_raw
    )


def classify_query(query: str) -> QueryRoute:
    """Sync entry — Python-only (no LLM)."""
    return classify_query_python(query)
