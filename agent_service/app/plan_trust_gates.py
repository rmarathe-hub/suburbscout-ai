"""Phase 6 — trust gates for QueryPlan before execution (query agent path)."""

from __future__ import annotations

import re

from app.entity_extractor import ExtractedEntities, extract_entities
from app.query_patterns import MAX_MULTI_COMPARE_TOWNS, MAX_MULTI_LOOKUP_SPECS
from app.query_patterns import (
    build_neighborhood_unsupported_message,
    is_neighborhood_level_query,
    is_semantic_vibe_query,
    semantic_lifestyle_limitation_message,
)
from app.query_plan import (
    CompareOp,
    LookupOp,
    MembershipOp,
    QueryPlan,
    RankOp,
    SemanticSearchOp,
    UnsupportedOp,
    assert_valid_plan_town_name,
)
from app.query_router import QueryRoute
from app.trust_gates import TrustGateResult, evaluate_trust_gate

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
    """
    Synthesize a QueryRoute from a QueryPlan so legacy trust rules can apply.

    Used only for trust evaluation — not for tool routing.
    """
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


def evaluate_plan_trust_gate(
    query: str,
    plan: QueryPlan,
    *,
    entities: ExtractedEntities | None = None,
) -> TrustGateResult | None:
    """
    Trust checks for the query-agent path (plan → execute → answer).

    Runs plan-native limits first, then delegates to route-based gates via
    ``plan_to_query_route``.
    """
    from app.query_patterns import (
        build_too_many_compare_message,
        build_too_many_lookup_message,
    )

    entities = entities or extract_entities(query)
    text = query.strip()

    if is_neighborhood_level_query(text):
        return TrustGateResult(
            gate_type="unsupported_neighborhood",
            message=build_neighborhood_unsupported_message(),
            blocks_pipeline=True,
        )

    semantic_gate = _evaluate_semantic_plan_gates(text, plan)
    if semantic_gate is not None:
        return semantic_gate

    lifestyle_note = semantic_lifestyle_limitation_message(text)
    if lifestyle_note and any(isinstance(o, SemanticSearchOp) for o in plan.ops):
        return TrustGateResult(
            gate_type="semantic_lifestyle_note",
            message=lifestyle_note,
            blocks_pipeline=False,
        )

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

    # Planner emitted compare but user named 3+ towns without multi-table wording
    compare_ops = [o for o in plan.ops if isinstance(o, CompareOp)]
    if (
        compare_ops
        and len(entities.valid_towns) > 2
        and re.search(r"\b(?:compare|versus|vs\.?)\b", text.lower())
        and len(compare_ops) == 1
        and len(compare_ops[0].towns) < 3
        and len(entities.valid_towns) > len(compare_ops[0].towns)
    ):
        from app.trust_gates import build_multi_compare_message

        return TrustGateResult(
            gate_type="multi_compare",
            message=build_multi_compare_message(entities.valid_towns),
            blocks_pipeline=True,
        )

    route = plan_to_query_route(text, plan)
    return evaluate_trust_gate(text, route, entities=entities)


def _evaluate_semantic_plan_gates(query: str, plan: QueryPlan) -> TrustGateResult | None:
    """Plan-native semantic safety before route-based gates."""
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

    if is_semantic_vibe_query(query) and rank_ops and not has_semantic:
        return TrustGateResult(
            gate_type="semantic_required",
            message=(
                "This question asks for vibe or similarity matching; use semantic_search "
                "before rank, not rank over the full dataset."
            ),
            blocks_pipeline=True,
        )

    return None
