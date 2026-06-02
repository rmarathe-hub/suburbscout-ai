"""Commute destination detection (Phase 2 agent — Boston stored, others limitation-only)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.entity_extractor import ExtractedEntities, extract_entities
from app.lookup_schema import AVAILABLE_FIELDS_BLURB
from app.query_patterns import is_town_in_exclude_context

DEFAULT_DESTINATION_KEY = "boston_south_station"

# Allowlisted destinations; only Boston has stored OD data today.
DESTINATIONS: dict[str, dict[str, object]] = {
    DEFAULT_DESTINATION_KEY: {
        "label": "Boston / South Station",
        "aliases": (
            r"\bboston\b",
            r"\bsouth station\b",
            r"\bdowntown boston\b",
        ),
        "data_available": True,
    },
    "cambridge_kendall": {
        "label": "Cambridge / Kendall Square",
        "aliases": (
            r"\bcambridge\b",
            r"\bkendall square\b",
            r"\bkendall\b",
        ),
        "data_available": False,
    },
    "waltham": {
        "label": "Waltham",
        "aliases": (r"\bwaltham\b",),
        "data_available": False,
    },
    "burlington": {
        "label": "Burlington",
        "aliases": (r"\bburlington\b",),
        "data_available": False,
    },
    "worcester": {
        "label": "Worcester",
        "aliases": (r"\bworcester\b",),
        "data_available": False,
    },
    "framingham_natick": {
        "label": "Framingham / Natick",
        "aliases": (
            r"\bframingham\b",
            r"\bnatick\b",
        ),
        "data_available": False,
    },
    "quincy": {
        "label": "Quincy",
        "aliases": (r"\bquincy\b",),
        "data_available": False,
    },
    "lowell": {
        "label": "Lowell",
        "aliases": (r"\blowell\b",),
        "data_available": False,
    },
}

_WORK_IN_RE = re.compile(
    r"\b(?:i\s+)?work\s+(?:in|at|near)\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_MINUTES_OF_RE = re.compile(
    r"\b(?:within|under|less than|max|up to)\s+\d+\s*(?:mins?|minutes)\s+of\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_COMMUTE_TO_RE = re.compile(
    r"\bcommut(?:e|ing)\s+to\s+([a-zA-Z][\w\s\-']+)",
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
    r"\bfrom\s+[a-zA-Z][\w\s\-']+?\s+to\s+([a-zA-Z][\w\s\-']+)",
    re.I,
)
_NEAR_JOB_RE = re.compile(
    r"\bnear\s+([a-zA-Z][\w\s\-']+?)(?:\s+with|\s+under|\?|$)",
    re.I,
)


@dataclass(frozen=True)
class CommuteDestinationResult:
    """Detected commute destination for a query."""

    key: str
    label: str
    data_available: bool
    is_default: bool
    mention: str | None = None


def _match_destination_phrase(phrase: str) -> CommuteDestinationResult | None:
    lower = phrase.lower().strip()
    for key, meta in DESTINATIONS.items():
        for alias in meta["aliases"]:
            if re.search(alias, lower):
                return CommuteDestinationResult(
                    key=key,
                    label=str(meta["label"]),
                    data_available=bool(meta["data_available"]),
                    is_default=key == DEFAULT_DESTINATION_KEY,
                    mention=phrase.strip(),
                )
    return None


def _extract_destination_phrase(query: str) -> str | None:
    for pattern in (_WORK_IN_RE, _MINUTES_OF_RE, _COMMUTE_TO_RE, _HOW_FAR_FROM_RE, _DISTANCE_FROM_RE, _TO_DEST_RE):
        match = pattern.search(query)
        if match:
            return match.group(1).strip()
    return None


def detect_commute_destination(
    query: str,
    entities: ExtractedEntities | None = None,
) -> CommuteDestinationResult:
    """
    Return detected commute destination. Defaults to Boston/South Station when
    no alternate workplace/destination is mentioned.
    """
    text = query.strip()
    lower = text.lower()
    entities = entities or extract_entities(text)

    phrase = _extract_destination_phrase(text)
    if phrase:
        hit = _match_destination_phrase(phrase)
        if hit:
            return hit

    # "Towns near Worcester with good schools" — Worcester as anchor, not Boston commute filter
    if re.search(r"\bnear\s+", lower) and len(entities.valid_towns) == 1:
        hit = _match_destination_phrase(entities.valid_towns[0])
        if hit and not hit.is_default:
            return hit

    for key, meta in DESTINATIONS.items():
        if key == DEFAULT_DESTINATION_KEY:
            continue
        for alias in meta["aliases"]:
            for match in re.finditer(alias, lower):
                if is_town_in_exclude_context(text, match.start()):
                    continue
                return CommuteDestinationResult(
                    key=key,
                    label=str(meta["label"]),
                    data_available=bool(meta["data_available"]),
                    is_default=False,
                    mention=None,
                )

    default = DESTINATIONS[DEFAULT_DESTINATION_KEY]
    return CommuteDestinationResult(
        key=DEFAULT_DESTINATION_KEY,
        label=str(default["label"]),
        data_available=True,
        is_default=True,
    )


def is_non_boston_destination_query(query: str, entities: ExtractedEntities | None = None) -> bool:
    dest = detect_commute_destination(query, entities)
    return not dest.is_default


def build_commute_destination_limitation(
    dest: CommuteDestinationResult,
    *,
    context: str = "recommend",
) -> str:
    """Deterministic limitation when alternate destination data is unavailable."""
    if dest.data_available:
        return ""

    if context == "lookup":
        return (
            f"I currently only have stored commute estimates to Boston/South Station, not to {dest.label}. "
            f"I cannot answer distance or commute to {dest.label} from stored data. "
            f"I can answer Boston/South Station commute plus {AVAILABLE_FIELDS_BLURB}."
        )

    return (
        f"I currently only have stored commute estimates to Boston/South Station, not to {dest.label}. "
        f"I cannot rank or filter towns by commute to {dest.label} using stored data. "
        f"Custom commute destinations require additional commute data. "
        f"I can answer using Boston/South Station commute plus {AVAILABLE_FIELDS_BLURB}."
    )
