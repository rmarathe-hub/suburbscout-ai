"""Score LLM QueryPlans against structured expectations (planner-only eval)."""

from __future__ import annotations

from typing import Any

from app.query_plan import (
    CompareOp,
    LookupOp,
    MembershipOp,
    QueryPlan,
    RankOp,
    SemanticSearchOp,
    UnsupportedOp,
    normalize_lookup_field,
    validate_plan,
)
from app.town_normalizer import canonical_town_name, normalize_key


def plan_from_dict(data: dict[str, Any]) -> QueryPlan:
    return validate_plan(data)


def extract_plan_features(plan: QueryPlan) -> dict[str, Any]:
    """Flatten a plan into comparable features for scoring."""
    ops: list[str] = []
    lookup_items: list[tuple[str, str]] = []
    compare_towns: list[str] = []
    compare_columns: list[str] = []
    rank_prefs: dict[str, Any] = {}
    semantic_queries: list[str] = []
    unsupported_categories: list[str] = []
    membership_towns: list[str] = []
    use_semantic_candidates = False

    for op in plan.ops:
        if isinstance(op, LookupOp):
            ops.append("lookup")
            for item in op.items:
                town = canonical_town_name(item.town)
                field = normalize_lookup_field(item.field)
                lookup_items.append((town, field))
        elif isinstance(op, CompareOp):
            ops.append("compare")
            compare_towns.extend(canonical_town_name(t) for t in op.towns)
            if op.columns:
                compare_columns.extend(op.columns)
        elif isinstance(op, RankOp):
            ops.append("rank")
            rank_prefs = op.preferences.model_dump(exclude_none=True)
            use_semantic_candidates = bool(op.use_semantic_candidates)
        elif isinstance(op, SemanticSearchOp):
            ops.append("semantic_search")
            semantic_queries.append(op.query_text.strip())
        elif isinstance(op, MembershipOp):
            ops.append("membership")
            membership_towns.append(canonical_town_name(op.town))
        elif isinstance(op, UnsupportedOp):
            ops.append("unsupported")
            unsupported_categories.append(op.category.value)

    return {
        "ops": ops,
        "lookup_items": lookup_items,
        "membership_towns": membership_towns,
        "compare_towns": compare_towns,
        "compare_columns": compare_columns,
        "rank_prefs": rank_prefs,
        "semantic_queries": semantic_queries,
        "unsupported_categories": unsupported_categories,
        "use_semantic_candidates": use_semantic_candidates,
    }


def _town_match(expected: str, actual: str) -> bool:
    return normalize_key(canonical_town_name(expected)) == normalize_key(
        canonical_town_name(actual)
    )


def score_plan_against_expect(
    plan: QueryPlan,
    expect: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare actual plan to case ``expect`` block.

    Returns dict with op_accuracy, town_accuracy, field_accuracy (0–1),
    passed (bool), and failure_reasons.
    """
    actual = extract_plan_features(plan)
    failures: list[str] = []

    expected_ops = expect.get("ops")
    if expected_ops is not None:
        strict_order = expect.get("ops_strict_order", True)
        if strict_order:
            op_ok = actual["ops"] == expected_ops
        else:
            op_ok = set(actual["ops"]) == set(expected_ops) and len(actual["ops"]) == len(
                expected_ops
            )
        if not op_ok:
            failures.append(
                f"ops: expected {expected_ops}, got {actual['ops']}"
            )

    primary_op = expect.get("primary_op")
    if primary_op and actual["ops"]:
        if actual["ops"][0] != primary_op and primary_op not in actual["ops"]:
            failures.append(
                f"primary_op: expected {primary_op!r}, got {actual['ops']}"
            )

    expected_lookup = expect.get("lookup_items") or []
    if expected_lookup:
        matched = 0
        for exp in expected_lookup:
            exp_town = canonical_town_name(exp["town"])
            exp_field = normalize_lookup_field(exp["field"])
            found = any(
                _town_match(exp_town, t) and f == exp_field
                for t, f in actual["lookup_items"]
            )
            if found:
                matched += 1
            else:
                failures.append(
                    f"lookup missing {exp_town}/{exp_field}; have {actual['lookup_items']}"
                )
        town_acc = matched / len(expected_lookup) if expected_lookup else 1.0
    else:
        town_acc = 1.0 if not actual["lookup_items"] else 1.0

    expected_towns = expect.get("compare_towns") or []
    if expected_towns:
        matched_ct = 0
        for exp_t in expected_towns:
            if any(_town_match(exp_t, a) for a in actual["compare_towns"]):
                matched_ct += 1
            else:
                failures.append(
                    f"compare missing town {exp_t!r}; have {actual['compare_towns']}"
                )
        compare_town_acc = matched_ct / len(expected_towns)
    else:
        compare_town_acc = 1.0

    expected_columns = expect.get("compare_columns") or []
    if expected_columns:
        actual_cols = {c.lower() for c in actual["compare_columns"]}
        col_matched = sum(
            1 for c in expected_columns if c.lower() in actual_cols
        )
        if col_matched < len(expected_columns):
            failures.append(
                f"compare columns: expected {expected_columns}, got {actual['compare_columns']}"
            )

    rank_expect = expect.get("rank_preferences") or {}
    field_hits = 0
    field_total = len(rank_expect)
    for key, val in rank_expect.items():
        actual_val = actual["rank_prefs"].get(key)
        if key == "exclude_towns" and isinstance(val, list):
            exp_set = {normalize_key(canonical_town_name(t)) for t in val}
            act_set = {
                normalize_key(canonical_town_name(t))
                for t in (actual_val or [])
            }
            if exp_set <= act_set:
                field_hits += 1
            else:
                failures.append(
                    f"rank exclude_towns: expected {exp_set}, got {act_set}"
                )
        elif actual_val == val:
            field_hits += 1
        else:
            failures.append(
                f"rank pref {key}: expected {val!r}, got {actual_val!r}"
            )

    if expect.get("use_semantic_candidates") is True:
        if not actual["use_semantic_candidates"]:
            failures.append("expected use_semantic_candidates=true on rank op")

    unsup_cat = expect.get("unsupported_category")
    if unsup_cat:
        if unsup_cat not in actual["unsupported_categories"]:
            failures.append(
                f"unsupported category: expected {unsup_cat}, got {actual['unsupported_categories']}"
            )

    semantic_min = expect.get("semantic_query_min_length")
    if semantic_min and actual["semantic_queries"]:
        if len(actual["semantic_queries"][0]) < semantic_min:
            failures.append("semantic query_text too short")

    plan_towns: list[str] = []
    for town, _field in actual["lookup_items"]:
        plan_towns.append(town)
    plan_towns.extend(actual["compare_towns"])
    plan_towns.extend(actual["membership_towns"])

    expected_town = expect.get("expected_town")
    if expected_town:
        if not any(_town_match(expected_town, t) for t in plan_towns):
            failures.append(
                f"expected town {expected_town!r} in plan, towns present: {plan_towns}"
            )

    for forbidden in expect.get("forbidden_towns") or []:
        if any(_town_match(forbidden, t) for t in plan_towns):
            failures.append(f"forbidden town {forbidden!r} appeared in plan: {plan_towns}")

    # Aggregate accuracies
    op_accuracy = 1.0 if not expected_ops or actual["ops"] == expected_ops else (
        1.0 if not failures or not any("ops:" in f for f in failures) else 0.0
    )
    if expected_ops and op_accuracy == 0.0:
        # partial credit: primary op match
        if primary_op and primary_op in actual["ops"]:
            op_accuracy = 0.5

    lookup_total = len(expected_lookup) if expected_lookup else 0
    if lookup_total:
        lookup_matched = lookup_total - sum(
            1 for f in failures if f.startswith("lookup missing")
        )
        town_accuracy = max(0.0, lookup_matched / lookup_total)
    elif expected_towns:
        town_accuracy = compare_town_acc
    else:
        town_accuracy = 1.0

    if field_total:
        field_accuracy = field_hits / field_total
    elif expected_columns:
        field_accuracy = 1.0 if not any("compare columns" in f for f in failures) else 0.0
    elif unsup_cat:
        field_accuracy = 1.0 if not any("unsupported category" in f for f in failures) else 0.0
    else:
        field_accuracy = 1.0

    passed = len(failures) == 0
    return {
        "passed": passed,
        "op_accuracy": op_accuracy,
        "town_accuracy": town_accuracy,
        "field_accuracy": field_accuracy,
        "failure_reasons": failures,
        "actual_ops": actual["ops"],
    }
