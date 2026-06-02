"""Phase 2 Step 3 — QueryPlan / Preferences contract (machine-readable)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# Fields supported on RankOp.preferences (schemas.Preferences). Not in dataset / not ranked:
UNSUPPORTED_PREFERENCE_CONCEPTS: tuple[str, ...] = (
    "diversity",
    "walkability",
    "nightlife",
    "politics",
    "weather",
    "job market",
    "transit / MBTA routing",
    "neighborhood within a town",
    "live MLS / Zillow prices",
)

SUPPORTED_PREFERENCE_FIELDS: tuple[str, ...] = (
    "budget_max",
    "allow_stretch_options",
    "require_housing_for_budget",
    "school_priority",
    "safety_priority",
    "commute_priority",
    "affordability_priority",
    "economic_priority",
    "max_commute_minutes",
    "min_commute_minutes",
    "requires_coastal",
    "region_preference",
    "region_key",
    "county_preference",
    "prefer_high_crime",
    "allow_low_safety",
    "prefer_low_school",
    "deprioritize_safety",
    "deprioritize_schools",
    "named_towns",
    "unknown_towns",
    "safer_than_town",
    "cheaper_than_town",
    "quieter_than_town",
    "similar_to_town",
    "candidate_towns",
    "exclude_towns",
)

PLANNER_RETRY_NOTE = (
    "LLM planner retries once on invalid JSON (LLM_QUERY_PLANNER_MAX_REPAIR_ATTEMPTS, default 1). "
    "If still invalid, narrow rule fallback may build a rank plan (app.plan_fallback)."
)

PIPELINE_NOTE = (
    "User text → LLM QueryPlan (raw) → plan_normalizer → plan_trust_gates → "
    "plan_executor → optional answer LLM"
)


class PlanExample(BaseModel):
    """Canonical phrase → primary op(s) for docs and verification."""

    phrase: str
    expected_ops: list[str]
    notes: str = ""


CANONICAL_PLAN_EXAMPLES: tuple[PlanExample, ...] = (
    PlanExample(
        phrase="What is the commute from Maynard?",
        expected_ops=["lookup"],
        notes="Single-town field lookup (commute), not membership.",
    ),
    PlanExample(
        phrase="Compare Acton and Framingham on schools and safety",
        expected_ops=["compare"],
        notes="Multi-town column compare from suburbs.json.",
    ),
    PlanExample(
        phrase="Safe suburb under $900k with good schools",
        expected_ops=["rank"],
        notes="budget_max + safety/school priorities → deterministic rank.",
    ),
    PlanExample(
        phrase="Quiet North Shore town with a coastal feel",
        expected_ops=["semantic_search", "rank"],
        notes="Vibe narrows candidates; rank uses use_semantic_candidates.",
    ),
    PlanExample(
        phrase="Which neighborhood in Brookline is best for kids?",
        expected_ops=["unsupported"],
        notes="Neighborhood granularity → trust gate / refusal.",
    ),
)


def preferences_field_docs() -> list[dict[str, str]]:
    """Short descriptions for PLAN_CONTRACT.md generation."""
    return [
        {"field": "budget_max", "description": "Max home price (USD); excludes towns without housing when required"},
        {"field": "max_commute_minutes / min_commute_minutes", "description": "Drive time to COMMUTE_DESTINATION"},
        {"field": "requires_coastal", "description": "Filter to coastal towns list"},
        {"field": "school_priority / safety_priority / commute_priority / affordability_priority", "description": "high | medium | low ranking weights"},
        {"field": "deprioritize_schools / deprioritize_safety", "description": "Invert or soften those dimensions"},
        {"field": "allow_low_safety / prefer_high_crime", "description": "Inverted crime/affordability tradeoffs"},
        {"field": "exclude_towns / named_towns / candidate_towns", "description": "Town set constraints"},
        {"field": "region_preference / county_preference", "description": "Geographic filters"},
        {"field": "similar_to_town", "description": "Often paired with semantic_search + rank"},
    ]


def example_as_dict(example: PlanExample) -> dict[str, Any]:
    return example.model_dump()
