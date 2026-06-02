"""Entity-first town extraction for Phase 1.4 routing."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

from app.config import SUBURBS_JSON_PATH
from app.constraint_parser import extract_town_mentions
from app.town_normalizer import (
    TOWN_ALIASES,
    canonical_town_name,
    normalize_key,
    resolve_town_in_dataset,
)

# Words that look like town names but are not
_NON_TOWN_TOKENS = frozenset({
    "more", "less", "better", "worse", "which", "what", "does", "would", "could",
    "should", "between", "compare", "coastal", "inland", "complete", "housing",
    "data", "everything", "anything", "something", "recommendations",
    "recommendation", "search", "track", "support", "recognize", "treated",
    "stored", "included", "covered", "dataset", "list", "scope", "towns", "town",
    "places", "options", "results", "schools", "safety", "crime", "commute",
    "price", "affordable", "expensive", "dangerous", "family", "friendly",
    "longer", "shorter", "cheaper", "stronger", "weaker", "marked", "considered",
    "pull", "give", "tell", "know", "show", "find", "rank", "exclude",
    "your system", "the app", "the system", "records", "queries", "coverage",
    "missing", "curated", "normalized", "mapped", "resolve", "handle", "loaded",
    "suburb scope", "non-massachusetts", "cape towns", "cape cod",
    "boston", "south station", "keep", "bring", "open", "skip", "fast",
    "quiet", "calm", "show", "give", "pull", "too", "also", "still",
    "lowest", "highest", "ocean-adjacent", "ocean", "waterfront", "practical",
    "tradeoff", "secondary", "rankable", "queryable", "usable", "available",
})

_LIST_QUERY_RE = re.compile(
    r"\b(?:towns|places|suburbs|options|recommendations|choices)\b",
    re.I,
)
_COMMUTE_LIST_RE = re.compile(
    r"\b(?:\d+\s*[-–]?\s*\d*\s*(?:minute|min)|commute|drive time|half an hour|hour or less)\b.*\bboston\b"
    r"|\bboston\b.*\b(?:commute|minutes|drive)\b",
    re.I,
)

# Prefix/suffix junk to strip from captured spans
_SPAN_PREFIX_RE = re.compile(
    r"^(?:about|on|for|in|at|to|from|me|is|are|does|do|the|a|an|"
    r"commute from|commute to|pull up|tell me|give me|what do you know about|everything you know about|"
    r"data profile for|the data profile for|questions about|search|track|"
    r"support recommendations for|recommendations for|able to search)\s+",
    re.I,
)
_SPAN_SUFFIX_RE = re.compile(
    r"\s+(?:marked as|considered|for commute(?: and safety)?|for schools?(?: and safety)?|"
    r"inland or coastal|in your data|in the dataset|in your list|in the 200[- ]town scope|"
    r"one of the 200 towns|a town you track|a coast town|have complete housing data|"
    r"have a high or low crime score|have good schools|expensive|included|"
    r"covered|stored with hyphens|treated as .+?|the same as .+? in your data).*$",
    re.I,
)

# Compare pair patterns (capture groups are town spans)
_COMPARE_AND_RE = re.compile(
    r"\bcompare\s+(.+?)\s+and\s+(.+?)(?:\s+for\s+[\w\s]+)?(?:\?|$|,|\.)",
    re.I,
)
_COMPARE_WITH_RE = re.compile(
    r"\bcompare\s+(.+?)\s+with\s+(.+?)(?:\?|$|,|\.)",
    re.I,
)
_COMPARED_WITH_COLON_RE = re.compile(
    r"\b(.+?)\s+compared with\s+(.+?)\s*:",
    re.I,
)
_FOR_FAMILY_OR_RE = re.compile(
    r"\bfor\s+(?:a\s+)?family,?\s*(.+?)\s+or\s+(.+?)(?:\?|$)",
    re.I,
)
_FARTHER_THAN_RE = re.compile(
    r"\bis\s+(.+?)\s+farther\s+from\b.+\s+than\s+(.+?)(?:\?|$)",
    re.I,
)
_LOSE_TO_ON_RE = re.compile(
    r"\bdoes\s+(.+?)\s+lose to\s+(.+?)\s+on\b",
    re.I,
)
_OR_IF_I_CARE_RE = re.compile(
    r"\b(.+?)\s+or\s+(.+?)\s+if\s+i\s+care\b",
    re.I,
)
_OR_FOR_GETTING_RE = re.compile(
    r"\b(.+?)\s+or\s+(.+?)\s+for\s+getting\b",
    re.I,
)
_OR_FOR_LIVABILITY_RE = re.compile(
    r"\b(.+?)\s+or\s+(.+?)\s+for\s+(?:family\s+)?livability\b",
    re.I,
)
_TOWN_OR_COLON_RE = re.compile(
    r"^(.+?)\s+or\s+(.+?)\s*:\s*",
    re.I,
)
_TOWN_OR_FOR_FIELD_RE = re.compile(
    r"^(.+?)\s+or\s+(.+?)\s+for\s+(?:low crime|safety|affordability|families|overall|overall value|getting|commute|schools?|price)\b",
    re.I,
)
_TOWN_OR_FOR_RE = re.compile(
    r"^(.+?)\s+or\s+(.+?)\s+for\s+",
    re.I,
)
_TOWN_FIRST_OR_DASH_RE = re.compile(
    r"^(.+?)\s+or\s+(.+?)\s*[—\-]\s*which\b",
    re.I,
)
_TOWN_VERSUS_SIMPLE_RE = re.compile(
    r"\b(.+?)\s+versus\s+(.+?)(?:\s+for\s+|\?|$)",
    re.I,
)
_TOWN_VERSUS_RE = re.compile(
    r"\b(.+?)\s+versus\s+(.+?)\s*:\s*which\b",
    re.I,
)
_FOR_FIELD_OR_RE = re.compile(
    r"\bfor\s+(?:commute|safety|schools?|price|affordability),?\s*(.+?)\s+or\s+(.+?)(?:\?|$)",
    re.I,
)
_SHOULD_PICK_OR_RE = re.compile(
    r"\bshould\s+i\s+pick\s+(.+?)\s+or\s+(.+?)(?:\?|$)",
    re.I,
)
_IS_BETTER_THAN_RE = re.compile(
    r"\bis\s+(.+?)\s+better than\s+(.+?)\s+for\b",
    re.I,
)
_WINS_ON_RE = re.compile(
    r"\bbetween\s+(.+?)\s+and\s+(.+?),\s*who wins\b",
    re.I,
)
_BETWEEN_AND_RE = re.compile(
    r"\bbetween\s+(.+?)\s+and\s+(.+?)(?:,\s*which|\?|$)",
    re.I,
)
_OR_COMPARE_RE = re.compile(
    r"\b(?:would|should|is|does)\s+(.+?)\s+or\s+(.+?)\s+(?:be|have|cost|beat|is)",
    re.I,
)
_WHICH_TOWN_OR_RE = re.compile(
    r"\bwhich(?:\s+town|\s+one)?\s+(?:has|is|has the)\s+[^,]+,\s*(.+?)\s+or\s+(.+?)(?:\?|$)",
    re.I,
)
_WHICH_OR_RE = re.compile(
    r"\bwhich(?:\s+one|\s+town|\s+is)?\s+[^,]*,\s*(.+?)\s+or\s+(.+?)(?:\?|$)",
    re.I,
)
_IS_SAFER_THAN_RE = re.compile(
    r"\bis\s+(.+?)\s+safer than\s+(.+?)(?:\?|$)",
    re.I,
)
_IS_CHEAPER_THAN_RE = re.compile(
    r"\bis\s+(.+?)\s+cheaper than\s+(.+?)(?:\?|$)",
    re.I,
)
_MORE_THAN_RE = re.compile(
    r"\b(?:is|does)\s+(.+?)\s+(?:more|less)\s+(?:dangerous|safe|affordable|expensive|coastal|family-friendly)\s+than\s+(.+?)(?:\?|$)",
    re.I,
)
_COST_MORE_RE = re.compile(
    r"\bdoes\s+(.+?)\s+cost\s+more\s+than\s+(.+?)(?:\?|$)",
    re.I,
)
_BEAT_FOR_RE = re.compile(
    r"\bdoes\s+(.+?)\s+beat\s+(.+?)\s+for\b",
    re.I,
)
_WOULD_OR_BETTER_RE = re.compile(
    r"\bwould\s+(.+?)\s+or\s+(.+?)\s+be\s+(?:better|more)\b",
    re.I,
)
_TOWN_OR_TOWN_TAIL_RE = re.compile(
    r"\b([A-Za-z][\w\s\-']+?)\s+or\s+([A-Za-z][\w\s\-']+?)(?:\?|$|,|\.)",
    re.I,
)
_VS_FOR_RE = re.compile(
    r"\b(.+?)\s+vs\.?\s+(.+?)\s+for\b",
    re.I,
)
_WHICH_COSTS_MORE_RE = re.compile(
    r"\bwhich costs more,?\s*(.+?)\s+or\s+(.+?)(?:\?|$)",
    re.I,
)
_WHICH_GETS_FASTER_RE = re.compile(
    r"\bwhich gets to boston faster,?\s*(.+?)\s+or\s+(.+?)(?:\?|$)",
    re.I,
)
_IF_VALUE_OR_RE = re.compile(
    r"\bif value matters,?\s*(.+?)\s+or\s+(.+?)(?:\?|$)",
    re.I,
)
_PRICE_ADVANTAGE_RE = re.compile(
    r"\bdoes\s+(.+?)\s+have a price advantage over\s+(.+?)(?:\?|$)",
    re.I,
)
_COMPARED_WITH_RE = re.compile(
    r"\b(.+?)\s+compared with\s+(.+?)(?:\?|$|\.|,)",
    re.I,
)

COMPARISON_RELATION_TOKENS: tuple[str, ...] = (
    "between",
    " vs ",
    " vs. ",
    "which has",
    "which is",
    "which one",
    "which town",
    "would ",
    " beat ",
    " beats ",
    "better",
    "worse",
    "safer",
    "less safe",
    "more dangerous",
    "more dangerous than",
    "cheaper",
    "more affordable",
    "more expensive",
    "cost more",
    "cost more than",
    "lower crime",
    "higher crime",
    "better schools",
    "stronger schools",
    "weaker schools",
    "shorter commute",
    "longer commute",
    "better value",
    "family-friendly",
    "more family-friendly",
    "more coastal",
    "stronger profile",
    "less safe than",
    " versus ",
    "who wins",
    "which is pricier",
    "which is longer",
    "should i pick",
    "looks better",
    "stronger for",
    "lose to",
    "farther from",
    "compared with",
    "livability",
    "getting into boston",
    "costs more",
    "price advantage",
    "gets to boston faster",
)


class ExtractedEntities(BaseModel):
    """Structured entities extracted from a user query."""

    valid_towns: list[str] = Field(default_factory=list)
    unknown_town_candidates: list[str] = Field(default_factory=list)
    aliases_used: dict[str, str] = Field(default_factory=dict)
    fuzzy_matches: dict[str, str] = Field(default_factory=dict)
    raw_spans: list[str] = Field(default_factory=list)
    cleaned_spans: dict[str, str] = Field(default_factory=dict)
    compare_pair: tuple[str, str] | None = None
    compare_field: str | None = None


@lru_cache(maxsize=1)
def _dataset_towns() -> tuple[str, ...]:
    import json

    with open(SUBURBS_JSON_PATH, encoding="utf-8") as f:
        suburbs = json.load(f)
    return tuple(s["name"] for s in suburbs)


def is_junk_town_candidate(name: str) -> bool:
    """True when a span should not drive lookup/membership routing."""
    key = normalize_key(name)
    if not key or key in _NON_TOWN_TOKENS:
        return True
    if key in ("boston", "south station", "keep", "bring", "open", "skip"):
        return True
    return len(key) < 3


def _sanitize_entities_for_query(entities: ExtractedEntities, query: str) -> None:
    """Drop destination words and list-query false positives."""
    lower = query.lower()
    is_list = bool(_LIST_QUERY_RE.search(lower)) or bool(_COMMUTE_LIST_RE.search(lower))

    def _keep(town: str) -> bool:
        if is_junk_town_candidate(town):
            return False
        if is_list and normalize_key(town) in ("boston", "south station"):
            return False
        return True

    entities.valid_towns = [t for t in entities.valid_towns if _keep(t)]
    entities.unknown_town_candidates = [
        u for u in entities.unknown_town_candidates if _keep(u)
    ]


def clean_entity_span(raw: str) -> str:
    """Normalize a captured town span to a canonical dataset name when possible."""
    text = raw.strip().strip(".,;:!?\"'")
    text = re.sub(r"['\u2019]s\b", "", text, flags=re.I)
    text = _SPAN_PREFIX_RE.sub("", text)
    text = _SPAN_SUFFIX_RE.sub("", text)
    text = re.sub(r"\s+(please|thanks|today)\b.*$", "", text, flags=re.I)
    text = re.sub(
        r"\s+for\s+(?:commute|safety|schools?|price|affordability|school score).*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s+(but|with|and|under|over|in|on|near)\b.*$", "", text, flags=re.I)
    text = text.strip()
    if not text or normalize_key(text) in _NON_TOWN_TOKENS:
        return ""
    canonical = canonical_town_name(text)
    resolved = resolve_town_in_dataset(canonical, list(_dataset_towns()))
    return resolved or canonical


def _resolve_span(raw: str, entities: ExtractedEntities) -> str | None:
    cleaned = clean_entity_span(raw)
    if not cleaned:
        return None
    key = normalize_key(cleaned)
    if key in _NON_TOWN_TOKENS:
        return None
    entities.raw_spans.append(raw)
    entities.cleaned_spans[raw] = cleaned
    towns = _dataset_towns()
    resolved = resolve_town_in_dataset(cleaned, list(towns))
    if resolved:
        if normalize_key(cleaned) != normalize_key(resolved):
            if normalize_key(cleaned) in {normalize_key(a) for a in TOWN_ALIASES.get(resolved, [])}:
                entities.aliases_used[cleaned] = resolved
            else:
                entities.fuzzy_matches[cleaned] = resolved
        if resolved not in entities.valid_towns:
            entities.valid_towns.append(resolved)
        return resolved
    if cleaned not in entities.unknown_town_candidates:
        entities.unknown_town_candidates.append(cleaned)
    return cleaned


def _has_comparison_relation(lower: str) -> bool:
    if re.search(
        r"\bis\s+.+\s+(?:a\s+)?(?:safer|riskier|better|worse)\s+or\s+(?:safer|riskier|better|worse)\b",
        lower,
    ):
        return False
    if re.search(r"\b\d+\s+minutes?\s+or\s+more\b", lower):
        return False
    if re.search(r"\bcommute between\s+\d+\s+and\s+\d+\s+minutes\b", lower):
        return False
    if re.search(r"\bbetween\s+\d+\s+and\s+\d+\s+minutes\b", lower):
        return False
    if "compare" in lower:
        return True
    if re.search(r"\b(?:more|less|better|worse)\s+\w+\s+than\b", lower):
        return True
    if re.search(r"\b(?:is|does)\s+.+\s+(?:safer|cheaper|more expensive|more dangerous|more affordable|less safe)\s+than\b", lower):
        return True
    if re.search(r"\bdoes\s+.+\s+cost\s+more\s+than\b", lower):
        return True
    if re.search(r"\bdoes\s+.+\s+beat\s+.+\s+for\b", lower):
        return True
    if re.search(r"\bbetween\s+.+\s+and\s+.+\s*,?\s*which\b", lower):
        return True
    if re.search(r"\bwould\s+.+\s+or\s+.+\s+be\b", lower):
        return True
    if re.search(r"\bwhich(?:\s+one|\s+town|\s+is)\s+[^?]*\bor\b", lower):
        return True
    if re.search(r"\bwhich\s+(?:has|town has)\s+the\s+(?:longer|shorter)\b", lower):
        return True
    if re.search(r"\bshould\s+i\s+pick\b", lower) and " or " in lower:
        return True
    if re.search(r"\bwho wins\b", lower) and "between" in lower:
        return True
    if re.search(r"\bversus\b", lower):
        return True
    if re.search(r"\bor\s+.+\s*[—\-]\s*which\b", lower):
        return True
    if re.search(r"\bfor\s+commute,\s+.+\s+or\s+", lower):
        return True
    if re.search(r"\bfor\s+(?:a\s+)?family,?\s+.+\s+or\s+", lower):
        return True
    if re.search(r"\blose to\b", lower) and " on " in lower:
        return True
    if re.search(r"\bfarther from\b", lower) and " than " in lower:
        return True
    if re.search(r"\bcompared with\b", lower):
        return True
    if re.search(r"\bor\s+.+\s+if\s+i\s+care\b", lower):
        return True
    if re.search(r"\bor\s+.+\s+for\s+getting\b", lower):
        return True
    if re.search(r"\bor\s+.+\s+for\s+(?:family\s+)?livability\b", lower):
        return True
    if re.search(r"^.+\s+or\s+.+:\s*", lower):
        return True
    if re.search(
        r"^.+\s+or\s+.+\s+for\s+(?:low crime|safety|affordability|families|overall|commute|schools?|price)\b",
        lower,
    ):
        return True
    if re.search(r"\bsafety-wise,\s+.+\s+or\s+", lower):
        return True
    if re.search(r"\bfamily fit:\s+.+\s+or\s+", lower):
        return True
    if re.search(r"\bfor affordability,\s+.+\s+or\s+", lower):
        return True
    return any(token in lower for token in COMPARISON_RELATION_TOKENS)


def _infer_compare_field(lower: str) -> str | None:
    if "school" in lower:
        return "schools"
    if "commute" in lower or "drive" in lower:
        return "commute"
    if "crime" in lower or "dangerous" in lower or "safe" in lower or "safety" in lower:
        return "safety"
    if "price" in lower or "afford" in lower or "expensive" in lower or "cost" in lower:
        return "price"
    if "coastal" in lower:
        return "coastal"
    if "family" in lower:
        return "family"
    return None


def _town_keys_in_dataset() -> frozenset[str]:
    return frozenset(normalize_key(t) for t in _dataset_towns())


def _both_towns_in_dataset(a: str, b: str) -> bool:
    keys = _town_keys_in_dataset()
    return normalize_key(a) in keys and normalize_key(b) in keys


def _pair_from_two_valid_towns(entities: ExtractedEntities) -> tuple[str, str] | None:
    if len(entities.valid_towns) == 2:
        return entities.valid_towns[0], entities.valid_towns[1]
    return None


def _try_compare_pair_from_patterns(query: str, entities: ExtractedEntities) -> tuple[str, str] | None:
    lower = query.lower()
    if re.search(
        r"\b(?:downtown .+ safer than|safer than the outskirts|safer than outskirts)\b",
        lower,
    ) and len(entities.valid_towns) == 1:
        return None
    if not _has_comparison_relation(lower):
        return None

    for pattern in (
        _COMPARE_AND_RE,
        _COMPARE_WITH_RE,
        _COMPARED_WITH_COLON_RE,
        _FOR_FAMILY_OR_RE,
        _FARTHER_THAN_RE,
        _LOSE_TO_ON_RE,
        _OR_IF_I_CARE_RE,
        _OR_FOR_GETTING_RE,
        _OR_FOR_LIVABILITY_RE,
        _VS_FOR_RE,
        _WHICH_COSTS_MORE_RE,
        _WHICH_GETS_FASTER_RE,
        _IF_VALUE_OR_RE,
        _PRICE_ADVANTAGE_RE,
        _COMPARED_WITH_RE,
        _BETWEEN_AND_RE,
        _WINS_ON_RE,
        _TOWN_OR_COLON_RE,
        _TOWN_OR_FOR_FIELD_RE,
        _TOWN_OR_FOR_RE,
        _TOWN_FIRST_OR_DASH_RE,
        _TOWN_VERSUS_SIMPLE_RE,
        _TOWN_VERSUS_RE,
        _FOR_FIELD_OR_RE,
        _SHOULD_PICK_OR_RE,
        _IS_BETTER_THAN_RE,
        _WHICH_TOWN_OR_RE,
        _WHICH_OR_RE,
        _IS_SAFER_THAN_RE,
        _IS_CHEAPER_THAN_RE,
        _MORE_THAN_RE,
        _COST_MORE_RE,
        _BEAT_FOR_RE,
        _WOULD_OR_BETTER_RE,
        _OR_COMPARE_RE,
    ):
        match = pattern.search(query)
        if match:
            a = _resolve_span(match.group(1), entities)
            b = _resolve_span(match.group(2), entities)
            if a and b and normalize_key(a) != normalize_key(b):
                if _both_towns_in_dataset(a, b):
                    return a, b
                fallback = _pair_from_two_valid_towns(entities)
                if fallback:
                    return fallback

    fallback = _pair_from_two_valid_towns(entities)
    if fallback and _has_comparison_relation(lower):
        return fallback

    if len(entities.valid_towns) > 2:
        return None

    if re.search(r"\b(?:which|would|better|more|less|safer)\b", lower):
        match = _TOWN_OR_TOWN_TAIL_RE.search(query)
        if match:
            a = _resolve_span(match.group(1), entities)
            b = _resolve_span(match.group(2), entities)
            if a and b and normalize_key(a) != normalize_key(b):
                if _both_towns_in_dataset(a, b):
                    return a, b
                fallback = _pair_from_two_valid_towns(entities)
                if fallback:
                    return fallback

    return None


def _merge_known_towns(entities: ExtractedEntities, known: list[str], unknown: list[str]) -> None:
    for town in known:
        if town not in entities.valid_towns:
            entities.valid_towns.append(town)
    for town in unknown:
        cleaned = clean_entity_span(town)
        if not cleaned:
            continue
        resolved = resolve_town_in_dataset(cleaned, list(_dataset_towns()))
        if resolved:
            if resolved not in entities.valid_towns:
                entities.valid_towns.append(resolved)
            if normalize_key(cleaned) != normalize_key(resolved):
                entities.fuzzy_matches[cleaned] = resolved
        elif cleaned not in entities.unknown_town_candidates:
            entities.unknown_town_candidates.append(cleaned)


def _dedupe_embedded_towns(towns: list[str]) -> list[str]:
    """Drop shorter town names embedded in longer ones (e.g. Reading inside North Reading)."""
    if len(towns) <= 1:
        return towns
    kept: list[str] = []
    for town in sorted(towns, key=len, reverse=True):
        key = normalize_key(town)
        embedded = False
        for other in kept:
            other_key = normalize_key(other)
            if key != other_key and re.search(rf"\b{re.escape(key)}\b", other_key):
                embedded = True
                break
        if not embedded:
            kept.append(town)
    return kept


def _dedupe_unknown_against_valid(entities: ExtractedEntities) -> None:
    valid_keys = {normalize_key(t) for t in entities.valid_towns}
    filtered: list[str] = []
    for candidate in entities.unknown_town_candidates:
        cleaned = clean_entity_span(candidate)
        resolved = resolve_town_in_dataset(cleaned, list(_dataset_towns()))
        if resolved:
            if resolved not in entities.valid_towns:
                entities.valid_towns.append(resolved)
            if normalize_key(cleaned) != normalize_key(resolved):
                entities.fuzzy_matches[cleaned] = resolved
            continue
        if normalize_key(candidate) not in valid_keys:
            filtered.append(candidate)
    # Drop unknown fragments already resolved via a longer span (e.g. Manchster -> Manchester-by-the-Sea).
    for raw, cleaned in entities.cleaned_spans.items():
        if cleaned in entities.valid_towns or normalize_key(cleaned) in valid_keys:
            filtered = [
                u for u in filtered
                if u.lower() not in raw.lower() and raw.lower() not in u.lower()
            ]
    entities.unknown_town_candidates = filtered
    entities.valid_towns = _dedupe_embedded_towns(entities.valid_towns)


def extract_entities(query: str) -> ExtractedEntities:
    """Extract towns, aliases, and optional compare pairs from a query."""
    text = query.strip()
    entities = ExtractedEntities()

    known, unknown = extract_town_mentions(text)
    _merge_known_towns(entities, known, unknown)

    # Explicit span patterns for lookup/membership phrasing
    span_patterns = (
        r"(?:show me the stored profile for|what does the dataset report for|"
        r"pull up everything you know about|what do you know about|"
        r"give me the data profile for|tell me if|tell me about|tell me whether|"
        r"what fields are unavailable for|summarize)\s+([A-Za-z][\w\s\-']+)",
        r"\b(?:give me|pull)\s+([A-Za-z][\w\s\-']+?)'s\b",
        r"(?:can you answer questions about|are you able to search|can you search|"
        r"can your system handle|do you track|do you recognize|"
        r"do you support|can the app answer)\s+([A-Za-z][\w\s\-']+)",
        r"(?:is|are)\s+([A-Za-z][\w\s\-']+?)\s+(?:in the curated list|covered by|"
        r"part of the suburb scope|one of the towns you loaded|"
        r"normalized to|recognized as|mapped to|treated as|stored with|"
        r"in the 200[- ]town scope|one of the 200 towns|a town you track)\b",
        r"\bwhat (?:price|commute|safety rating) do you have for\s+([A-Za-z][\w\s\-']+)",
        r"\bwhat is the school (?:rating|percentile) (?:for|does)\s+([A-Za-z][\w\s\-']+)",
        r"\bhow many miles is\s+([A-Za-z][\w\s\-']+?)\s+from\b",
        r"\bhow close is\s+([A-Za-z][\w\s\-']+?)\s+to\b",
        r"\bdo you know\s+([A-Za-z][\w\s\-']+?)'s\b",
        r"\bwhat is\s+([A-Za-z][\w\s\-']+?)'s\b",
        r"\bpull facts for\s+([A-Za-z][\w\s\-']+)",
        r"\bis\s+([A-Za-z][\w\s\-']+?)\s+expensive\b",
        r"\bdoes\s+([A-Za-z][\w\s\-']+?)\s+have a school score\b",
        r"\bwhat is\s+([A-Za-z][\w\s\-']+?)'s safety score\b",
        r"\blook up\s+([A-Za-z][\w\s\-']+)",
        r"\bcan you find\s+([A-Za-z][\w\s\-']+)",
        r"\bopen\s+([A-Za-z][\w\s\-']+?)'s\s+suburb entry\b",
        r"\bis\s+([A-Za-z][\w\s\-']+?)\s+in scope\b",
        r"\bis\s+([A-Za-z][\w\s\-']+?)\s+near the coast\b",
        r"\b(.+?)\s+vs\.?\s+(.+?)\s+for\s+schools\b",
    )
    for pat in span_patterns:
        for match in re.finditer(pat, text, re.I):
            if match.lastindex and match.lastindex >= 2:
                for idx in range(1, match.lastindex + 1):
                    span = match.group(idx)
                    if re.search(r"\bnot\b", span, re.I):
                        continue
                    _resolve_span(span, entities)
                continue
            span = match.group(1)
            if re.search(r"\bnot\b", span, re.I):
                continue
            _resolve_span(span, entities)

    pair = _try_compare_pair_from_patterns(text, entities)
    if pair:
        entities.compare_pair = pair
        entities.compare_field = _infer_compare_field(text.lower())

    _dedupe_unknown_against_valid(entities)
    _sanitize_entities_for_query(entities, text)
    return entities


def has_comparison_relation(query: str) -> bool:
    return _has_comparison_relation(query.lower())


def primary_town(entities: ExtractedEntities) -> str | None:
    if entities.valid_towns:
        return entities.valid_towns[0]
    if entities.unknown_town_candidates:
        return entities.unknown_town_candidates[0]
    return None
