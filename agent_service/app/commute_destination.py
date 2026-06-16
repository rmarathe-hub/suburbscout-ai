"""Commute destination detection — Phase 8.5 dynamic dataset-town destinations."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.commute_service import (
    BOSTON_LABEL,
    commute_destination_label,
    dataset_town_names,
    dynamic_commute_available,
    is_boston_destination,
    resolve_dataset_town,
)
from app.entity_extractor import ExtractedEntities, extract_entities
from app.lookup_schema import AVAILABLE_FIELDS_BLURB

DEFAULT_DESTINATION_KEY = "boston_south_station"

_BOSTON_ALIASES = (
    r"\bboston\b",
    r"\bsouth station\b",
    r"\bdowntown boston\b",
)

_WORK_IN_RE = re.compile(
    r"\b(?:i\s+)?work\s+(?:in|at|near|around)\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_JOB_IN_RE = re.compile(
    r"\b(?:my\s+)?job\s+is\s+in\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_OFFICE_IN_RE = re.compile(
    r"\b(?:my\s+)?office\s+is\s+in\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_OFFICE_NEAR_RE = re.compile(
    r"\b(?:my\s+)?office\s+is\s+near\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_COMMUTE_INTO_RE = re.compile(
    r"\bcommut(?:e|ing)\s+into\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_GET_TO_FOR_WORK_RE = re.compile(
    r"\bget\s+to\s+([a-zA-Z][\w\s\-']+?)\s+for\s+work\b",
    re.I,
)
_MINUTES_OF_RE = re.compile(
    r"\b(?:within|under|below|less than|max|up to)\s+\d+\s*(?:mins?|minutes)\s+of\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_MINUTES_TO_TOWN_RE = re.compile(
    r"\b(?:within|under|below|less than|max|up to)\s+\d+\s*(?:mins?|minutes)\s+to\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_TOWN_WITHIN_MINUTES_RE = re.compile(
    r"\b([A-Z][a-zA-Z\-']+(?:\s+[A-Z][a-zA-Z\-']+)*)\s+within\s+\d+\s*(?:mins?|minutes)\b",
    re.I,
)
_COMMUTE_TO_RE = re.compile(
    r"\bcommut(?:e|ing)\s+to\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_WHERE_TOWN_COMMUTE_RE = re.compile(
    r"\bwhere\s+([a-zA-Z][\w\-']+(?:\s+[a-zA-Z][\w\-']+)*)\s+commute\s+is\b",
    re.I,
)
_TOWN_COMMUTE_RE = re.compile(
    r"\b([A-Z][a-zA-Z\-']+(?:\s+[A-Z][a-zA-Z\-']+)*)\s+commute\s+(?:is\s+)?(?:under|below|less than)\b",
    re.I,
)
_TOWN_DRIVE_RE = re.compile(
    r"\b([A-Z][a-zA-Z\-']+(?:\s+[A-Z][a-zA-Z\-']+)*)\s+drive\s+(?:under|below|less than)\b",
    re.I,
)
_TOWN_MINUTES_COMMUTE_RE = re.compile(
    r"\b([A-Z][a-zA-Z\-']+(?:\s+[A-Z][a-zA-Z\-']+)*)\s+under\s+\d+\s*min(?:ute)?s?(?:\s+commute)?",
    re.I,
)
_COMMUTE_INTO_COMPARE_RE = re.compile(
    r"\b(?:commut(?:e|ing)\s+into|getting\s+into)\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_PHRASE_SEPARATOR_RE = re.compile(
    r"\b(?:and|with|under|from|more\s+than|for|that|who|where|if|but|within)\b|[,.;!?]",
    re.I,
)
_HOW_FAR_FROM_RE = re.compile(
    r"\bhow far is\s+[a-zA-Z][\w\s\-']+?\s+from\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_DISTANCE_FROM_RE = re.compile(
    r"\bdistance from\s+[a-zA-Z][\w\s\-']+?\s+to\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_TO_DEST_RE = re.compile(
    r"\bfrom\s+([a-zA-Z][\w\s\-']+?)\s+to\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_COMMUTE_FROM_TO_RE = re.compile(
    r"\bcommut(?:e|ing)\s+from\s+([a-zA-Z][\w\s\-']+?)\s+to\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_FOR_COMMUTE_TO_RE = re.compile(
    r"\bfor\s+commut(?:e|ing)\s+to\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)


@dataclass(frozen=True)
class CommuteDestinationResult:
    """Detected commute destination for a query."""

    destination_town: str | None
    label: str
    is_default: bool
    in_dataset: bool
    data_available: bool
    mention: str | None = None
    key: str = DEFAULT_DESTINATION_KEY

    @property
    def commute_destination_town(self) -> str | None:
        """Canonical dataset town when non-default; None for Boston default."""
        if self.is_default:
            return None
        return self.destination_town


def _is_boston_phrase(phrase: str) -> bool:
    lower = phrase.lower().strip()
    return any(re.search(alias, lower) for alias in _BOSTON_ALIASES)


def _trim_phrase_at_separator(phrase: str) -> str:
    """Keep only the leading segment before preference/clause separators."""
    text = phrase.strip()
    if not text:
        return text
    match = _PHRASE_SEPARATOR_RE.search(text)
    if match:
        return text[: match.start()].strip()
    return text


def _find_dataset_town_in_phrase(phrase: str) -> str | None:
    """Longest-first match of a dataset town at the start of a captured phrase."""
    trimmed = _trim_phrase_at_separator(phrase)
    if not trimmed or _is_boston_phrase(trimmed):
        return None

    resolved = resolve_dataset_town(trimmed)
    if resolved:
        return resolved

    towns = sorted(dataset_town_names(), key=len, reverse=True)
    trimmed_lower = trimmed.lower()
    for town in towns:
        town_lower = town.lower()
        if trimmed_lower == town_lower:
            return town
        if trimmed_lower.startswith(town_lower):
            next_char = trimmed[len(town) :][:1]
            if not next_char or next_char in " ,-'":
                return town
    return None


def _unsupported_destination_label(phrase: str) -> str:
    trimmed = _trim_phrase_at_separator(phrase)
    if not trimmed:
        return phrase.strip()
    return trimmed


def _resolve_destination_phrase(phrase: str) -> CommuteDestinationResult | None:
    cleaned = phrase.strip()
    if not cleaned:
        return None
    trimmed = _trim_phrase_at_separator(cleaned)
    if trimmed and _is_boston_phrase(trimmed):
        return _default_destination()

    town = _find_dataset_town_in_phrase(cleaned)
    if town:
        return CommuteDestinationResult(
            destination_town=town,
            label=commute_destination_label(town),
            is_default=False,
            in_dataset=True,
            data_available=True,
            mention=cleaned,
            key=normalize_destination_key(town),
        )

    if trimmed and re.match(r"^[A-Za-z]", trimmed):
        label = _unsupported_destination_label(cleaned)
        return CommuteDestinationResult(
            destination_town=None,
            label=label,
            is_default=False,
            in_dataset=False,
            data_available=False,
            mention=trimmed,
            key="unknown_destination",
        )
    return None


def normalize_destination_key(town: str) -> str:
    from app.town_normalizer import normalize_key as _normalize_key

    return _normalize_key(town).replace(" ", "_")



def _default_destination() -> CommuteDestinationResult:
    return CommuteDestinationResult(
        destination_town=None,
        label=BOSTON_LABEL,
        is_default=True,
        in_dataset=True,
        data_available=True,
        mention=None,
        key=DEFAULT_DESTINATION_KEY,
    )


def _extract_destination_phrase(query: str) -> str | None:
    where_commute = _WHERE_TOWN_COMMUTE_RE.search(query)
    if where_commute:
        return where_commute.group(1).strip()
    for shorthand in (
        _TOWN_COMMUTE_RE,
        _TOWN_DRIVE_RE,
        _TOWN_MINUTES_COMMUTE_RE,
        _TOWN_WITHIN_MINUTES_RE,
    ):
        match = shorthand.search(query)
        if match:
            phrase = match.group(1).strip()
            if _find_dataset_town_in_phrase(phrase):
                return phrase
    town_commute = re.search(
        r"\b([A-Z][a-zA-Z\-']+(?:\s+[A-Z][a-zA-Z\-']+)*)\s+commute\s+is\b",
        query,
    )
    if town_commute:
        return town_commute.group(1).strip()

    for pattern in (
        _MINUTES_TO_TOWN_RE,
        _MINUTES_OF_RE,
        _JOB_IN_RE,
        _OFFICE_NEAR_RE,
        _OFFICE_IN_RE,
        _WORK_IN_RE,
        _COMMUTE_INTO_RE,
        _GET_TO_FOR_WORK_RE,
        _FOR_COMMUTE_TO_RE,
        _COMMUTE_TO_RE,
        _COMMUTE_INTO_COMPARE_RE,
        _HOW_FAR_FROM_RE,
        _DISTANCE_FROM_RE,
    ):
        match = pattern.search(query)
        if match:
            return match.group(1).strip()
    pair = _TO_DEST_RE.search(query)
    if pair:
        return pair.group(2).strip()
    return None


def detect_commute_destination(
    query: str,
    entities: ExtractedEntities | None = None,
) -> CommuteDestinationResult:
    """
    Return detected commute destination. Defaults to Boston/South Station when
    no alternate workplace/destination is mentioned.
    """
    from app.commute_intent import resolve_commute_intent

    return resolve_commute_intent(query).to_destination_result()


def _legacy_detect_commute_destination(
    query: str,
    entities: ExtractedEntities | None = None,
) -> CommuteDestinationResult:
    """Regex-only destination detection (fallback path inside resolve_commute_intent)."""
    text = query.strip()
    lower = text.lower()
    entities = entities or extract_entities(text)

    phrase = _extract_destination_phrase(text)
    if phrase:
        hit = _resolve_destination_phrase(phrase)
        if hit:
            if hit.in_dataset and not hit.is_default and not dynamic_commute_available():
                return CommuteDestinationResult(
                    destination_town=hit.destination_town,
                    label=hit.label,
                    is_default=False,
                    in_dataset=True,
                    data_available=False,
                    mention=hit.mention,
                    key=hit.key,
                )
            return hit

    if re.search(r"\bnear\s+", lower) and len(entities.valid_towns) == 1:
        hit = _resolve_destination_phrase(entities.valid_towns[0])
        if hit and not hit.is_default:
            if hit.in_dataset and not dynamic_commute_available():
                return CommuteDestinationResult(
                    destination_town=hit.destination_town,
                    label=hit.label,
                    is_default=False,
                    in_dataset=True,
                    data_available=False,
                    mention=None,
                    key=hit.key,
                )
            return hit

    return _default_destination()


# Keep regex path available for commute_intent merge (avoid circular resolve).
detect_commute_destination_regex = _legacy_detect_commute_destination


def extract_commute_town_pair(
    query: str,
    entities: ExtractedEntities | None = None,
) -> tuple[str, str] | None:
    """Extract origin and destination for point-to-point commute lookups."""
    text = query.strip()
    if not re.search(r"\b(?:commute|drive|travel|how far|distance)\b", text, re.I):
        return None

    match = _COMMUTE_FROM_TO_RE.search(text) or _TO_DEST_RE.search(text)
    if not match:
        return None

    origin_raw, dest_raw = match.group(1).strip(), match.group(2).strip()
    origin = resolve_dataset_town(origin_raw)
    destination = resolve_dataset_town(dest_raw)
    if not origin or not destination:
        return None
    if is_boston_destination(destination):
        return None
    return origin, destination


def extract_compare_commute_destination(query: str) -> str | None:
    """Canonical dataset town for compare+workplace destination, if any."""
    result = detect_compare_commute_destination_result(query)
    if result and result.in_dataset and result.destination_town:
        return result.destination_town
    return None


def detect_compare_commute_destination_result(query: str) -> CommuteDestinationResult | None:
    """Full destination result for compare+workplace phrasing (dataset or unsupported)."""
    from app.commute_intent import resolve_commute_intent

    if re.search(r"\b(?:compare|versus|vs\.?|or|better|which)\b", query, re.I):
        resolved = resolve_commute_intent(query)
        if resolved.has_non_default_destination():
            return resolved.to_destination_result()
        phrase = _extract_destination_phrase(query)
        if phrase:
            return _resolve_destination_phrase(phrase)

    match = _FOR_COMMUTE_TO_RE.search(query.strip())
    if not match:
        return None
    return _resolve_destination_phrase(match.group(1).strip())


def detect_compare_commute_destination(query: str) -> CommuteDestinationResult | None:
    """Alias for compare destination detection."""
    return detect_compare_commute_destination_result(query)


def entity_towns_for_compare_gate(
    entities: ExtractedEntities,
    query: str,
    *,
    compare_towns: list[str] | None = None,
    commute_destination: str | None = None,
) -> list[str]:
    """Exclude commute-only destination towns from multi-compare counts."""
    dest = commute_destination or extract_compare_commute_destination(query)
    compare_keys = {t.lower() for t in (compare_towns or [])}
    filtered: list[str] = []
    for town in entities.valid_towns:
        key = town.lower()
        if dest and key == dest.lower() and key not in compare_keys:
            continue
        filtered.append(town)
    return filtered


def is_non_boston_destination_query(query: str, entities: ExtractedEntities | None = None) -> bool:
    dest = detect_commute_destination(query, entities)
    return not dest.is_default


def build_commute_destination_limitation(
    dest: CommuteDestinationResult,
    *,
    context: str = "recommend",
) -> str:
    """Deterministic limitation when alternate destination cannot be served."""
    if dest.is_default or (dest.in_dataset and dest.data_available):
        return ""

    if dest.in_dataset and not dest.data_available:
        return (
            "Dynamic commute lookup is unavailable because GOOGLE_MAPS_API_KEY is not configured. "
            f"I cannot fetch drive times to {dest.label} right now. "
            f"I can still answer using Boston/South Station commute plus {AVAILABLE_FIELDS_BLURB}."
        )

    target = dest.label or dest.mention or "that place"
    if context == "lookup":
        return (
            f"I only have commute data between towns in our curated 200-town dataset. "
            f"{target} is not in that dataset, so I cannot answer that commute from stored data. "
            f"I can answer Boston/South Station commute plus {AVAILABLE_FIELDS_BLURB}."
        )

    return (
        f"I only support commute filters to towns in our curated 200-town dataset. "
        f"{target} is not in that dataset, so I cannot rank or filter by commute there. "
        f"I can answer using Boston/South Station commute plus {AVAILABLE_FIELDS_BLURB}."
    )

