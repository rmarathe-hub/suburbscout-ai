"""Post-process LLM QueryPlans — Phase 9 plan-JSON structural normalization only."""

from __future__ import annotations

import re
from typing import Any

from app.commute_intent import CommuteContext, CommuteIntent
from app.plan_preferences import merge_rank_preferences
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
from app.town_normalizer import (
    canonical_town_name,
    normalize_key,
    resolve_town_for_plan,
    resolve_town_in_dataset,
)

# Tokens the planner often mis-extracts as town names from rank prefs.
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


def normalize_rank_preferences(
    query: str,
    prefs: Preferences,
    *,
    commute_intent: Any | None = None,
    regex_fallback: bool = False,
) -> Preferences:
    """LLM planner prefs first; Python validation only (no regex fill on live path)."""
    from app.commute_intent import CommuteIntent

    intent = commute_intent if isinstance(commute_intent, CommuteIntent) else None
    return merge_rank_preferences(
        query, prefs, commute_intent=intent, regex_fallback=regex_fallback
    )


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


def _canonicalize_plan_town(town: str, known: list[str]) -> str:
    """Canonicalize when confident; keep queried spelling when ambiguous."""
    resolution = resolve_town_for_plan(town, known)
    if resolution.resolved and not resolution.ambiguous:
        return canonical_town_name(resolution.resolved)
    return town.strip()


def _lookup_field_to_compare_column(field: str) -> str | None:
    """Map lookup field tokens to compare column keys (plan JSON only)."""
    key = (field or "").strip().lower()
    mapping = {
        LookupFieldKind.PRICE.value: "price",
        "latest_home_price": "price",
        "home_price": "price",
        LookupFieldKind.SCHOOL.value: "school_score",
        "schools": "school_score",
        LookupFieldKind.SAFETY.value: "safety_score",
        LookupFieldKind.COMMUTE.value: "drive_minutes_to_boston",
        LookupFieldKind.COASTAL.value: "is_coastal",
        LookupFieldKind.SUMMARY.value: "latest_home_price",
    }
    return mapping.get(key)


def _rewrite_lookup_to_compare_from_intent(plan: QueryPlan) -> QueryPlan | None:
    """
    Planner emitted lookup when compare was intended — fix from plan JSON only.
    """
    if any(isinstance(o, CompareOp) for o in plan.ops):
        return None

    lookup_ops = [o for o in plan.ops if isinstance(o, LookupOp)]
    if not lookup_ops:
        return None

    intent = plan.commute_intent
    towns: list[str] = []
    if intent and len(intent.compare_towns) >= 2:
        towns = list(intent.compare_towns[:2])
    else:
        seen: list[str] = []
        for op in lookup_ops:
            for item in op.items:
                t = item.town.strip()
                if t and t not in seen:
                    seen.append(t)
        if len(seen) >= 2:
            towns = seen[:2]

    if len(towns) < 2:
        return None

    columns: list[str] = []
    for op in lookup_ops:
        for item in op.items:
            col = _lookup_field_to_compare_column(item.field)
            if col and col not in columns:
                columns.append(col)

    if not columns:
        from app.query_plan import DEFAULT_COMPARE_COLUMNS

        columns = list(DEFAULT_COMPARE_COLUMNS)

    fixed_intent = intent or CommuteIntent()
    raw_dest = (fixed_intent.commute_destination_town or "").strip().lower()
    if fixed_intent.commute_context == CommuteContext.UNSUPPORTED and raw_dest in {
        "unsupported",
        "",
    }:
        fixed_intent = CommuteIntent(
            commute_context=CommuteContext.DEFAULT_BOSTON,
            compare_towns=towns,
            commute_destination_town=None,
            max_commute_minutes=fixed_intent.max_commute_minutes,
        )
    elif not fixed_intent.compare_towns:
        fixed_intent = fixed_intent.model_copy(update={"compare_towns": towns})

    return validate_plan(
        QueryPlan(
            ops=[CompareOp(towns=towns, columns=columns)],
            commute_intent=fixed_intent,
            user_intent_summary=plan.user_intent_summary,
        )
    )


def _apply_semantic_rank_invariant(
    query: str,
    ops: list[Any],
    *,
    commute_intent: Any | None = None,
) -> list[Any]:
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
                    normalize_rank_preferences(
                        query,
                        rank.preferences,
                        commute_intent=commute_intent,
                        regex_fallback=False,
                    ),
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
                normalize_rank_preferences(
                    query,
                    op.preferences,
                    commute_intent=commute_intent,
                    regex_fallback=False,
                ),
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
    Apply deterministic structural repairs after LLM planning.

    Phase 9: plan JSON only — no query-text intent rewrites.
    """
    text = query.strip()
    if not text:
        return plan

    original_commute_intent = plan.commute_intent

    rewritten = _rewrite_lookup_to_compare_from_intent(plan)
    if rewritten is not None:
        plan = rewritten
        if original_commute_intent and not plan.commute_intent:
            plan = plan.model_copy(update={"commute_intent": original_commute_intent})

    new_ops = _apply_semantic_rank_invariant(
        text,
        list(plan.ops),
        commute_intent=plan.commute_intent or original_commute_intent,
    )

    final_ops: list[Any] = []
    known = _known_towns()
    active_commute_intent = plan.commute_intent or original_commute_intent
    for op in new_ops:
        if isinstance(op, RankOp):
            prefs = clean_rank_preferences(
                normalize_rank_preferences(
                    text,
                    op.preferences,
                    commute_intent=active_commute_intent,
                    regex_fallback=False,
                ),
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
                items.append(
                    item.model_copy(update={"town": _canonicalize_plan_town(town, known)})
                )
            final_ops.append(LookupOp(items=items))
        elif isinstance(op, CompareOp):
            towns = []
            for t in op.towns:
                town = assert_valid_plan_town_name(t)
                towns.append(_canonicalize_plan_town(town, known))
            final_ops.append(
                CompareOp(
                    towns=towns,
                    columns=op.columns,
                    commute_destination_town=op.commute_destination_town,
                )
            )
        elif isinstance(op, MembershipOp):
            town = assert_valid_plan_town_name(op.town)
            final_ops.append(MembershipOp(town=_canonicalize_plan_town(town, known)))
        else:
            final_ops.append(op)

    plan = validate_plan(
        QueryPlan(
            ops=final_ops,
            commute_intent=plan.commute_intent or original_commute_intent,
            user_intent_summary=plan.user_intent_summary,
        )
    )
    from app.commute_intent import apply_commute_intent_to_plan

    return apply_commute_intent_to_plan(text, plan)
