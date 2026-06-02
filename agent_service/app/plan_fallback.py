"""Rule-based QueryPlan fallback when the LLM planner fails (Phase 2 Step 3).

Narrow scope: simple recommend/rank prompts with parseable budget, commute, coastal,
or school/safety filters. Does not replace lookup, compare, or membership planning.
"""

from __future__ import annotations

import logging
import re

from app.constraint_parser import parse_constraints
from app.entity_extractor import ExtractedEntities, extract_entities
from app.plan_normalizer import normalize_planned_query, normalize_rank_preferences
from app.query_patterns import (
    is_coastal_rank_query,
    is_dataset_membership_query,
    is_open_ended_recommendation,
    is_pull_up_town_lookup,
    is_semantic_vibe_query,
)
from app.query_plan import (
    DEFAULT_RANK_LIMIT,
    PlanValidationError,
    QueryPlan,
    RankOp,
    SemanticSearchOp,
    validate_plan,
)
from app.schemas import Preferences

logger = logging.getLogger(__name__)

_RECOMMEND_RE = re.compile(
    r"\b(?:recommend|find|show|list|rank|best|top|suggest|give me|looking for|"
    r"towns under|suburbs under|safe suburb|affordable)\b",
    re.I,
)
_COMPARE_RE = re.compile(r"\b(?:compare|versus|vs\.?| vs )\b", re.I)
_LOOKUP_RE = re.compile(
    r"\b(?:what is|how much|how long|commute from|commute to|price of|school score for|"
    r"pull up|open .+ profile|median price in)\b",
    re.I,
)
_UNSUPPORTED_HINT_RE = re.compile(
    r"\b(?:zillow|mls|redfin|neighborhood in|walkability score|demographics|"
    r"diversity score|transit time|mbta)\b",
    re.I,
)


def _has_rank_signals(prefs: Preferences) -> bool:
    return bool(
        prefs.budget_max is not None
        or prefs.requires_coastal
        or prefs.max_commute_minutes is not None
        or prefs.min_commute_minutes is not None
        or prefs.school_priority == "high"
        or prefs.safety_priority == "high"
        or prefs.affordability_priority == "high"
        or prefs.commute_priority == "high"
        or prefs.region_preference
        or prefs.county_preference
        or prefs.exclude_towns
        or prefs.similar_to_town
    )


def can_rule_fallback_plan(query: str, *, entities: ExtractedEntities | None = None) -> bool:
    """True only for simple filtered recommend queries."""
    text = query.strip()
    if not text or _UNSUPPORTED_HINT_RE.search(text):
        return False
    if is_dataset_membership_query(text) or is_pull_up_town_lookup(text):
        return False
    if _COMPARE_RE.search(text):
        return False
    if _LOOKUP_RE.search(text) and not _RECOMMEND_RE.search(text):
        return False
    if is_open_ended_recommendation(text):
        return False

    entities = entities or extract_entities(text)
    if entities.compare_pair:
        return False
    if len(entities.valid_towns) >= 2 and _COMPARE_RE.search(text):
        return False

    prefs = parse_constraints(text)
    if is_coastal_rank_query(text):
        return True
    if not _has_rank_signals(prefs):
        return False
    return bool(_RECOMMEND_RE.search(text) or is_coastal_rank_query(text))


def build_rule_fallback_plan(
    query: str,
    *,
    entities: ExtractedEntities | None = None,
) -> QueryPlan:
    """Build a minimal rank (or semantic+rank) plan from parse_constraints."""
    text = query.strip()
    if not can_rule_fallback_plan(text, entities=entities):
        raise PlanValidationError("Query not eligible for rule-based plan fallback.")

    entities = entities or extract_entities(text)
    prefs = normalize_rank_preferences(text, parse_constraints(text))

    ops: list[RankOp | SemanticSearchOp] = []
    if is_semantic_vibe_query(text) and not is_coastal_rank_query(text):
        ops.append(SemanticSearchOp(query_text=text, top_k=15))
        ops.append(
            RankOp(
                preferences=prefs,
                limit=DEFAULT_RANK_LIMIT,
                use_semantic_candidates=True,
            )
        )
    else:
        ops.append(RankOp(preferences=prefs, limit=DEFAULT_RANK_LIMIT))

    plan = QueryPlan(ops=ops)
    validate_plan(plan)
    return plan


def plan_with_rule_fallback(
    query: str,
    *,
    entities: ExtractedEntities | None = None,
    apply_normalizer: bool = True,
) -> QueryPlan | None:
    """Return a validated fallback plan, or None if not eligible."""
    text = query.strip()
    if not can_rule_fallback_plan(text, entities=entities):
        return None
    plan = build_rule_fallback_plan(text, entities=entities)
    if apply_normalizer:
        plan = normalize_planned_query(text, plan)
    logger.warning(
        "Using rule-based QueryPlan fallback (%d ops): %s",
        len(plan.ops),
        [getattr(o, "op", type(o).__name__) for o in plan.ops],
    )
    return plan
