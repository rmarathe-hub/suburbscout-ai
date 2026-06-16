"""LLM-first rank preference merge with Python validation (regex fills gaps only)."""

from __future__ import annotations

import re
from typing import Any

from app.commute_intent import CommuteContext, CommuteIntent
from app.commute_service import resolve_dataset_town
from app.constraint_parser import parse_constraints
from app.query_patterns import is_inverted_crime_affordability_query
from app.query_plan import CompareOp, PlanValidationError, QueryPlan, RankOp
from app.schemas import Preferences
from app.town_normalizer import canonical_town_name

_ABSURD_BUDGET_CEILING = 50_000

_VAGUE_TOWN_TOKENS = frozenset(
    {
        "that place",
        "unknown",
        "unknown destination",
        "there",
        "somewhere",
    }
)

_INVERTED_SCHOOL_RE = re.compile(
    r"\b(?:weaker schools? (?:are |is )?acceptable|schools? not a priority|ignore schools?|"
    r"do not care about schools|don't care about schools)\b",
    re.I,
)

_BOOL_PREF_FIELDS = frozenset(
    {
        "requires_coastal",
        "prefer_high_crime",
        "allow_low_safety",
        "prefer_low_school",
        "deprioritize_safety",
        "deprioritize_schools",
        "allow_stretch_options",
        "require_housing_for_budget",
    }
)


def _is_unset(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, list) and not value:
        return True
    return False


def _has_commute_signal(
    prefs: Preferences,
    commute_intent: CommuteIntent | None,
    query: str,
) -> bool:
    if prefs.max_commute_minutes is not None or prefs.commute_destination_town:
        return True
    if commute_intent and (
        commute_intent.commute_context != CommuteContext.DEFAULT_BOSTON
        or commute_intent.commute_destination_town
    ):
        return True
    lower = query.lower()
    return bool(
        any(
            token in lower
            for token in (
                "commute",
                "drive",
                "minutes",
                "minute",
                " min",
            )
        )
    )


def _sanitize_planner_preferences(
    prefs: Preferences,
    *,
    commute_intent: CommuteIntent | None = None,
    query: str = "",
) -> Preferences:
    updates: dict[str, Any] = {}

    if prefs.budget_max is not None and prefs.budget_max <= _ABSURD_BUDGET_CEILING:
        if _has_commute_signal(prefs, commute_intent, query):
            updates["budget_max"] = None

    if prefs.commute_destination_town:
        raw = prefs.commute_destination_town.strip()
        if raw.lower() in _VAGUE_TOWN_TOKENS:
            updates["commute_destination_town"] = None
        else:
            town = resolve_dataset_town(raw)
            updates["commute_destination_town"] = canonical_town_name(town) if town else None

    if prefs.budget_max is not None:
        updates["require_housing_for_budget"] = True

    if updates:
        return prefs.model_copy(update=updates)
    return prefs


def _apply_structural_preference_fixes(query: str, prefs: Preferences) -> Preferences:
    if is_inverted_crime_affordability_query(query):
        prefs = prefs.model_copy(
            update={
                "allow_low_safety": True,
                "prefer_high_crime": True,
                "deprioritize_safety": True,
                "safety_priority": prefs.safety_priority or "low",
                "affordability_priority": prefs.affordability_priority or "high",
            }
        )
    if _INVERTED_SCHOOL_RE.search(query) or re.search(r"\bweaker schools?\b", query, re.I):
        updates: dict[str, Any] = {"deprioritize_schools": True}
        if prefs.school_priority == "high":
            updates["school_priority"] = "low"
        prefs = prefs.model_copy(update=updates)
    return prefs


def _fill_missing_from_fallback(primary: Preferences, fallback: Preferences) -> Preferences:
    primary_data = primary.model_dump()
    fallback_data = fallback.model_dump(exclude_none=True)
    updates: dict[str, Any] = {}

    for key, value in fallback_data.items():
        if key == "raw_query":
            continue
        current = primary_data.get(key)
        if key in _BOOL_PREF_FIELDS:
            if current is False and value is True:
                updates[key] = value
            continue
        if _is_unset(current) and not _is_unset(value):
            updates[key] = value

    if updates:
        return primary.model_copy(update=updates)
    return primary


def merge_rank_preferences(
    query: str,
    planner_prefs: Preferences,
    *,
    commute_intent: CommuteIntent | None = None,
    regex_fallback: bool = False,
) -> Preferences:
    """
    Prefer LLM planner preferences; validate in Python; regex fills only missing fields
    when regex_fallback=True (offline/rule-fallback paths only).
    """
    merged = planner_prefs.model_copy(deep=True)
    if not merged.raw_query:
        merged = merged.model_copy(update={"raw_query": query})

    merged = _sanitize_planner_preferences(merged, commute_intent=commute_intent, query=query)
    merged = _apply_structural_preference_fixes(query, merged)

    if commute_intent and commute_intent.max_commute_minutes is not None:
        if merged.max_commute_minutes is None:
            merged = merged.model_copy(
                update={"max_commute_minutes": commute_intent.max_commute_minutes}
            )

    if regex_fallback:
        merged = _fill_missing_from_fallback(merged, parse_constraints(query))

    if merged.allow_low_safety:
        merged = merged.model_copy(update={"prefer_high_crime": True})
    if merged.deprioritize_schools and not merged.school_priority:
        merged = merged.model_copy(update={"school_priority": "low"})

    return merged


def validate_planner_plan_semantics(plan: QueryPlan, query: str = "") -> None:
    """
    Reject common planner mistakes before execution (triggers LLM repair loop).

    Uses plan JSON only — does not re-parse natural language.
    """
    del query  # kept for call-site compatibility; not used
    intent = plan.commute_intent or CommuteIntent()

    for op in plan.ops:
        if not isinstance(op, RankOp):
            continue
        prefs = op.preferences
        if prefs.budget_max is not None and prefs.budget_max <= _ABSURD_BUDGET_CEILING:
            if (
                prefs.max_commute_minutes is not None
                or intent.max_commute_minutes is not None
                or intent.commute_context == CommuteContext.DESTINATION_TOWN
            ):
                raise PlanValidationError(
                    f"budget_max={prefs.budget_max} appears to confuse minutes with dollars; "
                    "use max_commute_minutes for drive/commute time (e.g. 30), not budget_max."
                )
        if intent.max_commute_minutes is not None:
            if prefs.max_commute_minutes is None:
                raise PlanValidationError(
                    f"commute_intent.max_commute_minutes={intent.max_commute_minutes} "
                    "but rank preferences omit max_commute_minutes."
                )
            if prefs.max_commute_minutes != intent.max_commute_minutes:
                raise PlanValidationError(
                    "rank preferences max_commute_minutes must match "
                    f"commute_intent.max_commute_minutes ({intent.max_commute_minutes})."
                )

    compare_ops = [o for o in plan.ops if isinstance(o, CompareOp)]
    if compare_ops and intent.commute_context == CommuteContext.UNSUPPORTED:
        raw_dest = (intent.commute_destination_town or "").strip().lower()
        if raw_dest in _VAGUE_TOWN_TOKENS or raw_dest == "unsupported":
            raise PlanValidationError(
                "Plain compare without commute should use "
                'commute_intent.commute_context="default_boston" and omit commute_destination_town.'
            )

