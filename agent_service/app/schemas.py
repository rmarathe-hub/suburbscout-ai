"""Pydantic models for preferences, suburbs, and ranked results."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Preferences(BaseModel):
    """Parsed user preferences for suburb ranking."""

    budget_max: int | None = None
    allow_stretch_options: bool = False
    require_housing_for_budget: bool = True
    school_priority: Literal["high", "medium", "low"] | None = None
    safety_priority: Literal["high", "medium", "low"] | None = None
    commute_priority: Literal["high", "medium", "low"] | None = None
    affordability_priority: Literal["high", "medium", "low"] | None = None
    economic_priority: Literal["high", "medium", "low"] | None = None
    max_commute_minutes: int | None = None
    min_commute_minutes: int | None = None
    requires_coastal: bool = False
    region_preference: str | None = None
    region_key: str | None = None
    county_preference: str | None = None
    prefer_high_crime: bool = False
    allow_low_safety: bool = False
    prefer_low_school: bool = False
    deprioritize_safety: bool = False
    deprioritize_schools: bool = False
    named_towns: list[str] | None = None
    unknown_towns: list[str] | None = None
    safer_than_town: str | None = None
    cheaper_than_town: str | None = None
    quieter_than_town: str | None = None
    similar_to_town: str | None = None
    candidate_towns: list[str] | None = None
    exclude_towns: list[str] | None = None
    raw_query: str | None = None


class RankedSuburb(BaseModel):
    """One ranked suburb result."""

    rank: int
    name: str
    score: float
    matched_factors: list[str]
    reasons: list[str]
    tradeoffs: list[str]
    data: dict[str, Any]


class RecommendResponse(BaseModel):
    """Structured recommendation output."""

    query: str | None = None
    preferences: dict[str, Any]
    top_matches: list[dict[str, Any]]
    tradeoff_warning: str | None = None
    final_recommendation: str | None = None
