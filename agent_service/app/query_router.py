"""Rule-based query intent router (Phase 1.1 / 1.3)."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from app.constraint_parser import extract_town_mentions
from app.entity_extractor import extract_entities, is_junk_town_candidate
from app.intent_classifier import classify_user_intent, clean_town_label

QueryIntent = Literal[
    "lookup_single_town",
    "lookup_multi_town",
    "compare_towns",
    "compare_multi_town",
    "recommend_structured",
    "recommend_semantic",
    "explain_ranking",
    "data_limit_question",
    "dataset_membership",
    "needs_clarification",
    "unsupported",
]

EXPLAIN_RE = re.compile(
    r"\bwhy\s+(?:did|is|was)\s+(.+?)\s+(?:beat|rank(?:ed)?\s+above|better\s+than|score\s+higher\s+than)\s+(.+?)(?:\?|$)",
    re.IGNORECASE,
)

# Re-export for backward compatibility
DATASET_MEMBERSHIP_RE = re.compile(
    r"\b(?:do you cover|is .+ included|do you have|do you include|is .+ in (?:your )?(?:the )?(?:town )?(?:dataset|list|data))\b",
    re.IGNORECASE,
)
LOOKUP_FACT_RE = re.compile(
    r"\b(?:commute|crime(?:\s+rate)?|price|school(?:\s+score)?s?|safety|population|distance|expensive)\s+(?:for|in|of)\s+([a-zA-Z][\w\s\-']+)",
    re.IGNORECASE,
)
FACT_LOOKUP_HINTS: tuple[str, ...] = (
    "commute", "crime", "price", "school", "safety", "population", "distance", "expensive",
)
WHAT_IS_FACT_RE = re.compile(
    r"\bwhat\s+is\s+(?:the\s+)?(?:commute|crime|price|school|safety)\s+(?:for|in|of)\s+([a-zA-Z][\w\s\-']+)",
    re.IGNORECASE,
)
FACTS_ABOUT_RE = re.compile(
    r"\b(?:facts about|tell me about|info on|information on)\s+([a-zA-Z][\w\s\-']+)",
    re.IGNORECASE,
)
WORK_IN_RE = re.compile(
    r"\b(?:i\s+)?work\s+(?:in|at)\s+([a-zA-Z][\w\s\-']+)",
    re.IGNORECASE,
)
LIVE_IN_RE = re.compile(
    r"\b(?:i\s+)?live\s+(?:in|at)\s+([a-zA-Z][\w\s\-']+)",
    re.IGNORECASE,
)
DATA_LIMIT_PHRASES: tuple[str, ...] = (
    "zillow", "redfin", "realtor.com", "live price", "live data",
    "real-time", "realtime", "today's price", "todays price",
    "current market", "right now", "mls listing",
)
UNSUPPORTED_PHRASES: tuple[str, ...] = (
    "recipe", "weather in miami", "who won the super bowl",
    "write me a poem", "python code", "stock price",
)


class QueryRoute(BaseModel):
    """Routing decision for a user prompt."""

    intent: QueryIntent
    confidence: float = Field(ge=0.0, le=1.0)
    query: str
    named_towns: list[str] = Field(default_factory=list)
    unknown_towns: list[str] = Field(default_factory=list)
    compare_town_a: str | None = None
    compare_town_b: str | None = None
    compare_towns: list[str] = Field(default_factory=list)
    compare_columns: list[str] = Field(default_factory=list)
    lookup_town: str | None = None
    lookup_specs: list[dict[str, str]] = Field(default_factory=list)
    unsupported_field: bool = False
    requested_field: str | None = None
    requested_field_category: str | None = None
    use_semantic: bool = False
    pipeline: list[str] = Field(default_factory=list)
    message: str | None = None
    classification_source: Literal["python", "llm"] = "python"
    python_confidence: float | None = None
    python_intent: str | None = None
    llm_fallback_used: bool = False


def _clean_town_label(raw: str) -> str:
    return clean_town_label(raw)


def _extract_compare_towns(query: str) -> tuple[str, str] | None:
    from app.entity_extractor import extract_entities
    entities = extract_entities(query)
    return entities.compare_pair


def _pipeline_for_intent(intent: QueryIntent, *, use_semantic: bool) -> list[str]:
    if intent == "lookup_single_town":
        return ["get_town_facts_tool"]
    if intent == "lookup_multi_town":
        return ["get_town_facts_tool"]
    if intent == "compare_towns":
        return ["compare_suburbs_tool", "save_search_tool"]
    if intent == "compare_multi_town":
        return ["compare_suburbs_multi_tool", "save_search_tool"]
    if intent == "explain_ranking":
        return ["parse_preferences_tool", "rank_suburbs_tool", "explain_results_tool"]
    if intent == "recommend_semantic":
        return [
            "semantic_town_search_tool",
            "parse_preferences_tool",
            "rank_suburbs_tool",
            "explain_results_tool",
            "save_search_tool",
        ]
    if intent == "recommend_structured":
        return [
            "parse_preferences_tool",
            "rank_suburbs_tool",
            "explain_results_tool",
            "save_search_tool",
        ]
    return []


def route_from_classified(
    text: str,
    classified,
    *,
    known: list[str] | None = None,
    unknown: list[str] | None = None,
    llm_fallback_used: bool = False,
    python_snapshot=None,
) -> QueryRoute:
    """Map ClassifiedIntent to QueryRoute."""
    if python_snapshot is None:
        python_snapshot = classified
    known = known or classified.named_towns
    unknown = unknown or classified.unknown_towns

    if classified.intent == "refuse_out_of_scope":
        return QueryRoute(
            intent="unsupported",
            confidence=classified.confidence,
            query=text,
            named_towns=known,
            unknown_towns=unknown,
            message=classified.message,
            pipeline=[],
            classification_source=classified.classification_source,
            python_confidence=python_snapshot.python_confidence or python_snapshot.confidence,
            python_intent=python_snapshot.python_intent or python_snapshot.intent,
            llm_fallback_used=llm_fallback_used,
        )

    if classified.intent == "data_limit_question":
        return QueryRoute(
            intent="data_limit_question",
            confidence=classified.confidence,
            query=text,
            named_towns=known,
            unknown_towns=unknown,
            message=(
                "Live listing feeds (Zillow/Redfin/MLS) are not available. "
                "SuburbScout uses curated local dataset snapshots in suburbs.json."
            ),
            pipeline=[],
            classification_source=classified.classification_source,
            python_confidence=python_snapshot.python_confidence,
            python_intent=python_snapshot.python_intent,
            llm_fallback_used=llm_fallback_used,
        )

    if classified.intent == "needs_clarification":
        return QueryRoute(
            intent="needs_clarification",
            confidence=classified.confidence,
            query=text,
            named_towns=known,
            unknown_towns=unknown,
            message=classified.message,
            pipeline=[],
            classification_source=classified.classification_source,
            python_confidence=python_snapshot.python_confidence,
            python_intent=python_snapshot.python_intent,
            llm_fallback_used=llm_fallback_used,
        )

    if classified.intent in ("lookup_single_town", "dataset_membership"):
        from app.intent_classifier import _membership_town

        entities = extract_entities(text)
        lookup = (
            classified.lookup_town
            or _membership_town(text, entities)
            or (known[0] if known else None)
            or (unknown[0] if unknown else None)
        )
        if lookup and not is_junk_town_candidate(lookup):
            return QueryRoute(
                intent="lookup_single_town",
                confidence=classified.confidence,
                query=text,
                named_towns=known,
                unknown_towns=unknown,
                lookup_town=lookup,
                unsupported_field=bool(getattr(classified, "unsupported_field", False)),
                requested_field=getattr(classified, "requested_field", None),
                requested_field_category=getattr(classified, "requested_field_category", None),
                pipeline=_pipeline_for_intent("lookup_single_town", use_semantic=False),
                classification_source=classified.classification_source,
                python_confidence=python_snapshot.python_confidence,
                python_intent=python_snapshot.python_intent,
                llm_fallback_used=llm_fallback_used,
            )

    if classified.intent == "lookup_multi_town" and classified.lookup_specs:
        return QueryRoute(
            intent="lookup_multi_town",
            confidence=classified.confidence,
            query=text,
            named_towns=known,
            unknown_towns=unknown,
            lookup_specs=list(classified.lookup_specs),
            pipeline=_pipeline_for_intent("lookup_multi_town", use_semantic=False),
            classification_source=classified.classification_source,
            python_confidence=python_snapshot.python_confidence,
            python_intent=python_snapshot.python_intent,
            llm_fallback_used=llm_fallback_used,
        )

    if classified.intent == "compare_multi_town" and classified.compare_towns_list:
        return QueryRoute(
            intent="compare_multi_town",
            confidence=classified.confidence,
            query=text,
            named_towns=known,
            unknown_towns=unknown,
            compare_towns=list(classified.compare_towns_list),
            compare_columns=list(classified.compare_fields),
            pipeline=_pipeline_for_intent("compare_multi_town", use_semantic=False),
            classification_source=classified.classification_source,
            python_confidence=python_snapshot.python_confidence,
            python_intent=python_snapshot.python_intent,
            llm_fallback_used=llm_fallback_used,
        )

    if classified.intent == "compare_towns" and classified.compare_town_a and classified.compare_town_b:
        return QueryRoute(
            intent="compare_towns",
            confidence=classified.confidence,
            query=text,
            named_towns=known,
            unknown_towns=unknown,
            compare_town_a=classified.compare_town_a,
            compare_town_b=classified.compare_town_b,
            pipeline=_pipeline_for_intent("compare_towns", use_semantic=False),
            classification_source=classified.classification_source,
            python_confidence=python_snapshot.python_confidence,
            python_intent=python_snapshot.python_intent,
            llm_fallback_used=llm_fallback_used,
        )

    if classified.intent == "recommend_semantic":
        return QueryRoute(
            intent="recommend_semantic",
            confidence=classified.confidence,
            query=text,
            named_towns=known,
            unknown_towns=unknown,
            use_semantic=True,
            pipeline=_pipeline_for_intent("recommend_semantic", use_semantic=True),
            classification_source=classified.classification_source,
            python_confidence=python_snapshot.python_confidence,
            python_intent=python_snapshot.python_intent,
            llm_fallback_used=llm_fallback_used,
        )

    if classified.intent == "recommend_structured":
        return QueryRoute(
            intent="recommend_structured",
            confidence=classified.confidence,
            query=text,
            named_towns=known,
            unknown_towns=unknown,
            use_semantic=False,
            pipeline=_pipeline_for_intent("recommend_structured", use_semantic=False),
            classification_source=classified.classification_source,
            python_confidence=python_snapshot.python_confidence,
            python_intent=python_snapshot.python_intent,
            llm_fallback_used=llm_fallback_used,
        )

    return QueryRoute(
        intent="unsupported",
        confidence=0.5,
        query=text,
        named_towns=known,
        unknown_towns=unknown,
        message=classified.message or "Could not determine suburb query intent.",
        pipeline=[],
        classification_source=classified.classification_source,
        python_confidence=python_snapshot.python_confidence,
        python_intent=python_snapshot.python_intent,
        llm_fallback_used=llm_fallback_used,
    )


def classify_query_python(query: str) -> QueryRoute:
    """Python-only routing (no LLM)."""
    text = query.strip()
    lower = text.lower()
    known, unknown = extract_town_mentions(text)

    if not text:
        return QueryRoute(
            intent="unsupported",
            confidence=0.0,
            query=text,
            message="Empty query.",
            pipeline=[],
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

    if EXPLAIN_RE.search(text):
        return QueryRoute(
            intent="explain_ranking",
            confidence=0.9,
            query=text,
            named_towns=known,
            unknown_towns=unknown,
            pipeline=_pipeline_for_intent("explain_ranking", use_semantic=False),
            classification_source="python",
        )

    classified = classify_user_intent(text)
    classified.python_intent = classified.intent
    classified.python_confidence = classified.confidence
    return route_from_classified(text, classified, known=known, unknown=unknown)


def classify_query(query: str) -> QueryRoute:
    """Sync classify — Python rules only (backward compatible)."""
    return classify_query_python(query)
