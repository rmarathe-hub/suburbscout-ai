"""Town name normalization and alias matching across datasets."""

from __future__ import annotations

import re
from difflib import get_close_matches

# Canonical display name -> alternate normalized keys seen in source files
TOWN_ALIASES: dict[str, list[str]] = {
    "Manchester-by-the-Sea": [
        "manchester-by-the-sea",
        "manchester-by-the sea",
        "manchester by the sea",
        "manchester",
    ],
    "Westborough": ["westboro", "westborough"],
    "Marlborough": ["marlboro", "marlborough"],
    "Foxborough": ["foxboro", "foxborough"],
    "Northborough": ["northboro", "northborough"],
    "North Reading": ["north readin", "north reding", "north reading"],
    "Boxford": ["boxford"],
}


def normalize_key(name: str) -> str:
    """Lowercase, collapse whitespace, strip punctuation variants."""
    if not name or not str(name).strip():
        return ""
    text = str(name).strip().lower()
    text = text.replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    return text


# Build reverse lookup: normalized alias -> canonical display name
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for canonical, aliases in TOWN_ALIASES.items():
    _ALIAS_TO_CANONICAL[normalize_key(canonical)] = canonical
    for alias in aliases:
        _ALIAS_TO_CANONICAL[normalize_key(alias)] = canonical


def canonical_town_name(name: str) -> str:
    """Return preferred display name for a town if alias is known."""
    key = normalize_key(name)
    return _ALIAS_TO_CANONICAL.get(key, str(name).strip())


def town_match_keys(display_name: str) -> set[str]:
    """All normalized keys that should match this town in source data."""
    canonical = canonical_town_name(display_name)
    keys = {normalize_key(canonical), normalize_key(display_name)}
    for alias in TOWN_ALIASES.get(canonical, []):
        keys.add(normalize_key(alias))
    return {k for k in keys if k}


def matches_town(source_name: str, target_display_name: str) -> bool:
    """True if source_name refers to target_display_name."""
    source_key = normalize_key(source_name)
    return source_key in town_match_keys(target_display_name)


def find_canonical_in_set(source_name: str, known_towns: list[str]) -> str | None:
    """Find which known town display name matches a source label."""
    for town in known_towns:
        if matches_town(source_name, town):
            return town
    return None


def resolve_town_in_dataset(name: str, known_towns: list[str]) -> str | None:
    """Return canonical dataset town name for an exact or high-confidence fuzzy match."""
    if not name or not known_towns:
        return None
    keys = [normalize_key(t) for t in known_towns]
    key_to_name = dict(zip(keys, known_towns))
    query_key = normalize_key(canonical_town_name(name))
    if query_key in key_to_name:
        return key_to_name[query_key]

    fuzzy = get_close_matches(query_key, keys, n=8, cutoff=0.72)
    if not fuzzy:
        return None
    if len(fuzzy) == 1:
        return key_to_name[fuzzy[0]]

    query_tokens = [t for t in query_key.split() if len(t) > 2]
    best_key: str | None = None
    best_score = -1
    for candidate in fuzzy:
        score = len(candidate)
        if query_tokens and all(t in candidate for t in query_tokens):
            score += 100
        if query_tokens and candidate.startswith(query_tokens[0]):
            score += 50
        if len(query_tokens) >= 2 and candidate.count(" ") >= 1:
            score += 25
        if score > best_score:
            best_score = score
            best_key = candidate
    return key_to_name[best_key or fuzzy[0]]


def towns_equivalent(expected: str, actual: str) -> bool:
    """True when two labels refer to the same dataset town, allowing minor typos."""
    if normalize_key(expected) == normalize_key(actual):
        return True
    return get_close_matches(
        normalize_key(expected),
        [normalize_key(actual)],
        n=1,
        cutoff=0.82,
    ) != []
