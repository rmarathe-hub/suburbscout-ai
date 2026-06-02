"""Deterministic suburb ranking using suburbs.json only."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.constraint_parser import parse_constraints
from app.config import DEFAULT_RANKING_WEIGHTS, DEMO_MODE_FULL_DATA_ONLY, SUBURBS_JSON_PATH
from app.schemas import Preferences
from app.town_normalizer import matches_town, normalize_key
from app.town_normalizer import canonical_town_name, normalize_key

FACTOR_MAP = {
    "schools": ("school_score", "school_priority"),
    "safety": ("safety_score", "safety_priority"),
    "commute": ("commute_score", "commute_priority"),
    "affordability": ("affordability_score", "affordability_priority"),
    "economic": ("economic_score", "economic_priority"),
}


def load_suburbs(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or SUBURBS_JSON_PATH
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def parse_preferences_from_query(query: str) -> Preferences:
    """Parse user query into structured preferences (delegates to constraint_parser)."""
    return parse_constraints(query)


def _suburb_by_name(name: str | None, suburbs: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not name:
        return None
    key = normalize_key(canonical_town_name(name))
    for suburb in suburbs:
        if normalize_key(suburb["name"]) == key:
            return suburb
    return None


def _passes_hard_filters(
    suburb: dict[str, Any],
    preferences: Preferences,
    suburbs: list[dict[str, Any]],
) -> bool:
    """Exclude towns that violate explicit hard constraints."""
    if preferences.requires_coastal and not suburb.get("is_coastal"):
        return False

    if preferences.county_preference:
        county = (suburb.get("county") or "").lower()
        if county != preferences.county_preference.lower():
            return False

    if preferences.region_preference:
        if suburb.get("region") != preferences.region_preference:
            return False
    elif preferences.region_key:
        if suburb.get("region_key") != preferences.region_key:
            return False

    minutes = suburb.get("drive_minutes_to_boston")
    if preferences.max_commute_minutes is not None:
        if minutes is None or minutes > preferences.max_commute_minutes:
            return False

    if preferences.min_commute_minutes is not None:
        if minutes is None or minutes < preferences.min_commute_minutes:
            return False

    if preferences.budget_max is not None and preferences.require_housing_for_budget:
        price = suburb.get("latest_home_price")
        if price is None or float(price) > preferences.budget_max:
            return False

    if preferences.exclude_towns:
        name = suburb.get("name") or ""
        for excluded in preferences.exclude_towns:
            if matches_town(name, excluded) or normalize_key(name) == normalize_key(excluded):
                return False

    safer_ref = _suburb_by_name(preferences.safer_than_town, suburbs)
    if safer_ref is not None:
        sub_safety = suburb.get("safety_score")
        ref_safety = safer_ref.get("safety_score")
        if sub_safety is not None and ref_safety is not None and sub_safety <= ref_safety:
            return False

    cheaper_ref = _suburb_by_name(preferences.cheaper_than_town, suburbs)
    if cheaper_ref is not None:
        sub_price = suburb.get("latest_home_price")
        ref_price = cheaper_ref.get("latest_home_price")
        if sub_price is None:
            return False
        if ref_price is not None and sub_price >= ref_price:
            return False

    quieter_ref = _suburb_by_name(preferences.quieter_than_town, suburbs)
    if quieter_ref is not None:
        sub_crime = suburb.get("crime_rate_per_1000")
        ref_crime = quieter_ref.get("crime_rate_per_1000")
        if sub_crime is not None and ref_crime is not None:
            if sub_crime >= ref_crime:
                return False
        else:
            sub_pop = suburb.get("population")
            ref_pop = quieter_ref.get("population")
            if (
                sub_pop is not None
                and ref_pop is not None
                and sub_pop >= ref_pop
            ):
                return False

    return True


def describe_active_filters(preferences: Preferences) -> list[str]:
    """Human-readable list of hard filters applied for this query."""
    labels: list[str] = []
    if preferences.requires_coastal:
        labels.append("coastal towns only")
    if preferences.county_preference:
        labels.append(f"county={preferences.county_preference}")
    if preferences.region_preference:
        labels.append(f"region={preferences.region_preference}")
    if preferences.max_commute_minutes is not None:
        labels.append(f"commute<={preferences.max_commute_minutes} min")
    if preferences.min_commute_minutes is not None:
        labels.append(f"commute>={preferences.min_commute_minutes} min")
    if preferences.budget_max is not None:
        labels.append(f"budget<=${preferences.budget_max:,}")
    if preferences.exclude_towns:
        labels.append(f"exclude={', '.join(preferences.exclude_towns)}")
    if preferences.safer_than_town:
        labels.append(f"safer than {preferences.safer_than_town}")
    if preferences.cheaper_than_town:
        labels.append(f"cheaper than {preferences.cheaper_than_town}")
    if preferences.quieter_than_town:
        labels.append(f"quieter than {preferences.quieter_than_town}")
    if preferences.candidate_towns:
        labels.append(f"candidate pool ({len(preferences.candidate_towns)} towns)")
    if preferences.prefer_high_crime:
        labels.append("high-crime ranking mode")
    return labels


def _priority_multiplier(priority: str | None) -> float:
    return {"high": 1.5, "medium": 1.0, "low": 0.5}.get(priority or "medium", 1.0)


def _budget_penalty(price: float | None, budget_max: int | None) -> tuple[float, str | None]:
    """Return multiplier (<=1) and optional exclusion reason."""
    if budget_max is None or price is None:
        return 1.0, None
    if price <= budget_max:
        return 1.0, None
    over_pct = (price - budget_max) / budget_max * 100
    if over_pct <= 10:
        return 0.92, "slightly over budget"
    if over_pct <= 25:
        return 0.75, "moderately over budget"
    return 0.0, "over 25% above budget"


def rank_suburbs(
    preferences: Preferences | dict,
    top_n: int = 5,
    suburbs: list[dict] | None = None,
    demo_full_data_only: bool | None = None,
) -> list[dict[str, Any]]:
    """
    Rank suburbs deterministically.

    - Applies hard filters for coastal, county, region, commute min/max, and relative constraints.
    - Skips null score factors and renormalizes weights.
    - Excludes towns without latest_home_price for budget queries by default.
    - Applies budget penalty bands when stretch is allowed.
    - Returns empty list when no towns match (no invented results).
    """
    if isinstance(preferences, dict):
        preferences = Preferences(**preferences)

    if suburbs is None:
        suburbs = load_suburbs()

    demo_full = DEMO_MODE_FULL_DATA_ONLY if demo_full_data_only is None else demo_full_data_only
    budget_query = preferences.budget_max is not None

    candidates = suburbs
    if preferences.candidate_towns:
        allowed = {t.lower() for t in preferences.candidate_towns}
        candidates = [s for s in suburbs if s["name"].lower() in allowed]

    if demo_full:
        candidates = [s for s in candidates if s.get("data_quality_tier") == "full"]

    ranked: list[dict[str, Any]] = []

    for suburb in candidates:
        name = suburb["name"]
        missing = suburb.get("missing_fields") or []

        if not _passes_hard_filters(suburb, preferences, suburbs):
            continue

        if budget_query and preferences.require_housing_for_budget:
            if suburb.get("latest_home_price") is None:
                continue

        active_weights: dict[str, float] = {}
        matched_factors: list[str] = []
        factor_scores: dict[str, float] = {}

        for factor, (score_field, priority_field) in FACTOR_MAP.items():
            score = suburb.get(score_field)
            if score is None:
                continue
            priority = getattr(preferences, priority_field, None)
            weight = DEFAULT_RANKING_WEIGHTS[factor] * _priority_multiplier(priority)
            score_val = float(score)

            if factor == "safety" and (
                preferences.prefer_high_crime or preferences.allow_low_safety
            ):
                score_val = 10.0 - float(score)
            elif factor == "schools" and preferences.prefer_low_school:
                score_val = 10.0 - float(score)
            elif (
                factor == "safety"
                and preferences.deprioritize_safety
                and preferences.affordability_priority == "high"
            ):
                weight *= 0.5
                score_val = 10.0 - float(score)
            elif factor == "safety" and preferences.deprioritize_safety:
                weight *= 0.35
            elif factor == "schools" and preferences.deprioritize_schools:
                weight *= 0.35
            elif factor == "commute" and priority == "low":
                weight *= 0.4

            active_weights[factor] = weight
            factor_scores[factor] = score_val
            matched_factors.append(factor)

        if not active_weights:
            continue

        weight_sum = sum(active_weights.values())
        base_score = sum(
            factor_scores[f] * (active_weights[f] / weight_sum) for f in active_weights
        )

        price = suburb.get("latest_home_price")
        penalty, penalty_reason = _budget_penalty(
            float(price) if price is not None else None,
            preferences.budget_max,
        )

        if penalty == 0.0 and not preferences.allow_stretch_options:
            continue

        final_score = round(min(base_score * penalty, 10.0), 2)

        reasons = []
        for factor in matched_factors:
            score_field = FACTOR_MAP[factor][0]
            val = suburb.get(score_field)
            reasons.append(f"{factor.replace('_', ' ').title()} score: {val}/10")

        if suburb.get("latest_home_price") is not None:
            reasons.append(
                f"Latest home price: ${suburb['latest_home_price']:,} ({suburb.get('home_price_year')})"
            )
        elif "latest_home_price" in missing:
            reasons.append("Housing price data unavailable for this town.")

        if suburb.get("drive_minutes_to_boston") is not None:
            reasons.append(
                f"Drive to Boston: {suburb['drive_minutes_to_boston']} min "
                f"({suburb.get('drive_distance_miles_to_boston')} mi)"
            )

        if suburb.get("crime_rate_per_1000") is not None:
            reasons.append(f"Crime rate: {suburb['crime_rate_per_1000']} per 1,000")

        tradeoffs = []
        if penalty_reason:
            tradeoffs.append(penalty_reason)
        if suburb.get("data_quality_tier") == "partial":
            tradeoffs.append(
                f"Partial data quality — missing: {', '.join(missing) if missing else 'none'}"
            )
        if preferences.max_commute_minutes and suburb.get("drive_minutes_to_boston"):
            tradeoffs.append(
                f"Commute {suburb['drive_minutes_to_boston']} min vs your {preferences.max_commute_minutes} min target"
            )

        ranked.append(
            {
                "name": name,
                "score": final_score,
                "matched_factors": matched_factors,
                "reasons": reasons,
                "tradeoffs": tradeoffs,
                "data": {
                    "region": suburb.get("region"),
                    "region_key": suburb.get("region_key"),
                    "county": suburb.get("county"),
                    "is_coastal": suburb.get("is_coastal"),
                    "data_quality_tier": suburb.get("data_quality_tier"),
                    "latest_home_price": suburb.get("latest_home_price"),
                    "school_score": suburb.get("school_score"),
                    "safety_score": suburb.get("safety_score"),
                    "commute_score": suburb.get("commute_score"),
                    "affordability_score": suburb.get("affordability_score"),
                    "economic_score": suburb.get("economic_score"),
                    "family_score": suburb.get("family_score"),
                    "drive_minutes_to_boston": suburb.get("drive_minutes_to_boston"),
                    "crime_rate_per_1000": suburb.get("crime_rate_per_1000"),
                    "missing_fields": missing,
                },
            }
        )

    if preferences.prefer_high_crime:
        ranked.sort(
            key=lambda x: (
                x.get("data", {}).get("crime_rate_per_1000") is None,
                -(x.get("data", {}).get("crime_rate_per_1000") or 0),
                x["score"],
            )
        )
    elif preferences.prefer_low_school:
        ranked.sort(
            key=lambda x: (
                x.get("data", {}).get("school_score") is None,
                x.get("data", {}).get("school_score") or 0,
                -x["score"],
            )
        )
    elif preferences.deprioritize_safety and preferences.affordability_priority == "high":
        ranked.sort(
            key=lambda x: (
                x.get("data", {}).get("affordability_score") is None,
                -(x.get("data", {}).get("affordability_score") or 0),
                x.get("data", {}).get("safety_score") is None,
                x.get("data", {}).get("safety_score") or 10,
                x["score"],
            )
        )
    else:
        ranked.sort(key=lambda x: x["score"], reverse=True)
    for i, item in enumerate(ranked[:top_n], start=1):
        item["rank"] = i

    return ranked[:top_n]
