"""Town name normalization and alias matching across datasets."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches

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


@dataclass(frozen=True)
class TownResolution:
    """Result of resolving a user/planner town label against the dataset."""

    queried: str
    resolved: str | None
    ambiguous: bool
    candidates: tuple[str, ...]


def _fuzzy_match_ratio(query_key: str, candidate_key: str) -> float:
    return SequenceMatcher(None, query_key, candidate_key).ratio()


def resolve_town_for_plan(name: str, known_towns: list[str]) -> TownResolution:
    """
    Resolve a town for plan normalization.

    High-confidence matches are canonicalized; ambiguous multi-match typos are left
    unresolved so execution can surface "Did you mean A or B?".
    """
    queried = (name or "").strip()
    if not queried or not known_towns:
        return TownResolution(queried=queried, resolved=None, ambiguous=False, candidates=())

    keys = [normalize_key(t) for t in known_towns]
    key_to_name = dict(zip(keys, known_towns))
    query_key = normalize_key(canonical_town_name(queried))
    if query_key in key_to_name:
        return TownResolution(
            queried=queried,
            resolved=key_to_name[query_key],
            ambiguous=False,
            candidates=(),
        )

    fuzzy = get_close_matches(query_key, keys, n=8, cutoff=0.72)
    if not fuzzy:
        return TownResolution(queried=queried, resolved=None, ambiguous=False, candidates=())

    if len(fuzzy) == 1:
        return TownResolution(
            queried=queried,
            resolved=key_to_name[fuzzy[0]],
            ambiguous=False,
            candidates=(),
        )

    query_tokens = [t for t in query_key.split() if len(t) > 2]
    scored: list[tuple[int, float, str]] = []
    for candidate in fuzzy:
        score = len(candidate)
        if query_tokens and all(t in candidate for t in query_tokens):
            score += 100
        if query_tokens and candidate.startswith(query_tokens[0]):
            score += 50
        if len(query_tokens) >= 2 and candidate.count(" ") >= 1:
            score += 25
        scored.append((score, _fuzzy_match_ratio(query_key, candidate), candidate))

    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best_score, best_ratio, best_key = scored[0]
    second_score, second_ratio, second_key = scored[1]
    candidates = tuple(key_to_name[key] for _, _, key in scored[:3])

    # Ambiguous when heuristic scores tie or string similarity is too close.
    if best_score == second_score or abs(best_ratio - second_ratio) < 0.06:
        return TownResolution(
            queried=queried,
            resolved=None,
            ambiguous=True,
            candidates=candidates,
        )

    return TownResolution(
        queried=queried,
        resolved=key_to_name[best_key],
        ambiguous=False,
        candidates=(),
    )


def resolve_town_in_dataset(name: str, known_towns: list[str]) -> str | None:
    """Return canonical dataset town name for an exact or high-confidence fuzzy match."""
    return resolve_town_for_plan(name, known_towns).resolved


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
