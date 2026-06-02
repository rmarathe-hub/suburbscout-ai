"""Template town profiles for semantic search (Day 3)."""

from __future__ import annotations

from typing import Any

REGION_KEYWORDS: dict[str, list[str]] = {
    "Core Boston + inner metro": ["urban-adjacent", "inner metro", "close to Boston"],
    "North Shore / northeast suburbs": ["North Shore", "northeast suburbs", "coastal access"],
    "South Shore": ["South Shore", "south of Boston", "coastal access"],
    "MetroWest": ["MetroWest", "west of Boston"],
    "Northwest / Middlesex / Route 2 / 495 belt": [
        "Route 2 corridor",
        "495 belt",
        "northwest suburbs",
    ],
    "Southeast / Route 24 / commuter edge": [
        "southeast suburbs",
        "Route 24 corridor",
        "commuter edge",
    ],
    "Worcester-area but still Boston-commutable for some": [
        "Worcester area",
        "longer commute option",
        "central Massachusetts",
    ],
}


def _fmt_money(value: float | int | None) -> str:
    if value is None:
        return "unavailable"
    return f"${int(round(value)):,}"


def _fmt_score(value: float | None, label: str) -> str:
    if value is None:
        return f"{label} data unavailable"
    return f"{label} score {value}/10 (percentile within 200-town dataset)"


def build_profile_record(suburb: dict[str, Any]) -> dict[str, Any]:
    """Build one searchable town profile from a suburbs.json record."""
    name = suburb["name"]
    region = suburb.get("region") or "Massachusetts"
    county = suburb.get("county") or "unknown"
    tags = list(suburb.get("tags") or [])
    missing = list(suburb.get("missing_fields") or [])
    tier = suburb.get("data_quality_tier") or "partial"

    lines = [
        f"{name} is a Boston-area suburb in {region}, {county} County, Massachusetts.",
    ]

    pop = suburb.get("population")
    if pop is not None:
        lines.append(f"Population: {int(pop):,}.")

    commute = suburb.get("drive_minutes_to_boston")
    if commute is not None:
        miles = suburb.get("drive_distance_miles_to_boston")
        miles_part = f" ({miles} miles)" if miles is not None else ""
        lines.append(f"Drive commute to Boston: {commute} minutes{miles_part}.")

    price = suburb.get("latest_home_price")
    year = suburb.get("home_price_year")
    if price is not None:
        year_part = f" ({int(year)})" if year is not None else ""
        lines.append(f"Latest median home price: {_fmt_money(price)}{year_part}.")
    else:
        lines.append("Latest median home price: unavailable in dataset.")

    lines.append(_fmt_score(suburb.get("school_score"), "School"))
    lines.append(_fmt_score(suburb.get("safety_score"), "Safety"))
    lines.append(_fmt_score(suburb.get("commute_score"), "Commute"))
    lines.append(_fmt_score(suburb.get("affordability_score"), "Affordability"))
    lines.append(_fmt_score(suburb.get("economic_score"), "Economic"))

    if tags:
        lines.append("Character tags: " + ", ".join(tags) + ".")

    region_kw = REGION_KEYWORDS.get(region, [])
    keywords = sorted({name, region, county, *tags, *region_kw})

    if tier == "partial" and missing:
        lines.append(
            "Data note: partial data quality; missing fields include "
            + ", ".join(missing)
            + "."
        )

    lines.append(
        "Scores are 0-10 percentile ranks within the 200-town dataset, "
        "not official government ratings."
    )

    search_text = " ".join(lines)

    return {
        "name": name,
        "region": region,
        "county": county,
        "search_text": search_text,
        "keywords": keywords,
        "tags": tags,
        "data_quality_tier": tier,
        "missing_fields": missing,
        "snapshot": {
            "population": pop,
            "latest_home_price": suburb.get("latest_home_price"),
            "home_price_year": suburb.get("home_price_year"),
            "drive_minutes_to_boston": commute,
            "school_score": suburb.get("school_score"),
            "safety_score": suburb.get("safety_score"),
            "commute_score": suburb.get("commute_score"),
            "affordability_score": suburb.get("affordability_score"),
            "family_score": suburb.get("family_score"),
        },
    }


def build_all_profiles(suburbs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build profiles for every suburb record (same order as input)."""
    return [build_profile_record(s) for s in suburbs]
