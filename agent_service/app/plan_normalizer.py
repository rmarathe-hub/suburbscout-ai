"""Post-process LLM QueryPlans: membership, coastal rank, semantic chain, prefs, towns."""

from __future__ import annotations

import re
from typing import Any

from app.constraint_parser import parse_constraints
from app.entity_extractor import extract_entities, primary_town
from app.query_patterns import (
    extract_pull_up_town_name,
    is_coastal_rank_query,
    is_dataset_membership_query,
    is_inverted_crime_affordability_query,
    is_neighborhood_level_query,
    is_pull_up_town_lookup,
    is_semantic_vibe_query,
)
from app.query_plan import (
    CompareOp,
    LookupFieldKind,
    LookupOp,
    MembershipOp,
    PlanValidationError,
    QueryPlan,
    RankOp,
    SemanticSearchOp,
    UnsupportedOp,
    assert_valid_plan_town_name,
    validate_plan,
)
from app.ranking import load_suburbs
from app.schemas import Preferences
from app.town_normalizer import canonical_town_name, normalize_key, resolve_town_in_dataset

# Tokens the planner often mis-extracts as town names from NL prompts.
JUNK_UNKNOWN_TOWNS: frozenset[str] = frozenset(
    {
        "long",
        "even",
        "towns",
        "show",
        "find",
        "best",
        "cheap",
        "affordable",
        "commute",
        "nearby",
        "suburbs",
        "options",
        "good",
        "bad",
        "safe",
        "unsafe",
        "price",
        "budget",
        "schools",
        "safety",
        "waterfront",
        "water-adjacent",
        "beachy",
        "farther",
        "weaker",
        "i",
        "you",
        "me",
        "my",
        "the",
        "a",
        "an",
    }
)

_FAKE_SIMILAR_TO = frozenset({"vibe", "feel", "similar", "cheaper", "expensive", "town"})


def normalize_rank_preferences(query: str, prefs: Preferences) -> Preferences:
    """
    Merge rule-parsed constraints and fix inverted-preference bugs from the planner.
    """
    parsed = parse_constraints(query)
    merged = parsed.model_copy(deep=True)

    text = query.lower()
    if re.search(
        r"\b(?:weaker schools? (?:are |is )?acceptable|schools? (?:are |is )?not a priority|"
        r"ignore school|don'?t care about schools?|weak schools? ok)\b",
        text,
    ):
        merged.deprioritize_schools = True
        merged.school_priority = "low"
        merged.prefer_low_school = merged.prefer_low_school or bool(
            re.search(r"\bweak schools?\b", text)
        )

    if re.search(r"\bdon'?t care about safety\b", text):
        merged.deprioritize_safety = True
        merged.safety_priority = "low"

    if is_inverted_crime_affordability_query(query) or re.search(
        r"\b(?:crime (?:can be|is) high|safety can be poor|high[- ]crime|accept (?:bad|weak|worse) safety|"
        r"poor safety ok|worse safety ok|safety can be mediocre|tolerate worse safety|"
        r"higher crime|care more about cheap|prioritize affordability)\b",
        text,
    ):
        merged.allow_low_safety = True
        merged.prefer_high_crime = True
        merged.deprioritize_safety = True
        merged.safety_priority = "low"
        merged.affordability_priority = merged.affordability_priority or "high"

    if merged.allow_low_safety:
        merged.prefer_high_crime = True

    if merged.deprioritize_schools:
        merged.school_priority = merged.school_priority or "low"

    return merged


def clean_rank_preferences(prefs: Preferences, *, known_towns: list[str]) -> Preferences:
    """Remove junk unknown_towns and non-town similar_to tokens from rank prefs."""
    known_keys = {normalize_key(t) for t in known_towns}
    updates: dict[str, Any] = {}

    if prefs.unknown_towns:
        cleaned: list[str] = []
        for token in prefs.unknown_towns:
            t = (token or "").strip()
            if not t or len(t) < 3:
                continue
            low = t.lower()
            if low in JUNK_UNKNOWN_TOWNS:
                continue
            if re.search(r"[-_]like$", low) or low.endswith("-like"):
                continue
            if normalize_key(t) in known_keys:
                continue
            cleaned.append(t)
        updates["unknown_towns"] = cleaned or None

    if prefs.similar_to_town:
        st = prefs.similar_to_town.strip()
        if st.lower() in _FAKE_SIMILAR_TO or len(st) < 3:
            updates["similar_to_town"] = None
        elif normalize_key(st) not in known_keys and not resolve_town_in_dataset(st, known_towns):
            if st.lower() in JUNK_UNKNOWN_TOWNS or re.search(r"[-_]like", st, re.I):
                updates["similar_to_town"] = None

    if prefs.named_towns:
        named = [
            canonical_town_name(resolve_town_in_dataset(n, known_towns) or n)
            for n in prefs.named_towns
            if n and n.strip().lower() not in JUNK_UNKNOWN_TOWNS
        ]
        updates["named_towns"] = named or None

    if updates:
        return prefs.model_copy(update=updates)
    return prefs


def _known_towns() -> list[str]:
    return [s["name"] for s in load_suburbs()]


_LOOKUP_PROTECTED_FIELDS = frozenset(
    {
        LookupFieldKind.COMMUTE.value,
        LookupFieldKind.PRICE.value,
        LookupFieldKind.SCHOOL.value,
        LookupFieldKind.SAFETY.value,
        LookupFieldKind.COASTAL.value,
        LookupFieldKind.REGION.value,
        LookupFieldKind.MISSING.value,
    }
)


def _is_protected_field_lookup(plan: QueryPlan) -> bool:
    """Do not rewrite factual field lookups to membership."""
    if len(plan.ops) != 1 or not isinstance(plan.ops[0], LookupOp):
        return False
    return any(item.field in _LOOKUP_PROTECTED_FIELDS for item in plan.ops[0].items)


def _resolve_membership_town(query: str, plan: QueryPlan) -> str | None:
    known = _known_towns()
    if is_pull_up_town_lookup(query):
        pulled = extract_pull_up_town_name(query, known)
        if pulled:
            return pulled
    entities = extract_entities(query)
    if entities.valid_towns:
        return canonical_town_name(entities.valid_towns[0])
    if entities.unknown_town_candidates:
        resolved = resolve_town_in_dataset(entities.unknown_town_candidates[0], known)
        if resolved:
            return resolved
        return entities.unknown_town_candidates[0].strip()
    for op in plan.ops:
        if isinstance(op, LookupOp) and op.items:
            return assert_valid_plan_town_name(op.items[0].town)
        if isinstance(op, MembershipOp):
            return assert_valid_plan_town_name(op.town)
        if isinstance(op, CompareOp) and op.towns:
            return assert_valid_plan_town_name(op.towns[0])
    pt = primary_town(entities)
    return pt


def _rewrite_membership(query: str, plan: QueryPlan) -> QueryPlan | None:
    if not is_dataset_membership_query(query):
        return None
    town = _resolve_membership_town(query, plan)
    if not town:
        return None
    return validate_plan({"ops": [{"op": "membership", "town": town}]})


def _rewrite_hard_unsupported(query: str, plan: QueryPlan) -> QueryPlan | None:
    """Neighborhood / live-market asks → unsupported before pull-up or membership rewrites."""
    from app.lookup_schema import extract_unsupported_attribute

    if is_neighborhood_level_query(query):
        return validate_plan(
            {
                "ops": [
                    {
                        "op": "unsupported",
                        "category": "neighborhood",
                        "reason": "neighborhood-level detail",
                    }
                ]
            }
        )

    match = extract_unsupported_attribute(query)
    if match and match.category in (
        "live_market",
        "neighborhood",
        "transit",
        "demographics",
    ):
        return validate_plan(
            {
                "ops": [
                    {
                        "op": "unsupported",
                        "category": match.category,
                        "reason": match.label,
                    }
                ]
            }
        )
    return None


def _rewrite_membership_strip_extras(query: str, plan: QueryPlan) -> QueryPlan | None:
    """Membership scope questions must not keep compare/lookup sidecars."""
    if not is_dataset_membership_query(query):
        return None
    if len(plan.ops) == 1 and isinstance(plan.ops[0], MembershipOp):
        town = assert_valid_plan_town_name(plan.ops[0].town)
        known = _known_towns()
        resolved = resolve_town_in_dataset(town, known) or town
        return validate_plan(
            {"ops": [{"op": "membership", "town": canonical_town_name(resolved)}]}
        )
    # Multi-op membership phrasing → membership only
    membership = _rewrite_membership(query, plan)
    if membership is not None:
        return membership
    return None


def _rewrite_factual_field_lookup(query: str, plan: QueryPlan) -> QueryPlan | None:
    """Commute/price/school/safety questions → lookup, not membership."""
    if is_dataset_membership_query(query) or is_pull_up_town_lookup(query):
        return None
    lower = query.lower()
    field: str | None = None
    if re.search(r"\b(?:what is|how long|how much).*\bcommute\b", lower) or re.search(
        r"\bcommute from\b", lower
    ):
        field = LookupFieldKind.COMMUTE.value
    elif re.search(
        r"\b(?:median|latest|home |housing )?price\b|\bhow much\b.*\b(?:cost|price)\b",
        lower,
    ):
        field = LookupFieldKind.PRICE.value
    elif re.search(r"\bschool score\b|\bschool rating\b", lower):
        field = LookupFieldKind.SCHOOL.value
    elif re.search(r"\bsafety score\b|\bcrime rate\b", lower):
        field = LookupFieldKind.SAFETY.value
    else:
        return None

    if _is_protected_field_lookup(plan):
        return None

    town = _resolve_membership_town(query, plan)
    if not town:
        return None

    known = _known_towns()
    resolved = canonical_town_name(resolve_town_in_dataset(town, known) or town)
    return validate_plan(
        {
            "ops": [
                {
                    "op": "lookup",
                    "items": [{"town": resolved, "field": field}],
                }
            ]
        }
    )


def _rewrite_pull_up_lookup(query: str, plan: QueryPlan) -> QueryPlan | None:
    if not is_pull_up_town_lookup(query):
        return None
    town = _resolve_membership_town(query, plan)
    if not town:
        return None
    known = _known_towns()
    resolved = resolve_town_in_dataset(town, known) or town
    town = canonical_town_name(resolved)
    return validate_plan(
        {
            "ops": [
                {
                    "op": "lookup",
                    "items": [
                        {"town": town, "field": "summary"},
                        {"town": town, "field": "commute"},
                        {"town": town, "field": "price"},
                    ],
                }
            ]
        }
    )


def _rewrite_inverted_crime_affordability(query: str, plan: QueryPlan) -> QueryPlan | None:
    if not is_inverted_crime_affordability_query(query):
        return None
    limit = 10
    for op in plan.ops:
        if isinstance(op, RankOp):
            limit = op.limit
            break
    prefs = clean_rank_preferences(
        normalize_rank_preferences(query, parse_constraints(query)),
        known_towns=_known_towns(),
    )
    return validate_plan(
        {
            "ops": [
                {
                    "op": "rank",
                    "preferences": prefs.model_dump(exclude_none=True),
                    "limit": limit,
                }
            ]
        }
    )


def _rewrite_coastal_rank(query: str, plan: QueryPlan) -> QueryPlan | None:
    if not is_coastal_rank_query(query):
        return None
    prefs = normalize_rank_preferences(query, parse_constraints(query))
    prefs = clean_rank_preferences(prefs, known_towns=_known_towns())
    limit = 10
    for op in plan.ops:
        if isinstance(op, RankOp):
            limit = op.limit
            break
    return validate_plan(
        {
            "ops": [
                {
                    "op": "rank",
                    "preferences": prefs.model_dump(exclude_none=True),
                    "limit": limit,
                }
            ]
        }
    )


def _rewrite_lookup_to_membership(query: str, plan: QueryPlan) -> QueryPlan | None:
    if not is_dataset_membership_query(query):
        return None
    if _is_protected_field_lookup(plan):
        return None
    if len(plan.ops) != 1:
        return None
    op = plan.ops[0]
    if not isinstance(op, LookupOp) or len(op.items) != 1:
        return None
    item = op.items[0]
    if item.field not in (LookupFieldKind.SUMMARY.value, LookupFieldKind.TIER.value):
        return None
    return _rewrite_membership(query, plan)


def _rewrite_semantic_vibe(query: str, plan: QueryPlan) -> QueryPlan | None:
    """Inject semantic_search when planner returned rank-only for a vibe query."""
    if not is_semantic_vibe_query(query):
        return None
    if any(isinstance(o, SemanticSearchOp) for o in plan.ops):
        return None
    rank_ops = [o for o in plan.ops if isinstance(o, RankOp)]
    if not rank_ops:
        return None
    rank = rank_ops[0]
    prefs = clean_rank_preferences(
        normalize_rank_preferences(query, rank.preferences),
        known_towns=_known_towns(),
    )
    return validate_plan(
        {
            "ops": [
                {
                    "op": "semantic_search",
                    "query_text": query.strip()[:240],
                    "top_k": 10,
                },
                {
                    "op": "rank",
                    "preferences": prefs.model_dump(exclude_none=True),
                    "limit": rank.limit,
                    "use_semantic_candidates": True,
                },
            ]
        }
    )


def _apply_semantic_rank_invariant(query: str, ops: list[Any]) -> list[Any]:
    """Force semantic_search → rank chain to use semantic candidates only."""
    known = _known_towns()
    out: list[Any] = []
    i = 0
    while i < len(ops):
        op = ops[i]
        if isinstance(op, SemanticSearchOp):
            out.append(op)
            if i + 1 < len(ops) and isinstance(ops[i + 1], RankOp):
                rank = ops[i + 1]
                prefs = clean_rank_preferences(
                    normalize_rank_preferences(query, rank.preferences),
                    known_towns=known,
                )
                out.append(
                    RankOp(
                        preferences=prefs,
                        limit=rank.limit,
                        use_semantic_candidates=True,
                    )
                )
                i += 2
                continue
            i += 1
            continue
        if isinstance(op, RankOp):
            prefs = clean_rank_preferences(
                normalize_rank_preferences(query, op.preferences),
                known_towns=known,
            )
            use_sem = op.use_semantic_candidates
            if i > 0 and isinstance(out[-1], SemanticSearchOp):
                use_sem = True
            out.append(
                RankOp(
                    preferences=prefs,
                    limit=op.limit,
                    use_semantic_candidates=use_sem,
                )
            )
            i += 1
            continue
        out.append(op)
        i += 1
    return out


def normalize_planned_query(query: str, plan: QueryPlan) -> QueryPlan:
    """
    Apply deterministic repairs after LLM planning, before trust gates / execution.
    """
    text = query.strip()
    if not text:
        return plan

    for rewriter in (
        _rewrite_hard_unsupported,
        _rewrite_pull_up_lookup,
        _rewrite_factual_field_lookup,
        _rewrite_inverted_crime_affordability,
        _rewrite_membership_strip_extras,
        _rewrite_membership,
        _rewrite_lookup_to_membership,
        _rewrite_coastal_rank,
        _rewrite_semantic_vibe,
    ):
        rewritten = rewriter(text, plan)
        if rewritten is not None:
            plan = rewritten
            break

    if len(plan.ops) == 1 and isinstance(plan.ops[0], UnsupportedOp):
        inverted = _rewrite_inverted_crime_affordability(text, plan)
        if inverted is not None:
            plan = inverted
        elif is_dataset_membership_query(text):
            membership = _rewrite_membership(text, plan)
            if membership is not None:
                plan = membership

    new_ops = _apply_semantic_rank_invariant(text, list(plan.ops))

    final_ops: list[Any] = []
    known = _known_towns()
    for op in new_ops:
        if isinstance(op, RankOp):
            prefs = clean_rank_preferences(
                normalize_rank_preferences(text, op.preferences),
                known_towns=known,
            )
            final_ops.append(
                RankOp(
                    preferences=prefs,
                    limit=op.limit,
                    use_semantic_candidates=op.use_semantic_candidates,
                )
            )
        elif isinstance(op, LookupOp):
            items = []
            for item in op.items:
                town = assert_valid_plan_town_name(item.town)
                resolved = resolve_town_in_dataset(town, known) or town
                items.append(
                    item.model_copy(update={"town": canonical_town_name(resolved)})
                )
            final_ops.append(LookupOp(items=items))
        elif isinstance(op, CompareOp):
            towns = []
            for t in op.towns:
                town = assert_valid_plan_town_name(t)
                resolved = resolve_town_in_dataset(town, known) or town
                towns.append(canonical_town_name(resolved))
            final_ops.append(CompareOp(towns=towns, columns=op.columns))
        elif isinstance(op, MembershipOp):
            town = assert_valid_plan_town_name(op.town)
            resolved = resolve_town_in_dataset(town, known) or town
            final_ops.append(MembershipOp(town=canonical_town_name(resolved)))
        else:
            final_ops.append(op)

    return validate_plan(QueryPlan(ops=final_ops))
