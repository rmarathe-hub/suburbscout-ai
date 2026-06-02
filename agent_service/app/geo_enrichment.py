"""Curated geographic enrichment for suburbs.json (Phase 1.1)."""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

from app.config import DATA_DIR
from app.town_normalizer import canonical_town_name, normalize_key

COASTAL_TOWNS_PATH = DATA_DIR / "coastal_towns.csv"

# Stable slug for each product region label (used in filters / parser).
REGION_KEY_MAP: dict[str, str] = {
    "Core Boston + inner metro": "core_boston_inner_metro",
    "North Shore / northeast suburbs": "north_shore",
    "Northwest / Middlesex / Route 2 / 495 belt": "northwest_route_2_495",
    "MetroWest": "metrowest",
    "South Shore": "south_shore",
    "Southeast / Route 24 / commuter edge": "southeast_route_24",
    "Worcester-area but still Boston-commutable for some": "worcester_area",
}

# Explicit non-coastal spot-checks for QA (inland towns often returned for "coastal" queries).
NON_COASTAL_SPOT_CHECKS: tuple[str, ...] = (
    "Reading",
    "Boxford",
    "Acton",
    "Framingham",
    "Wellesley",
    "Bedford",
)


@lru_cache(maxsize=1)
def load_coastal_town_keys() -> frozenset[str]:
    """Normalized town keys curated as coastal (Atlantic / major harbor frontage)."""
    if not COASTAL_TOWNS_PATH.exists():
        return frozenset()

    keys: set[str] = set()
    with open(COASTAL_TOWNS_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            town = (row.get("town") or "").strip()
            flag = (row.get("is_coastal") or "").strip().lower()
            if town and flag in ("true", "1", "yes"):
                keys.add(normalize_key(canonical_town_name(town)))
    return frozenset(keys)


def region_key_for_label(region: str | None) -> str | None:
    """Map display region label to stable region_key slug."""
    if not region:
        return None
    return REGION_KEY_MAP.get(region.strip())


def coastal_enrichment_for_town(town_name: str) -> dict[str, object]:
    """Return is_coastal flags for one town."""
    key = normalize_key(canonical_town_name(town_name))
    is_coastal = key in load_coastal_town_keys()
    return {
        "is_coastal": is_coastal,
        "is_coastal_source": "curated" if is_coastal else None,
    }


def apply_geo_enrichment(record: dict) -> dict:
    """Add is_coastal, region_key to a suburb record (mutates copy)."""
    out = dict(record)
    town = out.get("name") or ""
    coastal = coastal_enrichment_for_town(town)
    out["is_coastal"] = coastal["is_coastal"]
    out["is_coastal_source"] = coastal["is_coastal_source"]
    out["region_key"] = region_key_for_label(out.get("region"))
    return out
