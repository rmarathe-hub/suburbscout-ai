"""Phase 9 — plan-JSON trust gates (no query-text veto on live path)."""

from __future__ import annotations

from app.commute_destination import build_commute_destination_limitation
from app.commute_intent import CommuteContext, resolve_commute_intent
from app.entity_extractor import ExtractedEntities, extract_entities
from app.query_patterns import MAX_MULTI_COMPARE_TOWNS, MAX_MULTI_LOOKUP_SPECS
from app.query_patterns import build_too_many_compare_message, build_too_many_lookup_message
from app.query_plan import (
    CompareOp,
    LookupOp,
    MembershipOp,
    PlanValidationError,
    QueryPlan,
    RankOp,
    SemanticSearchOp,
    UnsupportedOp,
    assert_valid_plan_town_name,
    normalize_compare_column,
)
from app.query_route_types import QueryRoute
from app.trust_gates import (
    TrustGateResult,
    build_unsupported_compare_message,
    build_unsupported_rank_message,
)

__all__ = [
    "evaluate_plan_trust_gate",
    "plan_to_query_route",
]


def _lookup_item_count(plan: QueryPlan) -> int:
    total = 0
    for op in plan.ops:
        if isinstance(op, LookupOp):
            total += len(op.items)
    return total


def _compare_town_count(plan: QueryPlan) -> int:
    towns: set[str] = set()
    for op in plan.ops:
        if isinstance(op, CompareOp):
            for name in op.towns:
                towns.add(name.lower())
    return len(towns)


def plan_to_query_route(query: str, plan: QueryPlan) -> QueryRoute:
    """Synthesize a QueryRoute from a QueryPlan (debug/tests only)."""
    entities = extract_entities(query)
    known = list(entities.valid_towns)
    unknown = list(entities.unknown_town_candidates)

    unsupported_ops = [o for o in plan.ops if isinstance(o, UnsupportedOp)]
    if unsupported_ops and len(plan.ops) == len(unsupported_ops):
        reason = unsupported_ops[0].reason
        return QueryRoute(
            intent="unsupported",
            confidence=0.95,
            query=query,
            named_towns=known,
            unknown_towns=unknown,
            message=reason,
            pipeline=[],
            classification_source="llm",
        )

    compare_ops = [o for o in plan.ops if isinstance(o, CompareOp)]
    if compare_ops:
        all_towns: list[str] = []
        columns: list[str] = []
        for cop in compare_ops:
            all_towns.extend(cop.towns)
            if cop.columns:
                columns = list(cop.columns)
        unique = []
        seen: set[str] = set()
        for town in all_towns:
            key = town.lower()
            if key not in seen:
                seen.add(key)
                unique.append(town)
        if len(unique) >= 3:
            return QueryRoute(
                intent="compare_multi_town",
                confidence=0.9,
                query=query,
                named_towns=known,
                unknown_towns=unknown,
                compare_towns=unique,
                compare_columns=columns,
                pipeline=[],
                classification_source="llm",
            )
        if len(unique) == 2:
            return QueryRoute(
                intent="compare_towns",
                confidence=0.9,
                query=query,
                named_towns=known,
                unknown_towns=unknown,
                compare_town_a=unique[0],
                compare_town_b=unique[1],
                compare_columns=columns,
                pipeline=[],
                classification_source="llm",
            )

    membership_ops = [o for o in plan.ops if isinstance(o, MembershipOp)]
    if membership_ops:
        return QueryRoute(
            intent="dataset_membership",
            confidence=0.95,
            query=query,
            named_towns=known,
            unknown_towns=unknown,
            lookup_town=membership_ops[0].town,
            pipeline=[],
            classification_source="llm",
        )

    lookup_ops = [o for o in plan.ops if isinstance(o, LookupOp)]
    if lookup_ops:
        specs: list[dict[str, str]] = []
        for lop in lookup_ops:
            for item in lop.items:
                specs.append({"town": item.town, "field": item.field})
        town_keys = {s["town"].lower() for s in specs}
        if len(specs) >= 2 and len(town_keys) >= 2:
            return QueryRoute(
                intent="lookup_multi_town",
                confidence=0.9,
                query=query,
                named_towns=known,
                unknown_towns=unknown,
                lookup_specs=specs,
                pipeline=[],
                classification_source="llm",
            )
        if specs:
            return QueryRoute(
                intent="lookup_single_town",
                confidence=0.9,
                query=query,
                named_towns=known,
                unknown_towns=unknown,
                lookup_town=specs[0]["town"],
                pipeline=[],
                classification_source="llm",
            )

    rank_ops = [o for o in plan.ops if isinstance(o, RankOp)]
    has_semantic = any(isinstance(o, SemanticSearchOp) for o in plan.ops)
    if rank_ops or has_semantic:
        intent = "recommend_semantic" if has_semantic else "recommend_structured"
        return QueryRoute(
            intent=intent,
            confidence=0.9,
            query=query,
            named_towns=known,
            unknown_towns=unknown,
            use_semantic=has_semantic,
            pipeline=[],
            classification_source="llm",
        )

    return QueryRoute(
        intent="unsupported",
        confidence=0.5,
        query=query,
        named_towns=known,
        unknown_towns=unknown,
        pipeline=[],
        classification_source="llm",
    )


def _unsupported_compare_column_gate(op: CompareOp) -> TrustGateResult | None:
    if not op.columns:
        return None
    for raw_col in op.columns:
        try:
            normalize_compare_column(raw_col)
        except PlanValidationError:
            town_a = op.towns[0] if op.towns else "Town A"
            town_b = op.towns[1] if len(op.towns) > 1 else "Town B"
            return TrustGateResult(
                gate_type="unsupported_compare",
                message=build_unsupported_compare_message(
                    town_a,
                    town_b,
                    raw_col,
                    category="lifestyle",
                ),
                blocks_pipeline=True,
            )
    return None


def _evaluate_semantic_plan_gates(plan: QueryPlan) -> TrustGateResult | None:
    """Plan-native semantic safety."""
    has_semantic = any(isinstance(o, SemanticSearchOp) for o in plan.ops)
    rank_ops = [o for o in plan.ops if isinstance(o, RankOp)]

    if has_semantic and rank_ops:
        if not rank_ops[0].use_semantic_candidates:
            return TrustGateResult(
                gate_type="semantic_rank_limit",
                message=(
                    "Ranking after semantic search must use semantic candidates only "
                    "(use_semantic_candidates=true)."
                ),
                blocks_pipeline=True,
            )
    return None


def _evaluate_compare_commute_gates(
    plan: QueryPlan,
    resolved,
) -> TrustGateResult | None:
    compare_ops = [o for o in plan.ops if isinstance(o, CompareOp)]
    if not compare_ops:
        return None

    if (
        resolved.commute_context == CommuteContext.UNSUPPORTED
        and resolved.has_non_default_destination()
    ):
        return TrustGateResult(
            gate_type="commute_destination_compare",
            message=build_commute_destination_limitation(
                resolved.to_destination_result(),
                context="lookup",
            ),
            blocks_pipeline=True,
        )

    for op in compare_ops:
        dest = op.commute_destination_town
        if dest and resolved.commute_context == CommuteContext.DESTINATION_TOWN:
            if not resolved.in_dataset or not resolved.data_available:
                return TrustGateResult(
                    gate_type="commute_destination_compare",
                    message=build_commute_destination_limitation(
                        resolved.to_destination_result(),
                        context="lookup",
                    ),
                    blocks_pipeline=True,
                )
        gate = _unsupported_compare_column_gate(op)
        if gate is not None:
            return gate
    return None


def _evaluate_rank_commute_gate(plan: QueryPlan, resolved) -> TrustGateResult | None:
    rank_ops = [o for o in plan.ops if isinstance(o, RankOp)]
    if not rank_ops:
        return None
    if resolved.commute_context != CommuteContext.UNSUPPORTED:
        return None
    if not resolved.has_non_default_destination():
        return None
    prefs = rank_ops[0].preferences
    if (
        prefs.max_commute_minutes is not None
        or prefs.commute_destination_town
        or (plan.commute_intent and plan.commute_intent.max_commute_minutes is not None)
    ):
        return TrustGateResult(
            gate_type="commute_destination_rank",
            message=build_commute_destination_limitation(
                resolved.to_destination_result(),
                context="recommend",
            ),
            blocks_pipeline=True,
        )
    return None


def _evaluate_lookup_commute_gate(plan: QueryPlan, resolved) -> TrustGateResult | None:
    lookup_ops = [o for o in plan.ops if isinstance(o, LookupOp)]
    if not lookup_ops:
        return None
    has_commute_lookup = any(
        item.field in ("commute", "drive_time", "drive_minutes")
        for op in lookup_ops
        for item in op.items
    )
    if not has_commute_lookup:
        return None
    if resolved.commute_context == CommuteContext.DESTINATION_TOWN:
        if resolved.in_dataset and resolved.data_available:
            return None
    if resolved.has_non_default_destination() and (
        not resolved.in_dataset or not resolved.data_available
    ):
        return TrustGateResult(
            gate_type="commute_destination_lookup",
            message=build_commute_destination_limitation(
                resolved.to_destination_result(),
                context="lookup",
            ),
            blocks_pipeline=True,
        )
    return None


def _evaluate_unsupported_op_gate(plan: QueryPlan) -> TrustGateResult | None:
    unsupported_ops = [o for o in plan.ops if isinstance(o, UnsupportedOp)]
    if not unsupported_ops:
        return None
    if len(plan.ops) != len(unsupported_ops):
        return None
    op = unsupported_ops[0]
    category = op.category.value if hasattr(op.category, "value") else str(op.category)
    if category == "neighborhood":
        from app.query_patterns import build_neighborhood_unsupported_message

        return TrustGateResult(
            gate_type="unsupported_neighborhood",
            message=build_neighborhood_unsupported_message(),
            blocks_pipeline=True,
        )
    if category in ("live_market", "transit", "demographics"):
        return TrustGateResult(
            gate_type=f"unsupported_{category}",
            message=op.reason or f"Request category '{category}' is out of scope.",
            blocks_pipeline=True,
        )
    return TrustGateResult(
        gate_type="unsupported",
        message=op.reason or "This request is outside dataset scope.",
        blocks_pipeline=True,
    )


def _evaluate_unsupported_rank_gate(plan: QueryPlan) -> TrustGateResult | None:
    """Block rank when planner left only unsupported lifestyle/demographic prefs and no supported filters."""
    rank_ops = [o for o in plan.ops if isinstance(o, RankOp)]
    if not rank_ops:
        return None
    prefs = rank_ops[0].preferences
    has_supported = any(
        (
            prefs.budget_max is not None,
            prefs.max_commute_minutes is not None,
            prefs.min_commute_minutes is not None,
            prefs.requires_coastal,
            prefs.region_preference,
            prefs.region_key,
            prefs.county_preference,
            prefs.safer_than_town,
            prefs.cheaper_than_town,
            prefs.quieter_than_town,
            prefs.similar_to_town,
            prefs.candidate_towns,
            prefs.school_priority,
            prefs.safety_priority,
            prefs.commute_priority,
            prefs.affordability_priority,
        )
    )
    if has_supported:
        return None
    unsupported_ops = [o for o in plan.ops if isinstance(o, UnsupportedOp)]
    if unsupported_ops:
        op = unsupported_ops[0]
        category = op.category.value if hasattr(op.category, "value") else "lifestyle"
        return TrustGateResult(
            gate_type="unsupported_rank",
            message=build_unsupported_rank_message(op.reason, category=category),
            blocks_pipeline=True,
        )
    return None


def evaluate_plan_trust_gate(
    query: str,
    plan: QueryPlan,
    *,
    entities: ExtractedEntities | None = None,
) -> TrustGateResult | None:
    """Trust checks from QueryPlan JSON before execution."""
    del entities  # plan JSON is authoritative on live path
    text = query.strip()
    resolved = resolve_commute_intent(text, plan.commute_intent, plan=plan)

    unsupported_gate = _evaluate_unsupported_op_gate(plan)
    if unsupported_gate is not None:
        return unsupported_gate

    semantic_gate = _evaluate_semantic_plan_gates(plan)
    if semantic_gate is not None:
        return semantic_gate

    for op in plan.ops:
        if isinstance(op, LookupOp):
            for item in op.items:
                try:
                    assert_valid_plan_town_name(item.town)
                except Exception as exc:
                    return TrustGateResult(
                        gate_type="invalid_plan_town",
                        message=str(exc),
                        blocks_pipeline=True,
                    )
        elif isinstance(op, CompareOp):
            for town in op.towns:
                try:
                    assert_valid_plan_town_name(town)
                except Exception as exc:
                    return TrustGateResult(
                        gate_type="invalid_plan_town",
                        message=str(exc),
                        blocks_pipeline=True,
                    )
        elif isinstance(op, MembershipOp):
            try:
                assert_valid_plan_town_name(op.town)
            except Exception as exc:
                return TrustGateResult(
                    gate_type="invalid_plan_town",
                    message=str(exc),
                    blocks_pipeline=True,
                )

    lookup_count = _lookup_item_count(plan)
    if lookup_count > MAX_MULTI_LOOKUP_SPECS:
        return TrustGateResult(
            gate_type="too_many_lookups",
            message=build_too_many_lookup_message(lookup_count),
            blocks_pipeline=True,
        )

    compare_count = _compare_town_count(plan)
    if compare_count > MAX_MULTI_COMPARE_TOWNS:
        return TrustGateResult(
            gate_type="too_many_compare",
            message=build_too_many_compare_message(compare_count),
            blocks_pipeline=True,
        )

    compare_gate = _evaluate_compare_commute_gates(plan, resolved)
    if compare_gate is not None:
        return compare_gate

    rank_gate = _evaluate_rank_commute_gate(plan, resolved)
    if rank_gate is not None:
        return rank_gate

    lookup_gate = _evaluate_lookup_commute_gate(plan, resolved)
    if lookup_gate is not None:
        return lookup_gate

    return _evaluate_unsupported_rank_gate(plan)
