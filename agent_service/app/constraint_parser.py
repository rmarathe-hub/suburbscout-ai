"""Rule-based constraint parser for suburb queries (Phase 1.1)."""

from __future__ import annotations

import re
from functools import lru_cache

from app.geo_enrichment import region_key_for_label
from app.schemas import Preferences
from app.town_normalizer import TOWN_ALIASES, canonical_town_name, normalize_key, resolve_town_in_dataset

# Longest phrases first so "North Shore" wins over "Shore".
REGION_PHRASES: tuple[tuple[str, str], ...] = (
    ("northwest / middlesex / route 2 / 495 belt", "Northwest / Middlesex / Route 2 / 495 belt"),
    ("northwest middlesex route 2 495 belt", "Northwest / Middlesex / Route 2 / 495 belt"),
    ("495 belt", "Northwest / Middlesex / Route 2 / 495 belt"),
    ("route 2 corridor", "Northwest / Middlesex / Route 2 / 495 belt"),
    ("worcester area", "Worcester-area but still Boston-commutable for some"),
    ("worcester-area", "Worcester-area but still Boston-commutable for some"),
    ("southeast / route 24 / commuter edge", "Southeast / Route 24 / commuter edge"),
    ("route 24 corridor", "Southeast / Route 24 / commuter edge"),
    ("core boston", "Core Boston + inner metro"),
    ("inner metro", "Core Boston + inner metro"),
    ("north shore", "North Shore / northeast suburbs"),
    ("south shore", "South Shore"),
    ("metrowest", "MetroWest"),
    ("metro west", "MetroWest"),
)

COUNTY_NAMES: tuple[str, ...] = (
    "Middlesex",
    "Essex",
    "Norfolk",
    "Suffolk",
    "Worcester",
    "Plymouth",
    "Bristol",
)

COASTAL_PHRASES: tuple[str, ...] = (
    "coastal",
    "coast",
    "ocean",
    "oceanfront",
    "beach",
    "beach town",
    "beach towns",
    "waterfront",
    "water-adjacent",
    "water adjacent",
    "on the water",
    "towns on the water",
    "near the ocean",
    "near the sea",
    "sea side",
    "seaside",
    "seaside towns",
)

NOT_EXPENSIVE_PHRASES: tuple[str, ...] = (
    "not expensive",
    "not too expensive",
    "inexpensive",
    "lower cost",
)

SAFER_THAN_RE = re.compile(
    r"(?:safer|more safe|better safety)\s+than\s+([a-zA-Z][a-zA-Z\s\-']+?)(?:\s|,|\.|$|but)",
    re.IGNORECASE,
)
CHEAPER_THAN_RE = re.compile(
    r"(?:cheaper|less expensive|lower price|more affordable)\s+than\s+([a-zA-Z][a-zA-Z\s\-']+?)(?:\s|,|\.|$|but)",
    re.IGNORECASE,
)
QUIETER_THAN_RE = re.compile(
    r"(?:quieter|more quiet|less busy|calmer)\s+than\s+([a-zA-Z][a-zA-Z\s\-']+?)(?:\s|,|\.|$|but)",
    re.IGNORECASE,
)
LIKE_TOWN_RE = re.compile(
    r"(?:like|similar to|towns like|something like)\s+([a-zA-Z][a-zA-Z\s\-']+?)(?:\s|,|\.|$|but)",
    re.IGNORECASE,
)
BUDGET_ONLY_RE = re.compile(
    r"(?:only have|have only|budget of|my budget is|budget is)\s*\$?\s*([\d,]+)\s*k?\b",
    re.IGNORECASE,
)
BUDGET_UNDER_RE = re.compile(
    r"(?:under|below|less than|max|up to|not over|don't show me anything over|"
    r"what can i get if my max is)\s*\$?\s*([\d,]+)\s*k?\b",
    re.IGNORECASE,
)
BUDGET_BELOW_K_RE = re.compile(
    r"\bbelow\s+(\d{3,4})k\b",
    re.IGNORECASE,
)
BUDGET_BARE_K_RE = re.compile(r"\b(\d{3,4})\s*k\b", re.IGNORECASE)
MILLION_RE = re.compile(
    r"(?:under|below|less than|max|up to|have|only)?\s*\$?\s*(\d+(?:\.\d+)?)\s*(?:million|mil|m)\b",
    re.IGNORECASE,
)
ONE_MILLION_RE = re.compile(r"\bone million\b", re.IGNORECASE)
BETWEEN_COMMUTE_RE = re.compile(
    r"\bbetween\s+(\d+)\s+and\s+(\d+)\s*(?:mins?|minutes)\b",
    re.IGNORECASE,
)
FARTHER_THAN_COMMUTE_RE = re.compile(
    r"\b(?:farther|further)\s+than\s+(\d+)\s*(?:mins?|minutes)\b",
    re.IGNORECASE,
)
IS_TOWN_COASTAL_RE = re.compile(r"\bis\s+.+\s+coastal\b", re.IGNORECASE)

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


def extract_exclude_towns(query: str) -> list[str]:
    """Return canonical town names the user asked to exclude from results."""
    towns: list[str] = []
    seen: set[str] = set()
    known = [t for t in _known_towns_by_length()]
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
MAX_COMMUTE_RE = re.compile(
    r"(?:under|within|less than|max|up to|no more than|(?:only|just)\s+)\s*(\d+)\s*(?:mins?|minutes)\b",
    re.IGNORECASE,
)
MIN_COMMUTE_RE = re.compile(
    r"(?:over|more than|at least|minimum|\bor more\b)\s+(\d+)\s*(?:mins?|minutes)\b",
    re.IGNORECASE,
)
MINUTES_OR_MORE_RE = re.compile(
    r"\b(\d+)\s+minutes or more\b",
    re.IGNORECASE,
)
COMMUTE_TO_RE = re.compile(
    r"\b(\d+)\s*[-–]\s*(?:to|-)\s*(\d+)\s*(?:mins?|minutes)\b",
    re.IGNORECASE,
)
COMMUTE_AWAY_RE = re.compile(
    r"(\d+)\s*(?:mins?|minutes)\s*(?:away\s+)?(?:from\s+)?(?:boston|south station)\b",
    re.IGNORECASE,
)
COMMUTE_WINDOW_RE = re.compile(
    r"\b(?:commute band|between)\s+(\d+)\s+(?:to|and|-)\s+(\d+)\s*(?:mins?|minutes)\b",
    re.IGNORECASE,
)
DRIVE_TIME_UNDER_RE = re.compile(
    r"\bdrive time under\s+(\d+)\s*(?:mins?|minutes)\b",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _known_towns_by_length() -> tuple[str, ...]:
    from app.ranking import load_suburbs

    suburbs = load_suburbs()
    return tuple(sorted((s["name"] for s in suburbs), key=lambda n: len(n), reverse=True))


@lru_cache(maxsize=1)
def _known_town_keys() -> frozenset[str]:
    return frozenset(normalize_key(t) for t in _known_towns_by_length())


def _parse_money(raw: str, *, unit_million: bool = False) -> int:
    amount = float(raw.replace(",", ""))
    if unit_million:
        return int(amount * 1_000_000)
    if amount < 1000:
        return int(amount * 1000)
    return int(amount)


def _clean_town_phrase(phrase: str) -> str:
    text = phrase.strip().strip(".,;:!?")
    text = re.sub(
        r"\s+for\s+(?:commute|safety|schools?|price|affordability|school score).*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+(but|with|and|under|over|in|on|near)\b.*$", "", text, flags=re.IGNORECASE)
    return canonical_town_name(text.strip())


def _town_in_dataset(name: str) -> bool:
    return normalize_key(name) in _known_town_keys()


def _town_name_pattern(town: str) -> str:
    """Regex for a dataset town name, allowing hyphen/space variants."""
    parts = [re.escape(part) for part in town.lower().split("-")]
    return r"\b" + r"[\s\-]+".join(parts) + r"\b"


_SKIP_UNKNOWN_TOKENS = frozenset({
    "boston",
    "massachusetts",
    "middlesex",
    "essex",
    "norfolk",
    "north",
    "south",
    "shore",
    "compare",
    "safe",
    "good",
    "strong",
    "decent",
    "tell",
    "give",
    "find",
    "show",
    "what",
    "which",
    "how",
    "is",
    "are",
    "the",
    "town",
    "list",
    "recommend",
    "quiet",
    "family",
    "affordable",
    "cheaper",
    "expensive",
})


def extract_town_mentions(query: str) -> tuple[list[str], list[str]]:
    """Return (known_towns, unknown_towns) mentioned in query text."""
    text = query.lower()
    known: list[str] = []
    unknown: list[str] = []
    seen_keys: set[str] = set()

    for town in _known_towns_by_length():
        key = normalize_key(town)
        pattern = _town_name_pattern(town)
        if re.search(pattern, text, re.IGNORECASE):
            if town == "Boston" and re.search(r"\b(from|to)\s+boston\b", text):
                continue
            if key not in seen_keys:
                known.append(town)
                seen_keys.add(key)

    for canonical, aliases in TOWN_ALIASES.items():
        canon_key = normalize_key(canonical)
        if canon_key in seen_keys:
            continue
        for label in (canonical, *aliases):
            pattern = _town_name_pattern(label) if "-" in label else r"\b" + re.escape(label.lower()) + r"\b"
            if re.search(pattern, text, re.IGNORECASE):
                known.append(canonical)
                seen_keys.add(canon_key)
                break

    # Explicit unknown examples outside dataset when clearly named
    for candidate in re.findall(r"\b([A-Z][a-zA-Z\-']+(?:\s+[A-Z][a-zA-Z\-']+)?)\b", query):
        cleaned = _clean_town_phrase(candidate)
        if not cleaned:
            continue
        key = normalize_key(cleaned)
        if key in seen_keys:
            continue
        if _town_in_dataset(cleaned):
            continue
        # Skip common English words / regions
        if cleaned.lower() in _SKIP_UNKNOWN_TOKENS:
            continue
        if candidate.split()[0].lower() in _SKIP_UNKNOWN_TOKENS:
            continue
        if len(cleaned) >= 4:
            unknown.append(cleaned)
            seen_keys.add(key)

    return known, unknown


def _parse_budget(text: str) -> int | None:
    if ONE_MILLION_RE.search(text):
        return 1_000_000
    million = MILLION_RE.search(text)
    if million:
        return _parse_money(million.group(1), unit_million=True)
    for pattern in (BUDGET_UNDER_RE, BUDGET_ONLY_RE):
        match = pattern.search(text)
        if match:
            tail = text[match.end() : match.end() + 12]
            if re.match(r"\s*(?:mins?|minutes)\b", tail, re.IGNORECASE):
                continue
            if re.match(r"\s*(?:million|mil|m)\b", tail, re.IGNORECASE):
                continue
            return _parse_money(match.group(1))
    match = BUDGET_BELOW_K_RE.search(text)
    if match:
        return _parse_money(match.group(1))
    match = BUDGET_BARE_K_RE.search(text)
    if match:
        return _parse_money(match.group(1))
    return None


def _parse_commute_bounds(text: str) -> tuple[int | None, int | None]:
    max_minutes: int | None = None
    min_minutes: int | None = None

    between = BETWEEN_COMMUTE_RE.search(text)
    if between:
        min_minutes = int(between.group(1))
        max_minutes = int(between.group(2))
        return max_minutes, min_minutes

    window = COMMUTE_WINDOW_RE.search(text)
    if window:
        min_minutes = int(window.group(1))
        max_minutes = int(window.group(2))
        return max_minutes, min_minutes

    to_window = COMMUTE_TO_RE.search(text)
    if to_window:
        min_minutes = int(to_window.group(1))
        max_minutes = int(to_window.group(2))
        return max_minutes, min_minutes

    drive_under = DRIVE_TIME_UNDER_RE.search(text)
    if drive_under:
        max_minutes = int(drive_under.group(1))

    farther = FARTHER_THAN_COMMUTE_RE.search(text)
    if farther:
        min_minutes = int(farther.group(1)) + 1

    min_match = MIN_COMMUTE_RE.search(text)
    if min_match:
        min_minutes = int(min_match.group(1))

    or_more = MINUTES_OR_MORE_RE.search(text)
    if or_more:
        min_minutes = max(min_minutes or 0, int(or_more.group(1)))

    max_match = MAX_COMMUTE_RE.search(text)
    if max_match:
        max_minutes = int(max_match.group(1))

    away_match = COMMUTE_AWAY_RE.search(text)
    if away_match:
        value = int(away_match.group(1))
        if min_minutes is not None and value == min_minutes:
            pass
        elif re.search(
            rf"\b(?:over|more than|at least|farther than|further than)\s+{value}\s*(?:mins?|minutes)\b",
            text,
            re.IGNORECASE,
        ):
            min_minutes = min_minutes or value
        elif max_minutes is None and not re.search(
            r"\b(?:over|more than|at least|farther|further)\b", text
        ):
            max_minutes = value

    if "long commute" in text or "far from boston" in text:
        min_minutes = min_minutes or 45
    if re.search(r"\b45\+\s*minutes\b|\b45\+ minutes\b", text):
        min_minutes = max(min_minutes or 0, 45)
    if re.search(r"\b(?:skip the close-in|far-out|farther out|farther/closer)\b", text):
        min_minutes = min_minutes or 40
    if "at least 50 minutes away" in text or "be at least 50 minutes" in text:
        min_minutes = max(min_minutes or 0, 50)

    if max_minutes is None and "not too far" in text:
        max_minutes = 50

    return max_minutes, min_minutes


def _parse_region(text: str) -> str | None:
    for phrase, label in REGION_PHRASES:
        if phrase in text:
            return label
    return None


def _parse_county(text: str) -> str | None:
    for county in COUNTY_NAMES:
        if re.search(rf"\b{county.lower()}\b(?:\s+county)?", text):
            return county
    return None


def _parse_relative_town(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if not match:
        return None
    name = _clean_town_phrase(match.group(1))
    return name if name else None


def parse_constraints(query: str) -> Preferences:
    """Parse natural language into structured ranking constraints (no LLM)."""
    text = query.lower()
    prefs = Preferences(raw_query=query, allow_stretch_options=False)

    prefs.budget_max = _parse_budget(text)
    max_commute, min_commute = _parse_commute_bounds(text)
    prefs.max_commute_minutes = max_commute
    prefs.min_commute_minutes = min_commute

    if any(phrase in text for phrase in COASTAL_PHRASES) and not IS_TOWN_COASTAL_RE.search(text):
        prefs.requires_coastal = True

    region = _parse_region(text)
    if region:
        prefs.region_preference = region
        prefs.region_key = region_key_for_label(region)

    county = _parse_county(text)
    if county:
        prefs.county_preference = county

    if re.search(
        r"\b(?:weaker schools? (?:are |is )?acceptable|schools? not a priority|ignore schools?)\b",
        text,
    ):
        prefs.deprioritize_schools = True
        prefs.school_priority = "low"

    if re.search(r"\bdon'?t care about safety\b", text):
        prefs.deprioritize_safety = True
        prefs.safety_priority = "low"

    if re.search(
        r"\b(?:crime (?:can be|is) high|safety can be poor|accept (?:bad|weak|worse) safety|"
        r"poor safety ok)\b",
        text,
    ):
        prefs.allow_low_safety = True
        prefs.prefer_high_crime = True
        prefs.deprioritize_safety = True
        prefs.safety_priority = "low"

    if any(w in text for w in ("safe", "safety", "low crime")):
        if not prefs.deprioritize_safety and not prefs.allow_low_safety:
            prefs.safety_priority = "high"
    if re.search(
        r"\bhigh[- ]crime\b|\brisky\b|\bworse safety\b|\bbad safety\b|\bhigher crime\b|\bworst safety\b|"
        r"\bsafety is weak\b|\bhigher-crime\b",
        text,
    ) and "low crime" not in text:
        prefs.prefer_high_crime = True
        prefs.allow_low_safety = True
    if re.search(r"\bcommute can be bad if\b", text):
        prefs.commute_priority = "low"
        prefs.affordability_priority = prefs.affordability_priority or "high"
    if re.search(r"\bdo not include inland\b", text):
        prefs.requires_coastal = True
    if re.search(r"\bcommute (?:can be|is not|not the) (?:bad|poor|worse|long|priority|important)\b", text):
        prefs.commute_priority = "low"
        prefs.affordability_priority = prefs.affordability_priority or "high"
    if re.search(r"\b(?:sacrifice|trade).*(?:commute|safety|schools)\b", text):
        prefs.affordability_priority = prefs.affordability_priority or "high"
        if "commute" in text or "drive" in text:
            prefs.commute_priority = "low"
        if "safety" in text or "crime" in text:
            prefs.deprioritize_safety = True
        if "school" in text:
            prefs.deprioritize_schools = True
    if re.search(r"\bdeprioritize (?:safety|schools)\b", text):
        if "safety" in text:
            prefs.deprioritize_safety = True
            prefs.safety_priority = "low"
        if "school" in text:
            prefs.deprioritize_schools = True
            prefs.school_priority = "low"
    if re.search(r"\b(?:bottom-priced|lowest-priced|rank low-cost|low-cost towns)\b", text):
        prefs.affordability_priority = "high"
    if re.search(r"\b(?:accept|okay with|tolerate).*(?:long|bad|poor|weak).*(?:commute|safety|schools)\b", text):
        prefs.affordability_priority = prefs.affordability_priority or "high"
    if re.search(r"\bcommute sacrifice\b|\bsacrifice commute\b|\btrade commute\b", text):
        prefs.commute_priority = "low"
        prefs.affordability_priority = prefs.affordability_priority or "high"
    if re.search(r"\bcommute not priority\b|\bcommute is not the priority\b", text):
        prefs.commute_priority = "low"
    if re.search(
        r"\bcheapest towns\b|\brank.*highest crime\b|\brank.*worst safety\b|"
        r"\bweaker schools are acceptable\b|\bserious tradeoffs\b|\btradeoff-heavy\b|"
        r"\baffordable towns with obvious red flags\b|\bnot top-ranked\b|\bmajor downsides\b|"
        r"\bignore school quality\b|\bprice and commute only\b|\bhigh-crime affordable\b|"
        r"\baccept weaker safety\b|\baccept bad safety\b|\baffordability upside\b",
        text,
    ):
        prefs.prefer_high_crime = True
        prefs.affordability_priority = "high"
    if re.search(r"\bprice and commute only\b", text):
        prefs.deprioritize_schools = True
        prefs.deprioritize_safety = True
        prefs.affordability_priority = "high"
        prefs.commute_priority = "high"
    if re.search(r"\bweak schools?\b|\baverage schools?\b", text):
        prefs.prefer_low_school = True
    if re.search(r"\bdon'?t care about (?:school|schools)\b", text) or re.search(
        r"\bignore schools?\b", text
    ):
        prefs.deprioritize_schools = True
        prefs.school_priority = "low"
    if re.search(r"\bdon'?t care about safety\b", text):
        prefs.deprioritize_safety = True
        prefs.safety_priority = "low"
    if (
        any(w in text for w in ("school", "schools", "education"))
        and not prefs.deprioritize_schools
        and not re.search(r"\bweaker schools?\b", text)
    ):
        if not prefs.prefer_low_school:
            prefs.school_priority = "high"
    if any(
        w in text
        for w in ("commute", "close to boston", "not too far", "near boston", "from boston")
    ):
        prefs.commute_priority = "high"
    if (
        "affordable" in text
        or "cheaper" in text
        or "lower price" in text
        or any(p in text for p in NOT_EXPENSIVE_PHRASES)
    ):
        prefs.affordability_priority = "high"
    if any(w in text for w in ("family", "families", "kids")):
        if not prefs.prefer_high_crime and not prefs.deprioritize_safety:
            prefs.school_priority = prefs.school_priority or "high"
            prefs.safety_priority = prefs.safety_priority or "high"

    prefs.safer_than_town = _parse_relative_town(SAFER_THAN_RE, query)
    prefs.cheaper_than_town = _parse_relative_town(CHEAPER_THAN_RE, query)
    prefs.quieter_than_town = _parse_relative_town(QUIETER_THAN_RE, query)
    prefs.similar_to_town = _parse_relative_town(LIKE_TOWN_RE, query)

    known, unknown = extract_town_mentions(query)
    if known:
        prefs.named_towns = known
    if unknown:
        prefs.unknown_towns = unknown

    excluded = extract_exclude_towns(query)
    if excluded:
        prefs.exclude_towns = excluded

    if prefs.budget_max is not None:
        prefs.require_housing_for_budget = True

    return prefs
