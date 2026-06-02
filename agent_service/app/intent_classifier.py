"""Shared query intent classification (Phase 1.4) — entity-first router + validator."""

from __future__ import annotations

import re
from typing import Literal


from pydantic import BaseModel, Field

from app.constraint_parser import parse_constraints
from app.entity_extractor import (
    ExtractedEntities,
    clean_entity_span,
    extract_entities,
    has_comparison_relation,
    is_junk_town_candidate,
    primary_town,
)
from app.query_patterns import (
    LookupSpec,
    detect_multi_commute_compare,
    detect_multi_town_lookup_specs,
    extract_multi_compare_towns,
    infer_compare_table_columns,
    is_coastal_town_list_query,
    is_membership_supported_query,
    is_multi_field_lookup,
    is_open_ended_recommendation,
    is_scope_inclusion_lookup,
    open_ended_clarification_message,
    resolve_typo_lookup_town,
)
from app.town_normalizer import canonical_town_name

IntentKind = Literal[
    "lookup_single_town",
    "lookup_multi_town",
    "dataset_membership",
    "compare_towns",
    "compare_multi_town",
    "recommend_structured",
    "recommend_semantic",
    "explain_ranking",
    "data_limit_question",
    "needs_clarification",
    "refuse_out_of_scope",
    "unsupported",
]

RECOMMEND_HINTS: tuple[str, ...] = (
    "recommend",
    "find me",
    "find a",
    "find towns",
    "find places",
    "best suburb",
    "best town",
    "best places",
    "top suburb",
    "top town",
    "top ",
    "which towns",
    "where should",
    "help me find",
    "looking for",
    "suggest",
    "show me towns",
    "show me places",
    "show me options",
    "show me affordable",
    "show me cheaper",
    "show me lower",
    "show me risky",
    "give me towns",
    "give me options",
    "give me good options",
)

SEMANTIC_VIBE_PHRASES: tuple[str, ...] = (
    "feel",
    "vibe",
    "walkable",
    "charming",
    "quaint",
    "small-town feel",
    "coastal feel",
    "coastal vibe",
    "character",
    " atmosphere",
    "sense of community",
    "new england town feel",
    "village-center",
    "less intense version",
    "lower-cost version",
    "similar to",
    "feels like",
    "like acton",
    "like wellesley",
    "like lexington",
    "like cambridge",
    "like brookline",
    "like sharon",
    "like burlington",
    "educated",
    "family-focused",
    "peaceful town",
    "balanced suburb",
    "energy without",
    "feels somewhat similar",
    "old new england center",
    "high-education",
    "maximize value",
    "calm, stable",
    "-style",
)

DATA_LIMIT_PHRASES: tuple[str, ...] = (
    "zillow",
    "redfin",
    "realtor.com",
    "live price",
    "live data",
    "real-time",
    "realtime",
    "today's price",
    "todays price",
    "current market",
    "right now",
    "mls listing",
)

LOOKUP_FIELD_WORDS: tuple[str, ...] = (
    "commute",
    "distance",
    "drive distance",
    "how far",
    "price",
    "home price",
    "housing price",
    "housing data",
    "expensive",
    "affordability",
    "crime",
    "crime score",
    "safety",
    "safe",
    "school rating",
    "school score",
    "schools",
    "strong schools",
    "missing",
    "fields",
    "partial",
    "full-data",
    "full data",
    "partial-data",
    "partial data",
    "data quality",
    "data-quality",
    "data profile",
    "county",
    "region",
    "coastal",
    "coast",
    "near the coast",
    "inland",
    "basic stats",
    "stats for",
    "summary",
    "population",
    "according to your data",
    "in your data",
    "stored home price",
    "have school data",
    "have a housing price",
    "complete housing",
    "marked coastal",
    "actually coastal",
    "coast town",
    "high or low",
    "everything you know",
    "what do you know",
    "pull up",
    "tell me if",
    "stored profile",
    "dataset report",
    "suburb record",
    "summarize",
    "pricey",
    "look risky",
    "drive time",
    "how many miles",
    "how close",
    "school percentile",
    "tagged",
    "median home value",
    "safety rating",
    "unavailable",
    "data complete",
    "according to your tags",
    "count as coastal",
)

LOOKUP_RELATION_SIGNALS: tuple[str, ...] = (
    "stored profile",
    "dataset report",
    "summarize",
    "using your stored",
    "pricey in your data",
    "look risky",
    "basic suburb record",
    "drive time",
    "how many miles",
    "how close is",
    "school percentile",
    "tagged as",
    "tagged coastal",
    "marked full",
    "marked partial",
    "data complete",
    "median home value",
    "safety rating does",
    "fields are unavailable",
    "school and safety info",
    "commute and safety numbers",
    "do you know",
    "what price do you have",
    "suburb entry",
    "numbers do you have saved",
    "recorded school metric",
    "strongest and weakest",
    "classified as complete",
    "complete data",
    "safety and commute snapshot",
    "full town summary",
    "home price is listed",
    "missing anything important",
    "based on your records",
    "labeled waterfront",
    "counts as inland",
    "housing data",
    "saved statistics",
    "information is incomplete",
    "incomplete for",
    "how long would",
    "take to boston",
    "home value is stored",
    "main numbers you store",
    "suburb file",
    "data card for",
    "main suburb stats",
    "complete row",
    "missing values record",
    "high-crime or low-crime",
    "price snapshot",
    "suburb stats",
)

MEMBERSHIP_RELATION_SIGNALS: tuple[str, ...] = (
    "can your system handle",
    "can you search",
    "can the app answer",
    "do you keep",
    "resolve to",
    "mapped to",
    "curated list",
    "support",
    "queries",
    "covered by",
    "suburb scope",
    "towns you loaded",
    "normalized to",
    "recognized as",
    "outside your coverage",
    "excluded from",
    "outside the boston",
    "out of scope",
    "non-massachusetts",
    "cape towns",
    "in the dataset",
    "in your dataset",
    "would resolve",
    "would be accepted",
    "would be rejected",
    "search term",
    "translate",
    "actually loaded",
    "results available",
    "redirect to",
    "queried directly",
    "town universe",
    "searchable",
    "loaded 200",
    "exact name",
    "in scope",
    "in your database",
    "alternate spelling",
    "work as a search",
    "valid result",
    "accepted alias",
    "be searched",
    "understood as",
    "point to",
    "dataset include",
    "canonical spelling",
    "200-town load",
    "usable in this app",
    "rankable",
    "queryable",
    "loaded into",
    "means marlborough",
    "ranked by this tool",
    "recommendations available",
    "understand it as",
    "exist in your dataset",
    "town list",
    "loaded and usable",
    "lookups possible",
    "will the app understand",
    "are there records for",
    "as a town name",
    "does the app know",
    "valid alias",
)

MEMBERSHIP_PHRASE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bdo you cover\b", re.I),
    re.compile(r"\bis .+ included\b", re.I),
    re.compile(r"\bis .+ in (?:your )?(?:the )?(?:town )?(?:dataset|list|data)\b", re.I),
    re.compile(r"\bis .+ part of\b", re.I),
    re.compile(r"\bdo you have (?:data for )?\b", re.I),
    re.compile(r"\bdo you include\b", re.I),
    re.compile(r"\bis .+ covered\b", re.I),
    re.compile(r"\b(?:is|are) .+ in your data\b", re.I),
    re.compile(r"\bclosest matches to\b", re.I),
    re.compile(r"\bare you able to search\b", re.I),
    re.compile(r"\bdo you track\b", re.I),
    re.compile(r"\bdo you recognize\b", re.I),
    re.compile(r"\bdo you support recommendations for\b", re.I),
    re.compile(r"\bcan you answer questions about\b", re.I),
    re.compile(r"\bis .+ treated as\b", re.I),
    re.compile(r"\bis .+ stored with\b", re.I),
    re.compile(r"\bis .+ in the 200[- ]town scope\b", re.I),
    re.compile(r"\bis .+ one of the 200 towns\b", re.I),
    re.compile(r"\bis .+ a town you track\b", re.I),
    re.compile(r"\bis .+ the same as .+ in your data\b", re.I),
    re.compile(r"\bcan your system handle\b", re.I),
    re.compile(r"\bis .+ mapped to\b", re.I),
    re.compile(r"\bwould .+ resolve to\b", re.I),
    re.compile(r"\bdo you keep\b", re.I),
    re.compile(r"\bis .+ in the curated list\b", re.I),
    re.compile(r"\bis .+ recognized as\b", re.I),
    re.compile(r"\bcan you search\b", re.I),
    re.compile(r"\bcan the app answer\b", re.I),
    re.compile(r"\bdo you support\b", re.I),
    re.compile(r"\bis .+ covered by\b", re.I),
    re.compile(r"\bis .+ part of the suburb scope\b", re.I),
    re.compile(r"\bis .+ one of the towns you loaded\b", re.I),
    re.compile(r"\bis .+ normalized to\b", re.I),
    re.compile(r"\bwill .+ work as a search term\b", re.I),
    re.compile(r"\bdoes the system translate\b", re.I),
    re.compile(r"\bis .+ actually loaded\b", re.I),
    re.compile(r"\bare .+ results available\b", re.I),
    re.compile(r"\bdoes .+ redirect to\b", re.I),
    re.compile(r"\bcan .+ be queried directly\b", re.I),
    re.compile(r"\bis .+ inside the project'?s town universe\b", re.I),
    re.compile(r"\bis .+ searchable\b", re.I),
    re.compile(r"\bcan .+ be used in recommendations\b", re.I),
    re.compile(r"\bdid .+ make it into the loaded 200 towns\b", re.I),
    re.compile(r"\bdo you store .+ under that exact name\b", re.I),
    re.compile(r"\bis .+ in scope\b", re.I),
    re.compile(r"\bis .+ supported\b", re.I),
    re.compile(r"\bis .+ excluded\b", re.I),
    re.compile(r"\bis .+ in your database\b", re.I),
    re.compile(r"\bwould .+ be accepted as an alternate spelling\b", re.I),
    re.compile(r"\bdo you have .+ in the loaded towns\b", re.I),
    re.compile(r"\bis .+ rankable\b", re.I),
    re.compile(r"\bis .+ queryable\b", re.I),
    re.compile(r"\b(?:are|is) .+ (?:usable|available)\b", re.I),
    re.compile(r"\bloaded into the 200\b", re.I),
    re.compile(r"\branked by this tool\b", re.I),
    re.compile(r"\b(?:does|do) .+ mean\b", re.I),
    re.compile(r"\bare recommendations available for\b", re.I),
    re.compile(r"\b(?:is|are) .+ loaded and usable\b", re.I),
    re.compile(r"\bare lookups possible for\b", re.I),
    re.compile(r"\bcan .+ be ranked\b", re.I),
    re.compile(r"\bis .+ recognized\b", re.I),
    re.compile(r"\bif i type .+, will the app understand\b", re.I),
    re.compile(r"\bare there records for\b", re.I),
    re.compile(r"\bcan i use .+ as a town name\b", re.I),
    re.compile(r"\bdoes the app know .+ means\b", re.I),
)

LOOKUP_PHRASE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bpull up everything you know about\b", re.I),
    re.compile(r"\bwhat do you know about\b", re.I),
    re.compile(r"\bgive me the data profile for\b", re.I),
    re.compile(r"\btell me if .+ has complete housing data\b", re.I),
    re.compile(r"\btell me about\b", re.I),
    re.compile(r"\bdoes .+ have a high or low crime score\b", re.I),
    re.compile(r"\bdoes .+ have good schools\b", re.I),
    re.compile(r"\bis .+ a coast town\b", re.I),
    re.compile(r"\bis .+ expensive\b", re.I),
    re.compile(r"\bwhat does your data say about\b", re.I),
    re.compile(r"\bwhat is the school rating for\b", re.I),
    re.compile(r"\bshow me the stored profile for\b", re.I),
    re.compile(r"\bwhat does the dataset report for\b", re.I),
    re.compile(r"\btell me whether\b", re.I),
    re.compile(r"\bwhat fields are unavailable for\b", re.I),
    re.compile(r"\bsummarize\b", re.I),
    re.compile(r"\bhow many miles is\b", re.I),
    re.compile(r"\bhow close is\b", re.I),
    re.compile(r"\bdo you know\b", re.I),
    re.compile(r"\bdoes .+ look risky\b", re.I),
    re.compile(r"\bis .+ tagged\b", re.I),
    re.compile(r"\bis .+ marked full\b", re.I),
    re.compile(r"\bwhat price do you have for\b", re.I),
    re.compile(r"\bwhat school percentile\b", re.I),
    re.compile(r"\bwhat safety rating does\b", re.I),
    re.compile(r"\bpull facts for\b", re.I),
    re.compile(r"\bsearch for\b", re.I),
    re.compile(r"\bwhat school number is listed for\b", re.I),
    re.compile(r"\bwhat is missing from\b", re.I),
    re.compile(r"\bcheck .+'s record for missing\b", re.I),
)

OUT_OF_SCOPE_TOWNS = frozenset({
    "providence", "nashua", "springfield", "amherst", "brooklyn",
})

OUTSIDE_DATASET_RE = re.compile(r"\boutside your 200[- ]town list\b", re.I)
WORK_IN_RE = re.compile(
    r"\b(?:i\s+)?work\s+(?:in|at)\s+([a-zA-Z][\w\s\-']+)",
    re.IGNORECASE,
)
FUTURE_YEAR_DATA_RE = re.compile(r"\b20\d{2}\b")
POSSESSIVE_TOWN_RE = re.compile(
    r"\b([A-Z][a-zA-Z\-']+(?:[\s\-][A-Z][a-zA-Z\-']+)?)'s\s+(?:crime|safety|school|commute|home|price|population|affordability|stored)",
    re.I,
)
HOW_FAR_RE = re.compile(
    r"\bhow far is\s+([a-zA-Z][\w\s\-']+?)\s+from\b",
    re.I,
)
HOW_EXPENSIVE_RE = re.compile(
    r"\bhow expensive is\s+([a-zA-Z][\w\s\-']+?)\b",
    re.I,
)
COMMUTE_DATA_FOR_RE = re.compile(
    r"\b(?:what )?commute data do you have for\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
COUNTY_REGION_RE = re.compile(
    r"\bwhat county and region is\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
MISSING_INFO_RE = re.compile(
    r"\bwhat information is missing for\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
BASIC_STATS_RE = re.compile(
    r"\bgive me (?:the )?basic stats for\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
DATA_QUALITY_SUMMARY_RE = re.compile(
    r"\b(?:give me )?(?:a )?data[- ]quality summary for\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
FULL_PARTIAL_RE = re.compile(
    r"\bis\s+([a-zA-Z][\w\s\-']+?)\s+(?:considered\s+)?(?:a\s+)?(?:full[- ]data|partial[- ]data)",
    re.I,
)
HAVE_HOUSING_RE = re.compile(
    r"\bdoes your dataset have (?:a )?housing price for\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
HAVE_SCHOOL_RE = re.compile(
    r"\bdoes\s+([a-zA-Z][\w\s\-']+?)\s+have school data",
    re.I,
)
MISSING_FIELDS_RE = re.compile(
    r"\bis\s+([a-zA-Z][\w\s\-']+?)\s+missing any",
    re.I,
)
MARKED_COASTAL_RE = re.compile(
    r"\bis\s+([a-zA-Z][\w\s\-']+?)\s+marked coastal",
    re.I,
)
IS_COASTAL_RE = re.compile(r"\bis\s+([a-zA-Z][\w\s\-']+?)\s+(?:actually\s+)?coastal\b", re.I)
COMMUTE_FOR_FLEX_RE = re.compile(
    r"(?:commute|drive)(?:\s+and\s+distance)?\s+for\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
COMMUTE_FROM_RE = re.compile(
    r"(?:commute|drive)\s+from\s+([a-zA-Z][\w\s\-']+?)(?:\s+to\s+boston|\?|$|,|\.)",
    re.I,
)
COMMUTE_TO_BOSTON_RE = re.compile(
    r"\b(?:what is )?(?:the )?(?:boston )?commute for\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
TELL_ME_STORED_RE = re.compile(
    r"\btell me\s+([a-zA-Z][\w\s\-']+?)'s\s+(?:stored )?(?:home price|commute|price)",
    re.I,
)
CLOSEST_MATCHES_RE = re.compile(
    r"\bclosest matches to\s+[\"']?([a-zA-Z][\w\s\-']+)[\"']?",
    re.I,
)
AMBIGUOUS_RE = re.compile(r"\bambiguous in your town list\b", re.I)
ALIAS_SAME_RE = re.compile(
    r"\bis\s+(.+?)\s+the same as\s+(.+?)\s+in your data",
    re.I,
)
FOXBORO_RE = re.compile(r"\bfoxboro(?:ugh)?\s+included,?\s+or only\s+foxboro(?:ugh)?\b", re.I)
MARLBORO_OR_RE = re.compile(r"\bmarlboro(?:ugh)?\s+or\s+marlboro(?:ugh)?\b", re.I)
RECOMMEND_IF_NOT_RE = re.compile(
    r"\brecommend .+ if (?:it is )?not in your dataset\b",
    re.I,
)
CAPE_COD_RE = re.compile(r"\bcape cod\b", re.I)
REGION_SCOPE_RE = re.compile(
    r"\b(?:north shore|south shore|metrowest|metro west|495 belt|route 2|route 24|"
    r"cape cod|inner metro|core boston)\b.*\b(?:included|in your list|in the dataset|cover)\b",
    re.I,
)

RECOMMEND_NOUN_PHRASES = (
    "affordable suburb", "affordable town", "good suburb", "good town",
    "safe town", "safe suburb", "family-friendly", "first-time homebuyer",
    "coastal town", "coastal suburbs", "north shore", "south shore",
    "close to boston", "near boston", "within ", "mins from", "minutes from",
    "minutes to", "mins to", "mins away", "minutes away", "don't care about",
    "only care about", "only have", "be honest about", "not extremely expensive",
    "lower home prices", "lower prices", "cheapest towns", "worse safety",
    "high crime", "high-crime", "risky but", "weak schools", "average schools",
    "elite schools", "decent schools", "low crime", "strong schools", "good schools",
    "coastal-only", "coastal only", "far-out towns", "far out towns",
    "exclude anything", "not partial data", "missing-price towns",
    "optimize schools", "optimize price", "rank towns by worst",
    "higher crime", "bad safety", "major downsides", "not top-ranked",
    "low-price options", "affordability first", "schools first", "safety first",
    "commute not the priority", "commute is not the priority",
    "exclude inland", "not city-like", "short commute and low price",
    "no missing price", "below 850k", "below 800k", "below 700k",
)


class ClassifiedIntent(BaseModel):
    """Unified intent classification result."""

    intent: IntentKind
    confidence: float = 0.0
    lookup_town: str | None = None
    lookup_field: str | None = None
    compare_town_a: str | None = None
    compare_town_b: str | None = None
    compare_towns_list: list[str] = Field(default_factory=list)
    compare_fields: list[str] = Field(default_factory=list)
    lookup_specs: list[dict[str, str]] = Field(default_factory=list)
    named_towns: list[str] = Field(default_factory=list)
    unknown_towns: list[str] = Field(default_factory=list)
    field: str | None = None
    constraints: dict[str, object] = Field(default_factory=dict)
    unsupported_field: bool = False
    requested_field: str | None = None
    requested_field_category: str | None = None
    reason: str | None = None
    message: str | None = None
    classification_source: Literal["python", "llm"] = "python"
    python_intent: str | None = None
    python_confidence: float | None = None


def clean_town_label(raw: str) -> str:
    return clean_entity_span(raw)


def _unsupported_field_lookup_intent(
    town: str,
    requested_field: str,
    *,
    entities: ExtractedEntities,
    category: str = "lifestyle",
    confidence: float = 0.92,
    reason: str = "",
) -> ClassifiedIntent:
    cleaned = clean_town_label(town)
    return ClassifiedIntent(
        intent="lookup_single_town",
        confidence=confidence,
        lookup_town=cleaned,
        lookup_field="unsupported",
        field="unsupported",
        unsupported_field=True,
        requested_field=requested_field,
        requested_field_category=category,
        constraints={
            "unsupported_field": True,
            "requested_field": requested_field,
            "requested_field_category": category,
        },
        named_towns=entities.valid_towns,
        unknown_towns=entities.unknown_town_candidates,
        reason=reason or f"unknown attribute lookup: {requested_field}",
    )


def _lookup_intent(
    town: str,
    field: str | None,
    *,
    entities: ExtractedEntities,
    confidence: float = 0.94,
    reason: str = "",
) -> ClassifiedIntent:
    cleaned = clean_town_label(town)
    return ClassifiedIntent(
        intent="lookup_single_town",
        confidence=confidence,
        lookup_town=cleaned,
        lookup_field=field,
        field=field,
        named_towns=entities.valid_towns,
        unknown_towns=entities.unknown_town_candidates,
        reason=reason or f"single town lookup ({field or 'summary'})",
    )


def _membership_intent(
    town: str | None,
    *,
    entities: ExtractedEntities,
    confidence: float = 0.93,
    reason: str = "",
) -> ClassifiedIntent:
    resolved = town or primary_town(entities)
    return ClassifiedIntent(
        intent="dataset_membership",
        confidence=confidence,
        lookup_town=clean_town_label(resolved) if resolved else None,
        lookup_field="dataset",
        field="dataset",
        named_towns=entities.valid_towns,
        unknown_towns=entities.unknown_town_candidates,
        reason=reason or "membership/scope/alias question",
    )


def _compare_intent(
    a: str,
    b: str,
    *,
    entities: ExtractedEntities,
    field: str | None = None,
    confidence: float = 0.95,
    reason: str = "",
) -> ClassifiedIntent:
    return ClassifiedIntent(
        intent="compare_towns",
        confidence=confidence,
        compare_town_a=clean_town_label(a),
        compare_town_b=clean_town_label(b),
        field=field,
        named_towns=entities.valid_towns,
        unknown_towns=entities.unknown_town_candidates,
        reason=reason or "two towns + comparison relation",
    )


def _lookup_multi_intent(
    specs: list[LookupSpec],
    *,
    entities: ExtractedEntities,
    confidence: float = 0.93,
    reason: str = "",
) -> ClassifiedIntent:
    payload = [{"town": s.town, "field": s.field} for s in specs]
    return ClassifiedIntent(
        intent="lookup_multi_town",
        confidence=confidence,
        lookup_specs=payload,
        named_towns=entities.valid_towns,
        unknown_towns=entities.unknown_town_candidates,
        reason=reason or f"multi-town lookup ({len(specs)} specs)",
    )


def _compare_multi_intent(
    towns: list[str],
    *,
    entities: ExtractedEntities,
    columns: list[str],
    confidence: float = 0.92,
    reason: str = "",
) -> ClassifiedIntent:
    return ClassifiedIntent(
        intent="compare_multi_town",
        confidence=confidence,
        compare_towns_list=towns,
        compare_fields=columns,
        named_towns=entities.valid_towns,
        unknown_towns=entities.unknown_town_candidates,
        reason=reason or f"multi-town compare table ({len(towns)} towns)",
    )


def _recommend_intent(
    *,
    entities: ExtractedEntities,
    semantic: bool = False,
    confidence: float = 0.86,
    reason: str = "",
) -> ClassifiedIntent:
    return ClassifiedIntent(
        intent="recommend_semantic" if semantic else "recommend_structured",
        confidence=confidence,
        named_towns=entities.valid_towns,
        unknown_towns=entities.unknown_town_candidates,
        reason=reason or "budget/commute/preference recommendation",
    )


def _has_lookup_field_signal(lower: str) -> bool:
    return any(w in lower for w in LOOKUP_FIELD_WORDS)


def _has_lookup_phrase(lower: str) -> bool:
    return any(p.search(lower) for p in LOOKUP_PHRASE_RES)


def _is_membership_query(lower: str) -> bool:
    return any(p.search(lower) for p in MEMBERSHIP_PHRASE_RES)


def _has_membership_relation(lower: str) -> bool:
    if re.search(r"\b(?:coastal|ocean|waterfront|seaside|ocean-adjacent).+\b(?:towns|suburbs|places|only)\b", lower):
        return False
    if re.search(r"\b(?:towns|suburbs|places).+\b(?:only|in the dataset)\b", lower):
        return False
    if re.search(r"\b(?:cheapest|affordable|find|show|give me|want the) towns\b", lower):
        return False
    if re.search(r"\bwhat (?:would|happens)\b", lower):
        return False
    if re.search(r"\bwhat .+ do you have saved\b", lower):
        return False
    if re.search(r"\bwould not normally rank\b", lower):
        return False
    if any(signal in lower for signal in MEMBERSHIP_RELATION_SIGNALS):
        return True
    return _is_membership_query(lower)


def _has_lookup_relation(lower: str) -> bool:
    if any(signal in lower for signal in LOOKUP_RELATION_SIGNALS):
        return True
    if _has_lookup_phrase(lower):
        return True
    if re.search(r"\b(?:give me|pull|do you know)\s+[a-z][\w\s\-']+'s\b", lower):
        return True
    if re.search(r"\bwhat is [a-z][\w\s\-']+'s\b", lower):
        return True
    return False


def _is_lookup_query(query: str, entities: ExtractedEntities) -> bool:
    """True when query asks for one town's facts (Phase 1.4B)."""
    lower = query.lower()
    if re.search(r"\b(?:towns|places|suburbs|options)\b", lower) and re.search(
        r"\b(?:drive time|commute).*(?:under|within|over|between|capped|at least|or more)\b",
        lower,
    ):
        return False
    if re.search(r"\bsuburb (?:file|entry|record|stats|card)\b|\bdata card for\b|\bmain suburb stats\b", lower):
        if len(entities.valid_towns) + len(entities.unknown_town_candidates) >= 1:
            return True
    if re.search(r"\b(?:keep|drive time under)\b", lower) and re.search(r"\b\d+\s*(?:mins?|minutes)\b", lower):
        if not re.search(r"\b(?:for|of)\s+[A-Z][a-z][\w\s\-']+\s*(?:\?|$)", query):
            return False
    if _is_single_town_lookup(query, entities):
        return True
    town_count = len(entities.valid_towns) + len(entities.unknown_town_candidates)
    if town_count >= 1 and _has_lookup_relation(lower):
        if re.search(r"\bwhat price do you have for\b", lower):
            return True
        if re.search(r"\b(?:stored profile|dataset report|summarize|drive time|school percentile)\b", lower):
            return True
        if re.search(r"\bnumbers do you have saved\b", lower):
            return True
        if re.search(r"\bnear the coast\b", lower):
            return True
        if re.search(r"\b(?:give me|pull)\s+[a-z].+'s\b", lower):
            return True
        if re.search(r"\b(?:is|does)\s+.+\s+(?:pricey|risky|tagged|marked|complete)\b", lower):
            return True
        if re.search(r"\b(?:suburb entry|numbers saved|recorded school|strongest and weakest|complete data)\b", lower):
            return True
        if re.search(r"\b(?:saved statistics|information is incomplete|how long would|home value is stored|main numbers you store)\b", lower):
            return True
        if re.search(r"\b(?:safety and commute snapshot|full town summary|based on your records)\b", lower):
            return True
    if re.search(r"\bsearch for\b", lower) and town_count >= 1:
        return True
    if re.search(r"\bwhat school number is listed for\b", lower) and town_count >= 1:
        return True
    if re.search(r"\bwhat is missing from\b", lower) and town_count >= 1:
        return True
    if re.search(r"\blook up\b", lower) and town_count >= 1:
        return True
    if re.search(r"\bcan you find\b", lower) and town_count >= 1 and "in scope" not in lower:
        return True
    if town_count >= 1 and re.search(r"\bnear the coast\b", lower):
        return True
    return False


def _is_single_town_lookup(query: str, entities: ExtractedEntities) -> bool:
    """True when query asks about one town's facts, not a list recommendation."""
    lower = query.lower()
    town_count = len(entities.valid_towns) + len(entities.unknown_town_candidates)

    if _has_lookup_phrase(lower):
        return True

    if town_count == 1 and _has_lookup_field_signal(lower):
        if re.search(r"\bdoes\s+.+\s+have\b", lower):
            return True
        if re.search(r"\bis\s+.+\s+(?:expensive|coastal|a coast town)\b", lower):
            return True
        if re.search(r"\bis\s+.+\s+near the coast\b", lower):
            return True
        if re.search(r"\bwhat does your data say about\b", lower):
            return True
        if "tell me about" in lower and not _has_recommendation_ask(query):
            return True

    lookup_patterns = (
        POSSESSIVE_TOWN_RE, HOW_FAR_RE, HOW_EXPENSIVE_RE, COMMUTE_DATA_FOR_RE,
        TELL_ME_STORED_RE, COUNTY_REGION_RE, MISSING_INFO_RE, BASIC_STATS_RE,
        DATA_QUALITY_SUMMARY_RE, FULL_PARTIAL_RE, HAVE_HOUSING_RE, HAVE_SCHOOL_RE,
        MISSING_FIELDS_RE, MARKED_COASTAL_RE, IS_COASTAL_RE, COMMUTE_FOR_FLEX_RE,
        COMMUTE_FROM_RE, COMMUTE_TO_BOSTON_RE,
    )
    if any(p.search(query) for p in lookup_patterns):
        return True

    if town_count == 1 and re.search(r"\btell me about\s+", lower) and not _has_recommendation_ask(query):
        return True

    if re.search(r"\bwhat is the school rating for\b", lower):
        return True
    if re.search(r"\bis\s+.+\s+expensive\b", lower) and not re.search(r"\bnot too expensive\b", lower):
        return True

    return False


def _infer_lookup_field(lower: str) -> str:
    if "commute" in lower or "distance" in lower or "how far" in lower:
        return "commute"
    if "crime" in lower or "safety" in lower:
        return "safety"
    if "school" in lower:
        return "school"
    if "price" in lower or "expensive" in lower or "affordability" in lower or "housing" in lower:
        return "price"
    if "missing" in lower or "fields" in lower:
        return "missing"
    if "county" in lower or "region" in lower:
        return "region"
    if "coastal" in lower or "inland" in lower or "coast" in lower:
        return "coastal"
    if "partial" in lower or "full-data" in lower or "data quality" in lower or "complete" in lower:
        return "tier"
    if "data profile" in lower or "everything you know" in lower or "what do you know" in lower:
        return "summary"
    if "stored profile" in lower or "dataset report" in lower or "summarize" in lower:
        return "summary"
    if "drive time" in lower or "how many miles" in lower:
        return "commute"
    if "percentile" in lower or "school score" in lower:
        return "school"
    if "pricey" in lower or "median home" in lower:
        return "price"
    if "risky" in lower:
        return "safety"
    if "tagged" in lower or "according to your tags" in lower:
        return "coastal"
    return "summary"


def _has_recommendation_ask(text: str) -> bool:
    lower = text.lower()
    if re.search(r"\bdoes\s+.+\s+(?:have|get)\b", lower):
        if not re.search(r"\b(?:towns|places|suburbs|options|recommend)\b", lower):
            return False
    if re.search(r"\b(?:can|is)\s+.+\s+(?:be used in|used in)\s+(?:recommendations|queries)\b", lower):
        return False
    if re.search(r"\brecommendations possible\b", lower):
        return False
    if re.search(r"\b(?:bring up|open)\b.+\bentry\b", lower):
        return False
    if re.search(r"\bentry from the suburb dataset\b", lower):
        return False
    if re.search(r"\bsuburb entry\b", lower):
        return False
    if re.search(r"\blook up\b", lower) and not re.search(r"\b(?:towns|places|suburbs)\b", lower):
        return False
    if re.search(r"\bgive me [a-z][\w\s\-']+'s\b", lower):
        return False
    if re.search(r"\bpull [a-z][\w\s\-']+'s\b", lower):
        return False
    if re.search(r"\bfind a\b", lower) and re.search(r"\b(?:north|south) shore\b", lower):
        return True
    if re.search(r"\b(?:keep|drive time under)\b", lower) and re.search(r"\b\d+\s*(?:mins?|minutes)\b", lower):
        return True
    if _has_lookup_relation(lower) and not re.search(r"\b(?:towns|places|suburbs|options|town|suburb)\b", lower):
        entities = extract_entities(text)
        if len(entities.valid_towns) + len(entities.unknown_town_candidates) <= 1:
            return False
    if any(h in lower for h in RECOMMEND_HINTS):
        return True
    if any(p in lower for p in RECOMMEND_NOUN_PHRASES):
        return True
    if re.search(r"\$\d", text):
        return True
    if re.search(r"\b(?:under|below|less than|max|up to|over|not over|don't show me anything over)\s*\$?\d", lower):
        return True
    if re.search(r"\bunder \d+k\b", lower):
        return True
    if re.search(r"\bbelow \d+k\b", lower):
        return True
    if re.search(r"\bmy budget is\b", lower):
        return True
    if re.search(r"\bwhat can i get if\b", lower):
        return True
    if re.search(r"\bi can stretch to\b", lower):
        return True
    if re.search(r"\bi prefer being\b", lower):
        return True
    if re.search(r"\b\d+\s+minutes or more\b", lower):
        return True
    if re.search(r"\bcommute is not the priority\b", lower):
        return True
    if re.search(r"\bcommute not priority\b", lower):
        return True
    if re.search(r"\bexclude inland\b", lower):
        return True
    if re.search(r"\bcoastal, but not\b", lower):
        return True
    if re.search(r"\bshort commute and low price\b", lower):
        return True
    if re.search(r"\baffordability first\b", lower):
        return True
    if re.search(r"\bschools first\b", lower):
        return True
    if re.search(r"\bsafety first\b", lower):
        return True
    if re.search(r"\bno missing price\b", lower):
        return True
    if re.search(r"\bkeep boston drive time under\b", lower):
        return True
    if re.search(r"\bdrive time under\s+\d+\s*(?:mins?|minutes)\b", lower) and not re.search(
        r"\b(?:for|of)\s+[A-Z][a-z]", text
    ):
        return True
    if re.search(r"\bquick boston access\b", lower):
        return True
    if re.search(r"\bdo not include inland\b", lower):
        return True
    if re.search(r"\bwater-side\b", lower) and re.search(r"\btowns\b", lower):
        return True
    if re.search(r"\bcoast town\b", lower) and re.search(r"\btowns\b", lower):
        return True
    if re.search(r"\bcheaper towns past\b", lower):
        return True
    if re.search(r"\bcommute can be bad if\b", lower):
        return True
    if re.search(r"\b(?:lowest|cheapest|low-cost|lower-cost|bottom-priced)\s+(?:cost\s+)?towns\b", lower):
        return True
    if re.search(r"\bsafety secondary\b", lower):
        return True
    if re.search(r"\bocean-adjacent\b", lower) and re.search(r"\btowns\b", lower):
        return True
    if re.search(r"\bcommute window\b", lower):
        return True
    if re.search(r"\baccept weaker schools\b", lower):
        return True
    if re.search(r"\brank towns with\b", lower):
        return True
    if re.search(
        r"\b(?:towns|places|suburbs|options)\b", lower
    ) and re.search(
        r"\b(?:drive time|commute).*(?:under|within|over|between|capped|at least|or more)\b",
        lower,
    ):
        return True
    if "suburb" in lower or "suburbs" in lower:
        if _has_lookup_relation(lower) or re.search(
            r"\bsuburb (?:file|entry|record|stats|card)\b|\bdata card for\b|\bmain suburb stats\b",
            lower,
        ):
            if not re.search(
                r"\b(?:show me towns|find towns|give me towns|recommend|options to live|places to live)\b",
                lower,
            ):
                return False
        return True
    if "show me" in lower and ("towns" in lower or "places" in lower or "options" in lower):
        return True
    if "best value" in lower or "best places" in lower:
        return True
    if re.search(r"\bcare a lot about\b", lower):
        return True
    if "even if crime" in lower or ("even if" in lower and "crime" in lower):
        return True
    if "even if schools" in lower or "even if they have tradeoffs" in lower:
        return True
    if re.search(r"\bfind (?:me )?(?:coastal|north shore|south shore|family|safe|good|cheaper|affordable|towns|places)\b", lower):
        return True
    if re.search(r"\bgive me (?:family|good|cheaper|coastal|options)\b", lower):
        return True
    if re.search(r"\bi have (?:a )?\d+k?\s+budget\b", lower):
        return True
    if re.search(r"\bi have \d+ million\b", lower):
        return True
    if "million dollars max" in lower:
        return True
    if re.search(r"\bwhat can i realistically get\b", lower):
        return True
    if re.search(r"\bcommute between\b", lower):
        return True
    if "long commute" in lower:
        return True
    if re.search(r"\bi care only about\b", lower):
        return True
    if "ignore school and safety" in lower:
        return True
    if re.search(r"\bhigher[- ]crime\b", lower) and "compare" not in lower:
        return True
    if re.search(r"\bhigher-crime\b", lower):
        return True
    if re.search(r"\bweaker schools are acceptable\b", lower):
        return True
    if re.search(r"\baffordability is good but safety is weak\b", lower):
        return True
    if re.search(r"\bprice and commute only\b", lower):
        return True
    if re.search(r"\bignore schools\b", lower) and "only" in lower:
        return True
    if re.search(r"\bcommute should be\b", lower):
        return True
    if re.search(r"\bboth short commute and low cost\b", lower):
        return True
    if re.search(r"\bcoastal but not\b", lower):
        return True
    if re.search(r"\bunder one million\b", lower):
        return True
    if re.search(r"\bworking with \d+k\b", lower):
        return True
    if re.search(r"\bleave out towns above\b", lower):
        return True
    if re.search(r"\bremove inland towns\b", lower):
        return True
    if re.search(r"\b\d+ to \d+ minutes from boston\b", lower):
        return True
    if re.search(r"\bcommute band\b", lower):
        return True
    if re.search(r"\b45\+\s*minutes\b", lower) or re.search(r"\b45\+ minutes\b", lower):
        return True
    if re.search(r"\bbad safety\b", lower):
        return True
    if re.search(r"\blow-price options\b", lower):
        return True
    if re.search(r"\bnot top-ranked\b", lower):
        return True
    if re.search(r"\bmajor downsides\b", lower):
        return True
    if re.search(r"\bcheapest towns\b", lower):
        return True
    if re.search(r"\brank towns by\b", lower):
        return True
    if re.search(r"\bworst safety\b", lower):
        return True
    if re.search(r"\bclose enough to boston\b", lower):
        return True
    if re.search(r"\bwhich towns\b", lower) and any(w in lower for w in ("safe", "close", "affordable", "coastal")):
        return True
    if re.search(r"\bbeyond\s+\d+\s+minutes\b", lower):
        return True
    if re.search(r"\baffordability upside\b", lower):
        return True
    if re.search(r"\bgive me towns beyond\b", lower):
        return True
    if re.search(r"\bprioritize cheap towns\b", lower):
        return True
    if re.search(r"\bcommute capped at\b", lower):
        return True
    if re.search(r"\blow price and quick commute\b", lower):
        return True
    if re.search(r"\btrade commute time for\b", lower):
        return True
    if re.search(r"\bseaside towns\b", lower):
        return True
    if re.search(r"\beven if the school score is not great\b", lower):
        return True
    if re.search(r"\baccept weaker safety\b", lower):
        return True
    if re.search(r"\bignore school quality and focus on price\b", lower):
        return True
    if re.search(r"\blowest-priced towns\b", lower):
        return True
    if re.search(r"\beven if safety is bad\b", lower):
        return True
    if re.search(r"\bschools are not a strength\b", lower):
        return True
    if re.search(r"\blow-cost towns but warn\b", lower):
        return True
    if re.search(r"\bwould not normally rank at the top\b", lower):
        return True
    if re.search(r"\btradeoff-heavy\b", lower):
        return True
    if re.search(r"\bshow cheaper towns\b", lower):
        return True
    if re.search(r"\bshow lower-cost towns\b", lower):
        return True
    if re.search(r"\bshow practical options\b", lower):
        return True
    if re.search(r"\baffordable towns with obvious red flags\b", lower):
        return True
    if re.search(r"\bi need towns\b", lower):
        return True
    if re.search(r"\bhalf an hour or less\b", lower):
        return True
    if re.search(r"\binside a \d+[- ]minute\b", lower):
        return True
    if re.search(r"\b\d+[- ]minute boston commute\b", lower):
        return True
    if re.search(r"\bskip the close-in towns\b", lower):
        return True
    if re.search(r"\bwater-adjacent\b", lower):
        return True
    if re.search(r"\bsafe-ish towns\b", lower):
        return True
    if re.search(r"\bdo not want inland\b", lower):
        return True
    if re.search(r"\bokay with lower school\b", lower):
        return True
    if re.search(r"\bdo not factor schools\b", lower):
        return True
    if re.search(r"\bfast commute matters more\b", lower):
        return True
    if re.search(r"\bsecond-tier practical\b", lower):
        return True
    if re.search(r"\bcheap and close\b", lower):
        return True
    return False


def _has_semantic_signal(text: str) -> bool:
    lower = text.lower()
    if parse_constraints(text).similar_to_town:
        return True
    if any(p in lower for p in SEMANTIC_VIBE_PHRASES):
        return True
    if re.search(r"\b(?:like|similar to|something like|lower-cost version of)\s+[a-z]", lower):
        return True
    if re.search(r"\b(?:concord|newton|brookline|winchester|wellesley|westford)[\s-]+(?:vibes?|like)\b", lower):
        return True
    if re.search(r"\b(?:brookline|winchester|wellesley)[\s-]+like\b", lower):
        return True
    if re.search(r"\b(?:polished|calm suburb|historic town-center|educated family|low-drama)\b", lower):
        return True
    if re.search(r"\balternative\b", lower) and re.search(r"\b(?:cheaper|lower|price tag)\b", lower):
        return True
    if re.search(r"\benergy without\b", lower):
        return True
    if re.search(r"\bfeels somewhat similar\b", lower):
        return True
    if re.search(r"\b(?:wellesley|westford|brookline|winchester)[\s-]+style\b", lower):
        return True
    if re.search(r"\bsafe, calm, stable\b", lower):
        return True
    if re.search(r"\bmaximize value\b", lower):
        return True
    if re.search(r"\bold new england center\b", lower):
        return True
    if re.search(r"\btoo expensive;\s*what feels\b", lower):
        return True
    if re.search(r"\bgreat schools, but i accept\b", lower):
        return True
    if "connected to amenities" in lower:
        return True
    if re.search(r"\bcalm town\b", lower):
        return True
    if re.search(r"\bfamily-centered\b|\bfamily value\b", lower):
        return True
    if re.search(r"\bsafe, predictable\b", lower):
        return True
    if re.search(r"\bconnected enough\b", lower):
        return True
    if re.search(r"\bis\s+.+\s+(?:walkable|mountainous|touristy|sketchy|snobby|boring|rural|urban)\b", lower):
        return False
    if re.search(r"\bpay more if the schools\b", lower):
        return True
    if re.search(r"\bi want cheap first\b", lower):
        return True
    return False


def _is_compare_query(query: str, entities: ExtractedEntities) -> tuple[str, str] | None:
    if entities.compare_pair:
        return entities.compare_pair
    lower = query.lower()
    if len(entities.valid_towns) == 2 and has_comparison_relation(lower):
        return entities.valid_towns[0], entities.valid_towns[1]
    if "compare" in lower and len(entities.valid_towns) == 2:
        return entities.valid_towns[0], entities.valid_towns[1]
    return None


def _membership_town(text: str, entities: ExtractedEntities) -> str | None:
    if entities.valid_towns:
        return entities.valid_towns[0]
    if entities.unknown_town_candidates:
        return entities.unknown_town_candidates[0]
    for pattern in (
        re.compile(
            r"\b(?:do you cover|are you able to search|can you search|do you track|"
            r"do you recognize|can you answer questions about|can your system handle|"
            r"can the app answer|do you support)\s+([a-zA-Z][\w\s\-']+)",
            re.I,
        ),
        re.compile(
            r"\bis\s+([a-zA-Z][\w\s\-']+?)\s+(?:included|in\s+your|treated as|stored with|"
            r"mapped to|normalized to|recognized as|covered by|part of the suburb scope|"
            r"one of the 200|one of the towns you loaded|a town you track|covered|part of|"
            r"in the curated list)\b",
            re.I,
        ),
        re.compile(
            r"\bis\s+([a-zA-Z][\w\s\-']+?)\s+in\s+(?:your\s+)?(?:the\s+)?(?:list|dataset|data|curated)\b",
            re.I,
        ),
        re.compile(r'\bwould\s+"?([a-zA-Z][\w\s\-\']+)"?\s+resolve to\b', re.I),
        re.compile(r"\bis\s+([a-zA-Z][\w\s\-']+?)\s+in scope\b", re.I),
    ):
        match = pattern.search(text)
        if match:
            return clean_town_label(match.group(1))
    return None


def classify_user_intent(query: str) -> ClassifiedIntent:
    """Classify user intent — entity-first (Phase 1.4)."""
    text = query.strip()
    lower = text.lower()
    entities = extract_entities(text)
    known = entities.valid_towns
    unknown = entities.unknown_town_candidates

    if not text:
        return ClassifiedIntent(intent="unsupported", confidence=0.0, message="Empty query.")

    from app.lookup_schema import detect_unknown_field_lookup

    unknown_field = detect_unknown_field_lookup(text, entities)
    if unknown_field:
        town, match = unknown_field
        return _unsupported_field_lookup_intent(
            town,
            match.label,
            entities=entities,
            category=match.category,
            reason=f"single town + unsupported attribute ({match.label})",
        )

    if any(p in lower for p in DATA_LIMIT_PHRASES):
        return ClassifiedIntent(intent="data_limit_question", confidence=0.95)

    if FUTURE_YEAR_DATA_RE.search(text) and any(
        w in lower for w in ("crime", "price", "rate", "data", "listing")
    ):
        return ClassifiedIntent(intent="data_limit_question", confidence=0.95)

    if OUTSIDE_DATASET_RE.search(text) or RECOMMEND_IF_NOT_RE.search(text):
        return ClassifiedIntent(
            intent="refuse_out_of_scope",
            confidence=0.95,
            message=(
                "I can only recommend or compare towns in the curated 200-town suburbs.json list. "
                "I cannot suggest towns outside that dataset."
            ),
        )

    if re.search(r"\bbeyond massachusetts\b|\boutside massachusetts\b|\btowns beyond massachusetts\b", lower):
        return ClassifiedIntent(
            intent="refuse_out_of_scope",
            confidence=0.92,
            message="This dataset covers Boston-area Massachusetts towns only.",
            reason="out-of-state scope question",
        )

    if re.search(r"\b(?:cape cod|cape towns)\b", lower) and _has_membership_relation(lower):
        return ClassifiedIntent(
            intent="refuse_out_of_scope",
            confidence=0.92,
            message="Cape Cod/Cape towns are regions, not single towns in the curated 200-town dataset.",
            named_towns=known,
            unknown_towns=unknown,
            reason="region scope question",
        )

    if re.search(r"\bnon-massachusetts towns\b", lower) and "supported" in lower:
        return ClassifiedIntent(
            intent="refuse_out_of_scope",
            confidence=0.92,
            message="This dataset covers Boston-area Massachusetts towns only.",
            reason="non-MA scope",
        )

    if re.search(r"\btown is not loaded\b|\bwhen the town is not loaded\b", lower):
        return ClassifiedIntent(
            intent="refuse_out_of_scope",
            confidence=0.9,
            message="Towns outside the curated 200-town suburbs.json list cannot be answered with stored data.",
            reason="missing-town meta question",
        )

    if re.search(
        r"\btown that is missing\b|\bask about a (?:town that is )?missing\b|"
        r"\btown you don'?t cover\b",
        lower,
    ):
        return ClassifiedIntent(
            intent="refuse_out_of_scope",
            confidence=0.88,
            message=(
                "Towns not in the curated 200-town suburbs.json dataset are outside scope for "
                "recommendations and comparisons."
            ),
            reason="missing-town meta question",
        )

    if CAPE_COD_RE.search(text) and (_has_membership_relation(lower) or REGION_SCOPE_RE.search(text)):
        return ClassifiedIntent(
            intent="refuse_out_of_scope",
            confidence=0.92,
            message="Cape Cod is a region, not a single town in the curated 200-town dataset.",
            named_towns=known,
            unknown_towns=unknown,
            reason="region scope question",
        )

    if re.search(r"\brank towns by commute to\b", lower) and "not boston" in lower:
        return ClassifiedIntent(
            intent="needs_clarification",
            confidence=0.9,
            message="Commute data is to South Station, Boston only — not other workplaces.",
        )

    if "i work in westborough" in lower and "rank" in lower:
        return ClassifiedIntent(
            intent="needs_clarification",
            confidence=0.9,
            message="Commute data is to South Station, Boston only — not Westborough.",
        )

    if re.search(r"\b(?:i\s+)?work\s+(?:in|at)\s+", lower) and not _has_recommendation_ask(text):
        place = "your workplace"
        work = WORK_IN_RE.search(text)
        if work:
            place = clean_town_label(work.group(1))
        return ClassifiedIntent(
            intent="needs_clarification",
            confidence=0.88,
            message=(
                f"You mentioned {place}. Commute data is to South Station, Boston only. "
                "Tell me your budget, school/safety priorities, or towns to compare."
            ),
        )

    if re.search(r"\b(?:outside|excluded from|out of scope)\b", lower):
        if any(oos in lower for oos in OUT_OF_SCOPE_TOWNS):
            return ClassifiedIntent(
                intent="refuse_out_of_scope",
                confidence=0.95,
                message="That location is outside the curated Boston-area 200-town suburbs.json dataset.",
                named_towns=known,
                unknown_towns=unknown,
                reason="out-of-scope town with coverage question",
            )

    if re.search(r"\b(?:exclude|unavailable|reject)\s+(?:springfield|amherst|providence|nashua|brooklyn)\b", lower):
        return ClassifiedIntent(
            intent="refuse_out_of_scope",
            confidence=0.95,
            message="That location is outside the curated Boston-area 200-town suburbs.json dataset.",
            named_towns=known,
            unknown_towns=unknown,
            reason="explicit out-of-scope town exclusion question",
        )

    if any(oos in lower for oos in OUT_OF_SCOPE_TOWNS) and (
        _has_membership_relation(lower)
        or re.search(r"\b(?:exclude|outside|unavailable|reject|not massachusetts)\b", lower)
    ):
        if not _has_recommendation_ask(text):
            return ClassifiedIntent(
                intent="refuse_out_of_scope",
                confidence=0.95,
                message="That location is outside the curated Boston-area 200-town suburbs.json dataset.",
                named_towns=known,
                unknown_towns=unknown,
                reason="out-of-scope town with coverage question",
            )

    if re.search(r"\b(?:bring up|open)\b.+\bentry\b", lower) or re.search(
        r"\bentry from the suburb dataset\b", lower
    ):
        town = primary_town(entities)
        if town:
            return _lookup_intent(town, "summary", entities=entities, reason="suburb dataset entry")

    if _has_semantic_signal(text) and re.search(
        r"\b(?:too expensive|what feels|feels somewhat|feels like|without .+ pricing)\b",
        lower,
    ):
        if not re.search(r"\b(?:stored|dataset report|missing|classified as complete)\b", lower):
            return _recommend_intent(
                entities=entities,
                semantic=True,
                confidence=0.88,
                reason="semantic reference-town preference",
            )

    if is_open_ended_recommendation(text):
        return ClassifiedIntent(
            intent="needs_clarification",
            confidence=0.9,
            message=open_ended_clarification_message(),
            named_towns=known,
            unknown_towns=unknown,
            reason="open-ended recommendation without constraints",
        )

    if is_coastal_town_list_query(text):
        return _recommend_intent(
            entities=entities,
            semantic=False,
            confidence=0.9,
            reason="coastal town list query",
        )

    if is_scope_inclusion_lookup(text, entities):
        town = entities.valid_towns[0]
        return _lookup_intent(town, "dataset", entities=entities, reason="scope inclusion/exclusion lookup")

    if is_membership_supported_query(text):
        town = primary_town(entities) or resolve_typo_lookup_town(text, entities)
        if town:
            return _membership_intent(town, entities=entities, reason="supported/in-scope membership")

    multi_lookup_specs = detect_multi_town_lookup_specs(text)
    if multi_lookup_specs:
        return _lookup_multi_intent(
            multi_lookup_specs,
            entities=entities,
            reason=f"multi-town lookup: {', '.join(f'{s.town}/{s.field}' for s in multi_lookup_specs)}",
        )

    typo_town = resolve_typo_lookup_town(text, entities)
    if typo_town and _is_single_town_lookup(text, entities):
        field = _infer_lookup_field(lower)
        if is_multi_field_lookup(text):
            return _lookup_intent(
                typo_town,
                field,
                entities=entities,
                reason=f"typo single-town multi-field lookup ({field}+)",
            )
        return _lookup_intent(typo_town, field, entities=entities, reason=f"typo single-town lookup field={field}")

    multi_commute = detect_multi_commute_compare(text)
    if multi_commute:
        return _compare_intent(
            multi_commute[0],
            multi_commute[1],
            entities=entities,
            field="commute",
            reason=f"multi commute lookup compare: {multi_commute[0]} vs {multi_commute[1]}",
        )

    multi_compare_towns = extract_multi_compare_towns(entities, text)
    if multi_compare_towns:
        return _compare_multi_intent(
            multi_compare_towns,
            entities=entities,
            columns=infer_compare_table_columns(lower),
            reason=f"compare table for {len(multi_compare_towns)} towns",
        )

    compare_pair = _is_compare_query(text, entities)
    if compare_pair:
        field = entities.compare_field or _infer_lookup_field(lower)
        return _compare_intent(
            compare_pair[0],
            compare_pair[1],
            entities=entities,
            field=field,
            reason=f"compare: {compare_pair[0]} vs {compare_pair[1]} + {field or 'general'}",
        )

    if re.search(
        r"\b(?:if i type|will the app understand|are there records for|"
        r"can i use .+ as a town name|does the app know .+ means|"
        r"can you recognize|do you recognize|is .+ loaded)\b",
        lower,
    ):
        town = _membership_town(text, entities)
        return _membership_intent(town, entities=entities, reason="alias/spelling membership")

    if re.search(r"\bsearch for\b", lower):
        town = primary_town(entities)
        if town and not is_junk_town_candidate(town):
            return _lookup_intent(town, "summary", entities=entities, reason="search for town")

    if re.search(r"\bwhat school number is listed for\b", lower):
        town = primary_town(entities)
        if town:
            return _lookup_intent(town, "school", entities=entities, reason="school number listed")

    if re.search(r"\bwhat is missing from\b", lower) and re.search(r"\bdata profile\b", lower):
        town = primary_town(entities)
        if town:
            return _lookup_intent(town, "missing", entities=entities, reason="missing data profile")

    if _is_lookup_query(text, entities):
        town = primary_town(entities)
        if not town:
            for pattern in (
                POSSESSIVE_TOWN_RE, HOW_FAR_RE, HOW_EXPENSIVE_RE, COMMUTE_DATA_FOR_RE,
                TELL_ME_STORED_RE, COUNTY_REGION_RE, MISSING_INFO_RE, BASIC_STATS_RE,
                DATA_QUALITY_SUMMARY_RE, FULL_PARTIAL_RE, HAVE_HOUSING_RE, HAVE_SCHOOL_RE,
                MISSING_FIELDS_RE, MARKED_COASTAL_RE, IS_COASTAL_RE, COMMUTE_FOR_FLEX_RE,
                COMMUTE_FROM_RE, COMMUTE_TO_BOSTON_RE,
                re.compile(r"\bshow me the stored profile for\s+([a-zA-Z][\w\s\-']+)", re.I),
                re.compile(r"\bwhat does the dataset report for\s+([a-zA-Z][\w\s\-']+)", re.I),
                re.compile(r"\bwhat fields are unavailable for\s+([a-zA-Z][\w\s\-']+)", re.I),
                re.compile(r"\bhow many miles is\s+([a-zA-Z][\w\s\-']+?)\s+from", re.I),
                re.compile(r"\bhow close is\s+([a-zA-Z][\w\s\-']+?)\s+to", re.I),
                re.compile(r"\bpull facts for\s+([a-zA-Z][\w\s\-']+)", re.I),
                re.compile(r"\bopen\s+([a-zA-Z][\w\s\-']+?)'s suburb entry\b", re.I),
                re.compile(r"\bwhat numbers do you have saved for\s+([a-zA-Z][\w\s\-']+)", re.I),
                re.compile(r"\bdoes\s+([a-zA-Z][\w\s\-']+?)\s+have a recorded school metric\b", re.I),
                re.compile(r"\bis\s+([a-zA-Z][\w\s\-']+?)\s+classified as complete data\b", re.I),
                re.compile(r"\blook up\s+([a-zA-Z][\w\s\-']+)", re.I),
                re.compile(r"\bbased on your records, is\s+([a-zA-Z][\w\s\-']+)", re.I),
            ):
                match = pattern.search(text)
                if match:
                    town = clean_town_label(match.group(1))
                    break
        if town and not is_junk_town_candidate(town):
            field = _infer_lookup_field(lower)
            return _lookup_intent(town, field, entities=entities, reason=f"lookup relation field={field}")

    if re.search(r"\brecommendations possible\b", lower):
        town = _membership_town(text, entities)
        return _membership_intent(town, entities=entities, reason="recommendations possible scope")

    if (
        _has_membership_relation(lower)
        or ALIAS_SAME_RE.search(text)
        or FOXBORO_RE.search(text)
        or MARLBORO_OR_RE.search(text)
    ):
        town = _membership_town(text, entities)
        check_town = (town or "").lower()
        if (
            check_town in OUT_OF_SCOPE_TOWNS
            or "amherst" in lower
            or ("springfield" in lower and "outside" in lower)
        ):
            return ClassifiedIntent(
                intent="refuse_out_of_scope",
                confidence=0.95,
                message=f"{town or 'That town'} is outside the curated Boston-area 200-town suburbs.json dataset.",
                named_towns=known,
                unknown_towns=unknown,
            )
        if "brooklyn" in lower and "brookline" not in lower:
            return ClassifiedIntent(
                intent="refuse_out_of_scope",
                confidence=0.95,
                message="Brooklyn, MA is not in the curated 200-town suburbs.json dataset.",
            )
        if AMBIGUOUS_RE.search(text):
            return _lookup_intent("Manchester-by-the-Sea", "summary", entities=entities, reason="ambiguous alias")
        if CLOSEST_MATCHES_RE.search(text):
            m = CLOSEST_MATCHES_RE.search(text)
            typo = clean_town_label(m.group(1)) if m else "Unknown"
            return _lookup_intent(typo, "close_matches", entities=entities, reason="closest fuzzy match lookup")
        alias = ALIAS_SAME_RE.search(text)
        if alias:
            return _membership_intent(alias.group(1), entities=entities, reason="alias same-as question")
        return _membership_intent(town, entities=entities)

    if _has_semantic_signal(text) and not _is_lookup_query(text, entities):
        return _recommend_intent(entities=entities, semantic=True, confidence=0.88, reason="semantic/vibe signal")

    if (
        _has_lookup_field_signal(lower)
        and (known or unknown)
        and len(known) + len(unknown) == 1
        and not _has_recommendation_ask(text)
        and not _has_semantic_signal(text)
        and not re.search(r"\btowns\b", lower)
        and not re.search(r"\b(?:keep|drive time under)\b", lower)
    ):
        town = primary_town(entities)
        if town and not is_junk_town_candidate(town):
            field = _infer_lookup_field(lower)
            if is_multi_field_lookup(text):
                return _lookup_intent(
                    town,
                    field,
                    entities=entities,
                    reason="single town multi-field lookup",
                )
            return _lookup_intent(town, field, entities=entities, reason=f"single town + field={field}")

    if re.search(r"\bcommute for\s+", lower) or re.search(r"\bcommute from\s+", lower):
        town = primary_town(entities)
        if (
            town
            and not is_junk_town_candidate(town)
            and not _has_recommendation_ask(text)
            and not re.search(r"\bcommute capped at\b", lower)
            and not re.search(r"\bdrive time to boston\b", lower)
            and not re.search(r"\b(?:keep|drive time under)\b", lower)
        ):
            return _lookup_intent(town, "commute", entities=entities, reason="commute for/from pattern")

    if _has_recommendation_ask(text):
        return _recommend_intent(entities=entities, reason="recommendation language detected")

    constraints = parse_constraints(text)
    if constraints.safer_than_town or constraints.cheaper_than_town or constraints.quieter_than_town:
        return _recommend_intent(entities=entities, reason="relative town constraint")

    if re.search(r"\bin\s+[A-Za-z]+\s+county\b", text) and re.search(r"\b\d+\s*(?:mins?|minutes)\b", lower):
        return _recommend_intent(entities=entities, reason="county + commute filter")

    if constraints.budget_max is not None or constraints.min_commute_minutes is not None:
        return _recommend_intent(entities=entities, reason="parsed budget/commute constraints")

    if constraints.max_commute_minutes is not None and re.search(r"\bcommute\b", lower):
        return _recommend_intent(entities=entities, reason="parsed max commute constraint")

    return ClassifiedIntent(
        intent="unsupported",
        confidence=0.4,
        named_towns=known,
        unknown_towns=unknown,
        reason="no structural match",
    )


def route_intent_matches(classified: ClassifiedIntent, route_intent: str) -> bool:
    """True when router intent aligns with classified intent."""
    if classified.intent == "refuse_out_of_scope":
        return route_intent in ("unsupported", "needs_clarification", "data_limit_question")
    if classified.intent == "dataset_membership":
        return route_intent == "lookup_single_town"
    if classified.intent == "data_limit_question":
        return route_intent in ("data_limit_question", "unsupported", "lookup_single_town")
    if classified.intent == "needs_clarification":
        return route_intent == "needs_clarification"
    if classified.intent == route_intent:
        return True
    if classified.intent == "lookup_multi_town" and route_intent == "lookup_multi_town":
        return True
    if classified.intent == "compare_multi_town" and route_intent == "compare_multi_town":
        return True
    if classified.intent == "recommend_structured" and route_intent == "recommend_semantic":
        return True
    if classified.intent == "recommend_semantic" and route_intent == "recommend_structured":
        return True
    return False
