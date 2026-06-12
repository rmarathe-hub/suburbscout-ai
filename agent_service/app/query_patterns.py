"""Query pattern helpers — Tier 1.5 + Phase 2 multi-town lookup/compare."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from app.entity_extractor import ExtractedEntities, extract_entities, primary_town
from app.town_normalizer import canonical_town_name, normalize_key, resolve_town_in_dataset

MAX_MULTI_LOOKUP_SPECS = 20
MAX_MULTI_COMPARE_TOWNS = 20

COMPARE_TABLE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("latest_home_price", "home_price", "Home price"),
    ("drive_minutes_to_boston", "commute_min", "Commute (min)"),
    ("safety_score", "safety_score", "Safety /10"),
    ("school_score", "school_score", "School /10"),
    ("crime_rate_per_1000", "crime_per_1k", "Crime /1k"),
    ("is_coastal", "coastal", "Coastal"),
)


@dataclass(frozen=True)
class LookupSpec:
    """One town + one stored field to fetch."""

    town: str
    field: str

_EXCLUDE_PREFIX_RE = re.compile(
    r"\b(?:not|except|excluding|exclude|without|avoid|skip|but not|other than)\s+(?:the\s+)?(?:town(?:s)?\s+(?:of\s+|like\s+|such as\s+)?)?$",
    re.I,
)

_EXCLUDE_CAPTURE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:but\s+)?not\s+([A-Za-z][\w\s\-']+?)(?:\s+and|\s+or|[,\?]|$|\s+(?:but|with|under|within|near|that|where|please|from)\b)",
        re.I,
    ),
    re.compile(
        r"\b(?:excluding|exclude|without|avoid|skip|other than)\s+([A-Za-z][\w\s\-']+?)(?:\s+and|\s+or|[,\?]|$)",
        re.I,
    ),
    re.compile(
        r"\bexcept(?:\s+for)?\s+([A-Za-z][\w\s\-']+?)(?:\s+and|\s+or|[,\?]|$)",
        re.I,
    ),
)

_COASTAL_LIST_RE = re.compile(
    r"\b(?:coastal|waterfront|ocean|seaside|beach|ocean-adjacent|on the water)\b.+\b(?:towns|suburbs|places|options)\b"
    r"|\b(?:towns|suburbs|places|options)\b.+\b(?:coastal|waterfront|ocean|seaside|beach|ocean-adjacent|on the water)\b",
    re.I,
)

_SINGLE_TOWN_COASTAL_RE = re.compile(
    r"\bis\s+.+\s+(?:coastal|waterfront|ocean-adjacent|a coast town)\b",
    re.I,
)

_OPEN_ENDED_RES: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bwhat towns should i consider\b", re.I),
    re.compile(r"\bwhat should i look at\b", re.I),
    re.compile(r"\bwhere should i (?:move|live)\b", re.I),
    re.compile(r"\bhelp me choose\b", re.I),
    re.compile(r"\bwhat do you recommend\b", re.I),
    re.compile(r"\bany suggestions\b", re.I),
    re.compile(r"\bwhat towns would you suggest\b", re.I),
)

_SCOPE_EXCLUSION_RE = re.compile(
    r"\b(?:excluded|exclude from|outside the list|not in the dataset|not in your list|"
    r"outside the curated|left out of)\b",
    re.I,
)

_MEMBERSHIP_SUPPORTED_RE = re.compile(
    r"\b(?:is|are)\s+.+\s+(?:supported|in scope|queryable|rankable|searchable|accepted|recognized)\b",
    re.I,
)

_MEMBERSHIP_WOULD_ACCEPT_RE = re.compile(
    r"\bwould\s+.+\s+be\s+(?:accepted|recognized|understood|supported)\b",
    re.I,
)

_MEMBERSHIP_CAN_USE_RE = re.compile(
    r"\bcan\s+(?:i|you)\s+use\s+.+\s+as\s+(?:a\s+)?town\s+name\b",
    re.I,
)

_MEMBERSHIP_RESOLVE_RE = re.compile(
    r"\b(?:resolve|map\s+to|recognized|recognised|alternate spelling|alternate spellings)\b",
    re.I,
)

_MEMBERSHIP_PART_OF_RE = re.compile(
    r"\b(?:part of|in scope for|within scope)\b.+\b(?:dataset|list|coverage|data)\b",
    re.I,
)

_MEMBERSHIP_TRACK_RE = re.compile(
    r"\b(?:do you track|would you track|is .+ tracked|is .+ loaded|is .+ in (?:the|your) (?:dataset|list|data))\b",
    re.I,
)

_PULL_UP_LOOKUP_RE = re.compile(
    r"^(?:pull up|bring up|open|show me|show)\s+[A-Za-z][\w\-']*",
    re.I,
)

_PULL_UP_TOWN_CAPTURE_RE = re.compile(
    r"^(?:pull up|bring up|open|show me|show)\s+(.+?)[\.\?\!]?\s*$",
    re.I,
)

_INVERTED_CRIME_AFFORD_RE = re.compile(
    r"\b(?:crime can be higher|higher crime is okay|higher crime|tolerate worse safety|"
    r"worse safety for|safety can be mediocre|poor safety ok|accept.*crime|high[- ]crime)\b",
    re.I,
)

_SEMANTIC_LIFESTYLE_RE = re.compile(
    r"\b(?:young families?|young professionals?|raising kids?|for families?|for kids\b|"
    r"family[- ]friendly)\b",
    re.I,
)

_COASTAL_RANK_RE = re.compile(
    r"\b(?:water-adjacent|water adjacent|waterfront|on the water|beach towns?|seaside towns?|"
    r"towns on the water|ocean-adjacent|ocean adjacent)\b",
    re.I,
)

_MULTI_COMMUTE_FROM_RE = re.compile(
    r"(?:commute from|(?:what is|what's)\s+(?:the\s+)?commute from)\s+([A-Za-z][\w\-']+)",
    re.I,
)

# Phase 2: per-clause town + field (e.g. commute from Maynard, housing cost in Newton)
_LOOKUP_SPEC_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"(?:what(?:'s| is) the )?(?:commute|drive time|how far)(?:\s+\w+){0,8}?\s+from\s+([A-Za-z][\w\-']+)",
            re.I,
        ),
        "commute",
    ),
    (
        re.compile(
            r"(?:commute|drive time)\s+(?:from|of|for|to)\s+([A-Za-z][\w\-']+)",
            re.I,
        ),
        "commute",
    ),
    (
        re.compile(
            r"(?:housing costs?|home prices?|median home prices?|housing prices?|prices?|costs?)"
            r"(?:\s+\w+){0,6}?\s+(?:in|of|for)\s+([A-Za-z][\w\-']+)",
            re.I,
        ),
        "price",
    ),
    (
        re.compile(
            r"(?:compare\s+)?(?:school scores?|school ratings?|schools?)"
            r"(?:\s+\w+){0,4}?\s+(?:in|for|of)\s+([A-Za-z][\w\-']+)",
            re.I,
        ),
        "school",
    ),
    (
        re.compile(
            r"(?:safety scores?|crime rates?|safety|crime)"
            r"(?:\s+\w+){0,4}?\s+(?:in|for|of)\s+([A-Za-z][\w\-']+)",
            re.I,
        ),
        "safety",
    ),
    (
        re.compile(
            r"(?:population)\s+(?:in|for|of)\s+([A-Za-z][\w\-']+)",
            re.I,
        ),
        "summary",
    ),
)

_LOOKUP_FIELD_MARKERS: tuple[tuple[str, str], ...] = (
    ("commute", r"\b(?:commute|drive time|how far|distance|miles)\b"),
    ("school", r"\bschool"),
    ("price", r"\b(?:price|home price|housing price|expensive|affordability|median home)\b"),
    ("safety", r"\b(?:crime|safety|safe)\b"),
    ("coastal", r"\b(?:coastal|coast|waterfront)\b"),
)


@lru_cache(maxsize=1)
def _dataset_towns() -> tuple[str, ...]:
    from app.suburb_store import suburbs_dataset_available

    if not suburbs_dataset_available():
        return ()
    from app.ranking import load_suburbs

    return tuple(item.get("name", "") for item in load_suburbs() if item.get("name"))


def is_town_in_exclude_context(query: str, match_start: int) -> bool:
    """True when a town name appears immediately after not/except/without/etc."""
    prefix = query[:match_start]
    return bool(_EXCLUDE_PREFIX_RE.search(prefix))


def extract_exclude_towns(query: str) -> list[str]:
    """Return canonical town names the user asked to exclude from results."""
    towns: list[str] = []
    seen: set[str] = set()
    known = list(_dataset_towns())
    for pattern in _EXCLUDE_CAPTURE_RES:
        for match in pattern.finditer(query):
            phrase = match.group(1).strip()
            resolved = resolve_town_in_dataset(phrase, known)
            if not resolved:
                continue
            key = normalize_key(resolved)
            if key not in seen:
                towns.append(resolved)
                seen.add(key)
    return towns


def is_coastal_town_list_query(query: str) -> bool:
    lower = query.lower()
    if _SINGLE_TOWN_COASTAL_RE.search(query):
        return False
    if not _COASTAL_LIST_RE.search(lower):
        return False
    if re.search(r"\bin the dataset\b|\bin your (?:data|list)\b", lower):
        return True
    if re.search(r"\b(?:list|show|give me|find|recommend|which)\b", lower):
        return True
    return bool(re.search(r"\b(?:towns|suburbs|places)\b", lower))


def is_open_ended_recommendation(query: str) -> bool:
    lower = query.lower()
    if any(p.search(lower) for p in _OPEN_ENDED_RES):
        from app.constraint_parser import parse_constraints

        constraints = parse_constraints(query)
        has_filters = any(
            (
                constraints.budget_max is not None,
                constraints.max_commute_minutes is not None,
                constraints.min_commute_minutes is not None,
                constraints.requires_coastal,
                constraints.region_preference,
                constraints.county_preference,
                constraints.safer_than_town,
                constraints.cheaper_than_town,
                constraints.similar_to_town,
            )
        )
        return not has_filters
    return False


def is_scope_inclusion_lookup(query: str, entities: ExtractedEntities) -> bool:
    """'Is Hull excluded?' — lookup whether a named town is in scope."""
    if len(entities.valid_towns) != 1:
        return False
    if not _SCOPE_EXCLUSION_RE.search(query):
        return False
    if re.search(r"\b(?:recommend|find|show|rank|compare)\b", query, re.I):
        return False
    return True


def is_membership_supported_query(query: str) -> bool:
    return bool(_MEMBERSHIP_SUPPORTED_RE.search(query))


def is_semantic_vibe_query(query: str) -> bool:
    """Vibe/similarity prompts that need semantic_search (not rank-only)."""
    lower = query.lower()
    if is_coastal_rank_query(query):
        return False
    if re.search(r"\b(?:versus|vs\.?)\b", lower):
        return False
    if is_pull_up_town_lookup(query):
        return False
    return bool(
        re.search(
            r"\b(?:vibe|feel|similar\s+to|similarity|[- ]like\b|like\s+[A-Za-z])",
            lower,
        )
    )


def extract_pull_up_town_name(
    query: str,
    known_towns: list[str] | None = None,
) -> str | None:
    """
    Town token from pull-up/open phrasing (longest known-town match).

    Prefer this over fuzzy entity extraction for Reading vs North Reading.
    """
    if not is_pull_up_town_lookup(query):
        return None
    match = _PULL_UP_TOWN_CAPTURE_RE.match(query.strip())
    if not match:
        return None
    span = match.group(1).strip()
    span = re.sub(
        r"\s+(?:profile|card|data|facts|summary|please)\s*.*$",
        "",
        span,
        flags=re.I,
    )
    span = span.rstrip(".,!? ").strip()
    if not span:
        return None

    if known_towns is None:
        known_towns = list(_dataset_towns())

    for town in sorted(known_towns, key=len, reverse=True):
        if re.match(rf"^{re.escape(town)}\s*$", span, re.I):
            return canonical_town_name(town)

    for prefix in ("open ", "show ", "pull up ", "bring up "):
        if span.lower().startswith(prefix):
            inner = span[len(prefix) :].strip()
            resolved = resolve_town_in_dataset(inner, known_towns)
            if resolved:
                return canonical_town_name(resolved)

    resolved = resolve_town_in_dataset(span, known_towns)
    if resolved:
        return canonical_town_name(resolved)
    return None


def is_pull_up_town_lookup(query: str) -> bool:
    """Show/open/pull up a single town card — lookup, not membership."""
    from app.lookup_schema import extract_unsupported_attribute

    text = query.strip()
    if not _PULL_UP_LOOKUP_RE.match(text):
        return False
    if extract_unsupported_attribute(text):
        return False
    if re.search(
        r"\b(?:current|live|zillow|redfin|mls|listings?|right now|today|homes? for sale)\b",
        text,
        re.I,
    ):
        return False
    if re.search(r"\b(?:towns|suburbs|options|list|rank|compare)\b", text, re.I):
        return False
    if _MEMBERSHIP_RESOLVE_RE.search(text) or _MEMBERSHIP_CAN_USE_RE.search(text):
        return False
    if _MEMBERSHIP_TRACK_RE.search(text):
        return False
    return True


def is_inverted_crime_affordability_query(query: str) -> bool:
    """User accepts worse safety/crime in exchange for affordability."""
    lower = query.lower()
    if not _INVERTED_CRIME_AFFORD_RE.search(lower):
        return False
    if re.search(r"\b(?:versus|vs\.?|compare)\b", lower):
        return False
    return bool(
        re.search(r"\b(?:cheap|afford|affordable|low price|affordability|price)\b", lower)
        or re.search(r"\bcare more about cheap\b", lower)
        or re.search(r"\bprioritize affordability\b", lower)
    )


def is_neighborhood_level_query(query: str) -> bool:
    """Within-town neighborhood / area questions — out of scope."""
    from app.lookup_schema import extract_unsupported_attribute

    match = extract_unsupported_attribute(query)
    if match and match.category == "neighborhood":
        return True
    lower = query.lower()
    patterns = (
        r"\b(?:best|safest|worst)\s+(?:neighborhood|area|part)\s+(?:in|of|inside)\b",
        r"\bneighborhoods?\s+in\s+[A-Za-z]",
        r"\b(?:area|part)\s+inside\s+[A-Za-z]",
        r"\bbest part of\s+[A-Za-z]+\s+to live\b",
        r"\bwhich neighborhood in\b",
    )
    return any(re.search(p, lower) for p in patterns)


def semantic_lifestyle_limitation_message(query: str) -> str | None:
    """Non-blocking note when semantic vibe uses unsupported lifestyle wording."""
    if not is_semantic_vibe_query(query):
        return None
    if not _SEMANTIC_LIFESTYLE_RE.search(query):
        return None
    return (
        "The dataset does not include a dedicated lifestyle or family-composition field. "
        "Semantic matches reflect stored town profile similarity only—not verified "
        "demographics or family-type labels."
    )


def build_neighborhood_unsupported_message() -> str:
    return (
        "This dataset covers town-level suburbs only, not neighborhoods or areas within a town. "
        "I cannot rank or compare parts of Brookline, Newton, or other towns at neighborhood granularity. "
        "I can answer town-level home price, commute to Boston/South Station, safety, schools, "
        "and coastal status for whole towns."
    )


def is_dataset_membership_query(query: str) -> bool:
    """True when user asks whether a town is in scope (not a data-card lookup)."""
    lower = query.lower()
    if is_pull_up_town_lookup(query):
        return False
    if is_coastal_rank_query(query):
        return False
    if re.search(
        r"\b(?:what is|how much|how long|tell me|give me|median|full-data|partial)\b",
        lower,
    ) and re.search(r"\b(?:price|commute|school|safety|crime|summary|tier|data)\b", lower):
        return False
    if re.search(r"\b(?:recommend|rank|compare|find|show me|top|best)\s+.+\s+towns\b", lower):
        return False
    if _MEMBERSHIP_WOULD_ACCEPT_RE.search(query):
        return True
    if _MEMBERSHIP_CAN_USE_RE.search(query):
        return True
    if _MEMBERSHIP_TRACK_RE.search(query):
        return True
    if _MEMBERSHIP_RESOLVE_RE.search(query):
        if not re.search(r"\b(?:versus|vs\.?|compare|price|commute|safety|school)\b", lower):
            return True
    if _MEMBERSHIP_PART_OF_RE.search(query):
        return True
    if re.search(r"\bwould\s+.+\s+resolve\b", lower):
        return True
    if is_membership_supported_query(query):
        return True
    membership_markers = (
        r"\bin (?:the|your) (?:dataset|list|data)\b",
        r"\b(?:loaded|tracked|supported|accepted|recognized|queryable|searchable|in scope)\b",
        r"\b(?:exist in|included in|part of)\b",
    )
    if re.search(r"\b(?:is|are|does|do you|can you|will)\b", lower) and any(
        re.search(p, lower) for p in membership_markers
    ):
        if re.search(
            r"\b(?:what is|how much|how long|tell me|give me|median|full-data|partial)\b",
            lower,
        ):
            return False
        if re.search(
            r"\b(?:stats?|numbers?|price|commute|school|safety|crime|summary|tier)\b",
            lower,
        ):
            return False
        return True
    return False


def is_coastal_rank_query(query: str) -> bool:
    """List/recommend coastal towns — rank with requires_coastal, not semantic search."""
    if _SINGLE_TOWN_COASTAL_RE.search(query):
        return False
    lower = query.lower()
    if _COASTAL_RANK_RE.search(lower) and re.search(
        r"\b(?:towns|suburbs|places|options|list|show|find|recommend|which)\b", lower
    ):
        return True
    return is_coastal_town_list_query(query)


def _collect_lookup_specs_from_text(text: str, known: list[str], seen: set[tuple[str, str]]) -> list[LookupSpec]:
    found: list[LookupSpec] = []
    for pattern, field in _LOOKUP_SPEC_PATTERNS:
        for match in pattern.finditer(text):
            phrase = match.group(1).strip().rstrip("?.,")
            town = resolve_town_in_dataset(phrase, known)
            if not town:
                continue
            key = (normalize_key(town), field)
            if key in seen:
                continue
            seen.add(key)
            found.append(LookupSpec(town=town, field=field))
    return found


def detect_multi_town_lookup_specs(query: str) -> list[LookupSpec]:
    """
    Parse 2+ lookups when each clause ties a town to a field (comma-separated lists OK).
    Same town with multiple fields stays on single-town multi-field path.
    """
    known = list(_dataset_towns())
    raw: list[LookupSpec] = []
    seen: set[tuple[str, str]] = set()
    raw.extend(_collect_lookup_specs_from_text(query, known, seen))
    if "," in query:
        for segment in query.split(","):
            segment = segment.strip()
            if not segment:
                continue
            raw.extend(_collect_lookup_specs_from_text(segment, known, seen))
    if len(raw) < 2:
        return []
    if len({normalize_key(s.town) for s in raw}) < 2:
        return []
    if len(raw) == 2 and all(s.field == "commute" for s in raw):
        return []
    return raw[:MAX_MULTI_LOOKUP_SPECS]


def infer_compare_table_columns(lower: str) -> list[str]:
    """Return suburbs.json keys to include in a multi-town compare table."""
    keys: list[str] = []
    if re.search(r"\b(?:price|afford|housing|cost|expensive)\b", lower):
        keys.append("latest_home_price")
    if re.search(r"\b(?:commute|drive|minutes|boston)\b", lower):
        keys.append("drive_minutes_to_boston")
    if re.search(r"\b(?:school|education)\b", lower):
        keys.append("school_score")
    if re.search(r"\b(?:safety|crime|safe)\b", lower):
        keys.extend(["safety_score", "crime_rate_per_1000"])
    if re.search(r"\bcoastal\b", lower):
        keys.append("is_coastal")
    if not keys:
        return ["latest_home_price", "drive_minutes_to_boston", "safety_score", "school_score"]
    out: list[str] = []
    for key, _, _ in COMPARE_TABLE_COLUMNS:
        if key in keys and key not in out:
            out.append(key)
    return out


def extract_multi_compare_towns(entities: ExtractedEntities, query: str) -> list[str]:
    """3–20 named towns with explicit compare language."""
    lower = query.lower()
    if len(entities.valid_towns) < 3:
        return []
    if not re.search(r"\bcompare\b", lower) and not re.search(
        r"\b(?:versus|vs\.?)\b", lower
    ):
        return []
    if detect_multi_town_lookup_specs(query):
        return []
    return list(entities.valid_towns)[:MAX_MULTI_COMPARE_TOWNS]


def build_too_many_compare_message(count: int) -> str:
    return (
        f"I can build a comparison table for up to {MAX_MULTI_COMPARE_TOWNS} towns at once. "
        f"You named {count}. Please narrow the list or ask for a ranked recommendation with filters."
    )


def build_too_many_lookup_message(count: int) -> str:
    return (
        f"I can answer up to {MAX_MULTI_LOOKUP_SPECS} separate town lookups in one message. "
        f"You asked for {count}. Please split into smaller batches."
    )


def detect_multi_commute_compare(query: str) -> tuple[str, str] | None:
    """Two explicit commute-from lookups → compare on commute."""
    known = list(_dataset_towns())
    towns: list[str] = []
    seen: set[str] = set()
    for match in _MULTI_COMMUTE_FROM_RE.finditer(query):
        phrase = match.group(1).strip()
        resolved = resolve_town_in_dataset(phrase, known)
        if not resolved:
            continue
        key = normalize_key(resolved)
        if key in seen:
            continue
        towns.append(resolved)
        seen.add(key)
        if len(towns) >= 2:
            return towns[0], towns[1]
    return None


def infer_lookup_fields(lower: str) -> list[str]:
    fields: list[str] = []
    for field, pattern in _LOOKUP_FIELD_MARKERS:
        if re.search(pattern, lower) and field not in fields:
            fields.append(field)
    return fields


def is_multi_field_lookup(query: str) -> bool:
    return len(infer_lookup_fields(query.lower())) >= 2


def resolve_typo_lookup_town(query: str, entities: ExtractedEntities) -> str | None:
    """Resolve a single typo/unknown town for lookup when field signals are present."""
    if len(entities.valid_towns) == 1:
        return entities.valid_towns[0]
    if entities.valid_towns:
        return None
    if len(entities.unknown_town_candidates) != 1:
        return None
    lower = query.lower()
    if not (
        re.search(r"\bdoes\s+.+\s+have\b", lower)
        or re.search(r"\bis\s+.+\s+(?:expensive|coastal|safe)\b", lower)
        or re.search(r"\b(?:tell me about|look up|what is)\b", lower)
        or infer_lookup_fields(lower)
    ):
        return None
    candidate = entities.unknown_town_candidates[0]
    resolved = resolve_town_in_dataset(candidate, list(_dataset_towns()))
    return resolved or candidate


def open_ended_clarification_message() -> str:
    return (
        "I can recommend towns from the curated 200-town dataset when you share constraints "
        "like budget, max commute to Boston/South Station, school/safety priorities, or coastal preference. "
        "What matters most to you?"
    )
