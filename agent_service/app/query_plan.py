"""Phase 1 — structured query plans for the two-stage query agent.

LLM planners emit JSON matching these models; ``validate_plan`` enforces limits
and field allowlists before execution (Phase 2 ``plan_executor``).
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field, field_validator, model_validator

from app.commute_intent import CommuteIntent
from app.commute_service import resolve_dataset_town
from app.query_patterns import MAX_MULTI_COMPARE_TOWNS, MAX_MULTI_LOOKUP_SPECS
from app.schemas import Preferences
from app.town_normalizer import canonical_town_name

MAX_PLAN_OPS = 12
MAX_RANK_LIMIT = 30
MAX_SEMANTIC_TOP_K = 30
MIN_SEMANTIC_TOP_K = 1
MIN_RANK_LIMIT = 1
DEFAULT_RANK_LIMIT = 10
DEFAULT_COMPARE_COLUMNS: tuple[str, ...] = (
    "latest_home_price",
    "drive_minutes_to_boston",
    "safety_score",
    "school_score",
)


class LookupFieldKind(StrEnum):
    """Logical lookup field (executor maps to suburbs.json keys)."""

    SUMMARY = "summary"
    COMMUTE = "commute"
    PRICE = "price"
    SCHOOL = "school"
    SAFETY = "safety"
    COASTAL = "coastal"
    REGION = "region"
    MISSING = "missing"
    TIER = "tier"


class UnsupportedCategory(StrEnum):
    """Out-of-scope request categories (aligned with lookup_schema)."""

    LIVE_MARKET = "live_market"
    NEIGHBORHOOD = "neighborhood"
    SAFETY_GRANULAR = "safety_granular"
    SCHOOL_DETAIL = "school_detail"
    DEMOGRAPHICS = "demographics"
    TRANSIT = "transit"
    LIFESTYLE = "lifestyle"
    OTHER = "other"


# suburbs.json keys safe for compare tables and direct field fetch
ALLOWED_DATASET_FIELDS: frozenset[str] = frozenset(
    {
        "name",
        "region",
        "county",
        "population",
        "latest_home_price",
        "home_price_year",
        "dor_income_per_capita",
        "eqv_per_capita",
        "economic_score",
        "crime_rate_per_1000",
        "safety_score",
        "drive_minutes_to_boston",
        "drive_distance_miles_to_boston",
        "commute_score",
        "school_score",
        "affordability_score",
        "family_score",
        "missing_fields",
        "data_quality_tier",
        "data_sources",
        "tags",
        "is_coastal",
        "is_coastal_source",
        "region_key",
    }
)

ALLOWED_LOOKUP_FIELDS: frozenset[str] = frozenset(f.value for f in LookupFieldKind)

# Aliases the planner may emit → canonical LookupFieldKind or dataset column
FIELD_ALIASES: dict[str, str] = {
    "commute": LookupFieldKind.COMMUTE.value,
    "drive_time": LookupFieldKind.COMMUTE.value,
    "drive_minutes": LookupFieldKind.COMMUTE.value,
    "drive_minutes_to_boston": LookupFieldKind.COMMUTE.value,
    "drive_distance_miles_to_boston": LookupFieldKind.COMMUTE.value,
    "commute_score": LookupFieldKind.COMMUTE.value,
    "price": LookupFieldKind.PRICE.value,
    "housing": LookupFieldKind.PRICE.value,
    "home_price": LookupFieldKind.PRICE.value,
    "latest_home_price": LookupFieldKind.PRICE.value,
    "affordability": LookupFieldKind.PRICE.value,
    "affordability_score": LookupFieldKind.PRICE.value,
    "school": LookupFieldKind.SCHOOL.value,
    "schools": LookupFieldKind.SCHOOL.value,
    "school_score": LookupFieldKind.SCHOOL.value,
    "safety": LookupFieldKind.SAFETY.value,
    "crime": LookupFieldKind.SAFETY.value,
    "crime_rate": LookupFieldKind.SAFETY.value,
    "crime_rate_per_1000": LookupFieldKind.SAFETY.value,
    "safety_score": LookupFieldKind.SAFETY.value,
    "coastal": LookupFieldKind.COASTAL.value,
    "is_coastal": LookupFieldKind.COASTAL.value,
    "region": LookupFieldKind.REGION.value,
    "county": LookupFieldKind.REGION.value,
    "region_key": LookupFieldKind.REGION.value,
    "missing": LookupFieldKind.MISSING.value,
    "missing_fields": LookupFieldKind.MISSING.value,
    "tier": LookupFieldKind.TIER.value,
    "data_quality": LookupFieldKind.TIER.value,
    "data_quality_tier": LookupFieldKind.TIER.value,
    "summary": LookupFieldKind.SUMMARY.value,
    "profile": LookupFieldKind.SUMMARY.value,
    "facts": LookupFieldKind.SUMMARY.value,
}


class PlanValidationError(ValueError):
    """Raised when a query plan fails structural validation."""


_PLACEHOLDER_TOWN_RE = re.compile(
    r"^(?:town_name_|placeholder|example_town|test_town|fake_town|sample_town|"
    r"unknown_town|town_\d+)",
    re.I,
)


def assert_valid_plan_town_name(name: str) -> str:
    """Reject planner placeholder town tokens."""
    stripped = (name or "").strip()
    if not stripped:
        raise PlanValidationError("Town name cannot be empty.")
    if _PLACEHOLDER_TOWN_RE.search(stripped.replace(" ", "_")):
        raise PlanValidationError(
            f"Invalid placeholder town name '{stripped}'. Use a real MA town from the dataset."
        )
    return stripped


class LookupItem(BaseModel):
    """One town + one logical field to retrieve."""

    town: str = Field(min_length=1, max_length=120)
    field: str = Field(min_length=1, max_length=64)

    @field_validator("town", "field", mode="before")
    @classmethod
    def _strip_strings(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class LookupOp(BaseModel):
    op: Literal["lookup"] = "lookup"
    items: list[LookupItem] = Field(min_length=1, max_length=MAX_MULTI_LOOKUP_SPECS)


class CompareOp(BaseModel):
    op: Literal["compare"] = "compare"
    towns: list[str] = Field(min_length=2, max_length=MAX_MULTI_COMPARE_TOWNS)
    columns: list[str] | None = Field(
        default=None,
        description="suburbs.json column keys; defaults to core compare columns if omitted",
    )
    commute_destination_town: str | None = Field(
        default=None,
        description="When set, compare includes drive time to this dataset town",
    )

    @field_validator("towns", mode="before")
    @classmethod
    def _strip_towns(cls, value: Any) -> Any:
        if isinstance(value, list):
            return [t.strip() for t in value if isinstance(t, str) and t.strip()]
        return value


class RankOp(BaseModel):
    op: Literal["rank"] = "rank"
    preferences: Preferences = Field(default_factory=Preferences)
    limit: int = Field(default=DEFAULT_RANK_LIMIT, ge=MIN_RANK_LIMIT, le=MAX_RANK_LIMIT)
    use_semantic_candidates: bool = Field(
        default=False,
        description="If true, executor may intersect rank with prior semantic_search op in same plan",
    )


class SemanticSearchOp(BaseModel):
    op: Literal["semantic_search"] = "semantic_search"
    query_text: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=15, ge=MIN_SEMANTIC_TOP_K, le=MAX_SEMANTIC_TOP_K)

    @field_validator("query_text", mode="before")
    @classmethod
    def _strip_query(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class MembershipOp(BaseModel):
    """Dataset scope check — is this town in suburbs.json?"""

    op: Literal["membership"] = "membership"
    town: str = Field(min_length=1, max_length=120)

    @field_validator("town", mode="before")
    @classmethod
    def _strip_town(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class CommutePairOp(BaseModel):
    """Point-to-point commute between two dataset towns (Phase 8.5)."""

    op: Literal["commute_pair"] = "commute_pair"
    origin_town: str = Field(min_length=1, max_length=120)
    destination_town: str = Field(min_length=1, max_length=120)

    @field_validator("origin_town", "destination_town", mode="before")
    @classmethod
    def _strip_towns(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


class UnsupportedOp(BaseModel):
    op: Literal["unsupported"] = "unsupported"
    category: UnsupportedCategory = UnsupportedCategory.OTHER
    reason: str = Field(min_length=1, max_length=500)
    user_message_hint: str | None = Field(
        default=None,
        max_length=500,
        description="Optional short hint for answer stage; must not invent facts",
    )

    @field_validator("reason", mode="before")
    @classmethod
    def _strip_reason(cls, value: Any) -> Any:
        if isinstance(value, str):
            return value.strip()
        return value


PlanOp = Annotated[
    Union[
        LookupOp,
        CompareOp,
        RankOp,
        SemanticSearchOp,
        MembershipOp,
        CommutePairOp,
        UnsupportedOp,
    ],
    Field(discriminator="op"),
]


class QueryPlan(BaseModel):
    """Ordered operations to run against suburbs.json (+ optional vector index)."""

    ops: list[PlanOp] = Field(min_length=1, max_length=MAX_PLAN_OPS)
    commute_intent: CommuteIntent | None = Field(
        default=None,
        description="Planner-emitted commute slots; validated before execution",
    )
    user_intent_summary: str | None = Field(
        default=None,
        max_length=500,
        description="Planner-only note; not shown to user as fact",
    )

    @field_validator("user_intent_summary", mode="before")
    @classmethod
    def _strip_summary(cls, value: Any) -> Any:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


def normalize_lookup_field(raw: str) -> str:
    """Map planner field strings to canonical LookupFieldKind values."""
    key = (raw or "").strip().lower().replace(" ", "_")
    if not key:
        raise PlanValidationError("Lookup field cannot be empty.")
    if key in ALLOWED_LOOKUP_FIELDS:
        return key
    if key in FIELD_ALIASES:
        return FIELD_ALIASES[key]
    raise PlanValidationError(
        f"Unknown lookup field '{raw}'. Allowed: {', '.join(sorted(ALLOWED_LOOKUP_FIELDS))}."
    )


def normalize_compare_column(raw: str) -> str:
    """Map planner column names to suburbs.json keys."""
    key = (raw or "").strip()
    if not key:
        raise PlanValidationError("Compare column cannot be empty.")
    lower = key.lower().replace(" ", "_")
    if lower in FIELD_ALIASES:
        mapped = FIELD_ALIASES[lower]
        if mapped in ALLOWED_DATASET_FIELDS:
            return mapped
        # logical field → default dataset column for compare
        return _lookup_field_to_dataset_keys(mapped)[0]
    if lower in ALLOWED_DATASET_FIELDS:
        return lower
    if lower in FIELD_ALIASES.values():
        return _lookup_field_to_dataset_keys(lower)[0]
    raise PlanValidationError(
        f"Unknown compare column '{raw}'. Allowed dataset keys include: "
        f"{', '.join(sorted(ALLOWED_DATASET_FIELDS))}."
    )


def _lookup_field_to_dataset_keys(field: str) -> list[str]:
    """Primary suburbs.json keys used when a logical lookup field appears in compare."""
    mapping: dict[str, list[str]] = {
        LookupFieldKind.COMMUTE.value: ["drive_minutes_to_boston", "drive_distance_miles_to_boston"],
        LookupFieldKind.PRICE.value: ["latest_home_price"],
        LookupFieldKind.SCHOOL.value: ["school_score"],
        LookupFieldKind.SAFETY.value: ["safety_score", "crime_rate_per_1000"],
        LookupFieldKind.COASTAL.value: ["is_coastal"],
        LookupFieldKind.REGION.value: ["region", "county"],
        LookupFieldKind.MISSING.value: ["missing_fields"],
        LookupFieldKind.TIER.value: ["data_quality_tier"],
        LookupFieldKind.SUMMARY.value: list(DEFAULT_COMPARE_COLUMNS),
    }
    return mapping.get(field, [field])


def lookup_field_dataset_keys(field: str) -> list[str]:
    """Return suburbs.json keys to read for a canonical lookup field."""
    canonical = normalize_lookup_field(field)
    return _lookup_field_to_dataset_keys(canonical)


def _normalize_lookup_op(op: LookupOp) -> LookupOp:
    items: list[LookupItem] = []
    seen: set[tuple[str, str]] = set()
    for item in op.items:
        town = assert_valid_plan_town_name(item.town)
        field = normalize_lookup_field(item.field)
        key = (town.lower(), field)
        if key in seen:
            continue
        seen.add(key)
        items.append(LookupItem(town=town, field=field))
    if not items:
        raise PlanValidationError("Lookup op must include at least one town+field pair.")
    if len(items) > MAX_MULTI_LOOKUP_SPECS:
        raise PlanValidationError(
            f"Lookup op exceeds {MAX_MULTI_LOOKUP_SPECS} items (got {len(items)})."
        )
    return LookupOp(items=items)


def _normalize_compare_op(op: CompareOp) -> CompareOp:
    towns = []
    seen_towns: set[str] = set()
    for name in op.towns:
        stripped = assert_valid_plan_town_name(name)
        norm = stripped.lower()
        if norm in seen_towns:
            continue
        seen_towns.add(norm)
        towns.append(stripped)
    if len(towns) < 2:
        raise PlanValidationError("Compare op requires at least two distinct towns.")
    if len(towns) > MAX_MULTI_COMPARE_TOWNS:
        raise PlanValidationError(
            f"Compare op exceeds {MAX_MULTI_COMPARE_TOWNS} towns (got {len(towns)})."
        )
    columns: list[str] | None = None
    if op.columns is not None:
        cols: list[str] = []
        seen_cols: set[str] = set()
        for raw in op.columns:
            col = normalize_compare_column(raw)
            if col not in seen_cols:
                seen_cols.add(col)
                cols.append(col)
        if not cols:
            raise PlanValidationError("Compare op columns list cannot be empty when provided.")
        columns = cols
    dest_town = op.commute_destination_town
    if dest_town:
        resolved = resolve_dataset_town(dest_town)
        if resolved:
            dest_town = canonical_town_name(resolved)
    return CompareOp(
        towns=towns,
        columns=columns,
        commute_destination_town=dest_town,
    )


def _count_towns_in_plan(plan: QueryPlan) -> int:
    names: set[str] = set()
    for op in plan.ops:
        if isinstance(op, LookupOp):
            for item in op.items:
                names.add(item.town.lower())
        elif isinstance(op, CompareOp):
            for town in op.towns:
                names.add(town.lower())
    return len(names)


def validate_plan(raw: QueryPlan | dict[str, Any]) -> QueryPlan:
    """
    Parse and normalize a query plan.

    Raises:
        PlanValidationError: structural or policy violations
        pydantic.ValidationError: malformed JSON shapes
    """
    plan = raw if isinstance(raw, QueryPlan) else QueryPlan.model_validate(raw)

    if not plan.ops:
        raise PlanValidationError("Query plan must include at least one op.")

    if len(plan.ops) > MAX_PLAN_OPS:
        raise PlanValidationError(f"Query plan exceeds {MAX_PLAN_OPS} operations.")

    normalized_ops: list[PlanOp] = []
    unsupported_only = True

    for op in plan.ops:
        if isinstance(op, LookupOp):
            unsupported_only = False
            normalized_ops.append(_normalize_lookup_op(op))
        elif isinstance(op, CompareOp):
            unsupported_only = False
            normalized_ops.append(_normalize_compare_op(op))
        elif isinstance(op, RankOp):
            unsupported_only = False
            normalized_ops.append(op)
        elif isinstance(op, SemanticSearchOp):
            unsupported_only = False
            normalized_ops.append(op)
        elif isinstance(op, MembershipOp):
            unsupported_only = False
            normalized_ops.append(MembershipOp(town=assert_valid_plan_town_name(op.town)))
        elif isinstance(op, CommutePairOp):
            unsupported_only = False
            normalized_ops.append(
                CommutePairOp(
                    origin_town=assert_valid_plan_town_name(op.origin_town),
                    destination_town=assert_valid_plan_town_name(op.destination_town),
                )
            )
        elif isinstance(op, UnsupportedOp):
            normalized_ops.append(op)
        else:
            raise PlanValidationError(f"Unknown op type: {op!r}")

    if unsupported_only and len(normalized_ops) > 1:
        raise PlanValidationError(
            "Multiple unsupported ops in one plan; combine into a single unsupported op."
        )

    normalized = QueryPlan(
        ops=normalized_ops,
        commute_intent=plan.commute_intent,
        user_intent_summary=plan.user_intent_summary,
    )
    town_count = _count_towns_in_plan(normalized)
    if town_count > MAX_MULTI_COMPARE_TOWNS:
        raise PlanValidationError(
            f"Plan names {town_count} distinct towns; max is {MAX_MULTI_COMPARE_TOWNS}."
        )
    return normalized


def parse_plan_json(text: str) -> QueryPlan:
    """Parse JSON string (optionally fenced in markdown) into a validated QueryPlan."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise PlanValidationError(f"Invalid JSON for query plan: {exc}") from exc
    if not isinstance(payload, dict):
        raise PlanValidationError("Query plan JSON must be an object.")
    return validate_plan(payload)


def plan_json_schema() -> dict[str, Any]:
    """JSON Schema for LLM structured output (OpenAI response_format / tool schema)."""
    return QueryPlan.model_json_schema()


def plan_schema_prompt_block() -> str:
    """Compact schema description for system prompts."""
    return (
        "QueryPlan JSON: { "
        f'"ops": [1-{MAX_PLAN_OPS} op], optional "commute_intent", optional "user_intent_summary" }}. '
        "commute_intent (always include when commute/workplace/proximity is mentioned): "
        "{ commute_destination_town, commute_origin_town, compare_towns[], "
        'commute_context: "default_boston" | "destination_town" | "unsupported", '
        "optional max_commute_minutes }. "
        "When user states a drive-time cap, set max_commute_minutes on commute_intent AND rank preferences. "
        "Plain compare with no workplace → commute_context=default_boston only (omit commute_destination_town). "
        "Multi-town compare on schools/safety/price → op compare with columns, not lookup. "
        "Set commute_context=destination_town only for towns in the 200-town dataset; "
        "unsupported for Providence/Hartford/Manhattan/Logan Airport etc. "
        "compare_towns = the two towns being compared (NOT the workplace destination). "
        "Rank preferences semantics: max_commute_minutes = drive TIME (e.g. 30 for 'under 30 minutes'); "
        "budget_max = home price in dollars (e.g. 850000 for 850k). "
        "Never encode minute caps as budget_max (e.g. budget_max=30000 for 'drive under 30' is wrong). "
        "Ops (discriminator 'op'): "
        f'lookup — items[{{town, field}}], max {MAX_MULTI_LOOKUP_SPECS} items, '
        f"fields one of: {', '.join(sorted(ALLOWED_LOOKUP_FIELDS))}; "
        f"compare — towns[2-{MAX_MULTI_COMPARE_TOWNS}], optional columns, optional commute_destination_town; "
        f"rank — preferences object, limit 1-{MAX_RANK_LIMIT}; "
        f"semantic_search — query_text, top_k 1-{MAX_SEMANTIC_TOP_K}; "
        "membership — town (yes/no dataset scope, NOT summary lookup); "
        "unsupported — category, reason. "
        "Do not invent towns or fields outside the 200-town suburbs.json dataset."
    )
