"""Phase 2 — execute validated QueryPlans against suburbs.json and the vector index."""

from __future__ import annotations

import asyncio
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.query_plan import (
    CompareOp,
    CommutePairOp,
    DEFAULT_COMPARE_COLUMNS,
    LookupFieldKind,
    LookupOp,
    MembershipOp,
    PlanValidationError,
    QueryPlan,
    RankOp,
    SemanticSearchOp,
    UnsupportedOp,
    lookup_field_dataset_keys,
    validate_plan,
)
from app.commute_service import commute_destination_label, get_commute_minutes
from app.ranking import describe_active_filters, rank_suburbs
from app.schemas import Preferences
from app.tools import (
    SCORE_DISCLAIMER,
    compare_suburbs_multi_tool,
    get_town_facts,
    run_semantic_town_search,
)


class ExecutionStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    NOT_FOUND = "not_found"
    NO_ROWS = "no_rows"
    OUT_OF_SCOPE = "out_of_scope"
    INVALID_PLAN = "invalid_plan"


# Weakest → strongest for merging op-level statuses into plan-level
_STATUS_RANK: dict[ExecutionStatus, int] = {
    ExecutionStatus.OK: 0,
    ExecutionStatus.NO_ROWS: 1,
    ExecutionStatus.PARTIAL: 2,
    ExecutionStatus.NOT_FOUND: 3,
    ExecutionStatus.OUT_OF_SCOPE: 4,
    ExecutionStatus.INVALID_PLAN: 5,
}


class OpExecutionResult(BaseModel):
    op: str
    status: ExecutionStatus
    data: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    """Aggregate outcome of running all ops in order."""

    status: ExecutionStatus
    message_code: str | None = None
    ops_results: list[OpExecutionResult] = Field(default_factory=list)
    plan: QueryPlan | None = None
    missing_fields: list[str] = Field(default_factory=list)
    """Compact payload for the answer LLM (Phase 5); facts only, no invented text."""

    answer_context: dict[str, Any] = Field(default_factory=dict)

    def refusal_message(self) -> str:
        """Template response when execution cannot support a factual answer."""
        return refusal_message_for(self.message_code, answer_context=self.answer_context)


def refusal_message_for(
    message_code: str | None,
    *,
    answer_context: dict[str, Any] | None = None,
) -> str:
    ctx = answer_context or {}
    if message_code == "unsupported_request":
        reason = ctx.get("reason") or "That request is outside what this dataset can answer."
        return (
            f"I don't have information in our curated 200-town dataset to answer that. {reason} "
            f"I can help with stored home price, commute to Boston, safety, schools, coastal status, "
            f"and ranked recommendations from suburbs.json."
        )
    if message_code == "town_not_in_dataset":
        towns = ctx.get("unknown_towns") or []
        if towns:
            return (
                f"I don't have stored data for {', '.join(towns)} in the curated 200-town suburbs.json dataset. "
                "Please check the spelling or pick a town from the Boston-area list."
            )
        return (
            "I don't have that town in the curated 200-town suburbs.json dataset."
        )
    if message_code == "no_matching_towns":
        filters = ctx.get("filters_applied")
        suffix = f" Active filters: {filters}." if filters else ""
        return (
            "No towns in the dataset matched those filters, so I can't recommend options from stored data."
            + suffix
        )
    if message_code == "semantic_index_missing":
        return (
            "Semantic search is unavailable because the local vector index has not been built. "
            "Run scripts/build_vector_index.py or ask using specific town names and filters."
        )
    if message_code == "semantic_no_candidates":
        return (
            "Semantic search did not return any candidate towns from the dataset for that description."
        )
    if message_code == "compare_failed":
        return (
            "I couldn't build a comparison from the dataset for the towns named. "
            "Please use towns from the curated 200-town list."
        )
    if message_code == "membership_not_found":
        town = ctx.get("queried_town") or "That town"
        close = ctx.get("close_matches") or []
        msg = (
            f"No, {town} is not in the curated 200-town suburbs.json dataset."
        )
        if close:
            msg += f" Did you mean: {', '.join(close[:5])}?"
        return msg
    if message_code == "membership_found":
        town = ctx.get("town") or "That town"
        return f"Yes, {town} is in the curated 200-town suburbs.json dataset."
    if message_code == "lookup_field_unavailable":
        town = ctx.get("town") or "That town"
        field = ctx.get("field") or "requested field"
        return (
            f"I have {town} in the dataset, but stored {field} data is missing for that town."
        )
    return (
        "I don't have enough information in our curated dataset to answer that question accurately."
    )


def _merge_status(current: ExecutionStatus, new: ExecutionStatus) -> ExecutionStatus:
    if _STATUS_RANK[new] > _STATUS_RANK[current]:
        return new
    return current


def _format_price(value: float | int | None) -> str:
    if value is None:
        return "unavailable"
    return f"${int(value):,}"


def _extract_field_values(town: dict[str, Any], field: str) -> tuple[dict[str, Any], list[str]]:
    """Return stored values for a logical lookup field and list of missing dataset keys."""
    from app.tools import _public_suburb_record

    if field == LookupFieldKind.SUMMARY.value:
        record = _public_suburb_record(town)
        missing = [k for k, v in record.items() if v is None and k not in ("missing_fields", "tags")]
        return record, missing

    keys = lookup_field_dataset_keys(field)
    payload: dict[str, Any] = {}
    missing: list[str] = []
    for key in keys:
        value = town.get(key)
        payload[key] = value
        if value is None:
            missing.append(key)
    return payload, missing


def _lookup_snippet(name: str, town: dict[str, Any], field: str) -> str:
    """Short factual line for answer context (mirrors orchestrator lookup snippets)."""
    if field == LookupFieldKind.COMMUTE.value:
        minutes = town.get("drive_minutes_to_boston")
        miles = town.get("drive_distance_miles_to_boston")
        if minutes is not None:
            return (
                f"{name}: {miles or 'n/a'} miles from South Station, Boston "
                f"({minutes} min drive per suburbs.json)."
            )
        return f"{name}: commute data unavailable in dataset."
    if field == LookupFieldKind.PRICE.value:
        price = town.get("latest_home_price")
        year = town.get("home_price_year")
        if price is not None:
            suffix = f" ({year})" if year else ""
            return f"{name}: median home price {_format_price(price)}{suffix}."
        return f"{name}: housing price unavailable in dataset."
    if field == LookupFieldKind.SCHOOL.value:
        score = town.get("school_score")
        if score is not None:
            return f"{name}: school score {score}/10 (dataset percentile)."
        return f"{name}: school score unavailable in dataset."
    if field == LookupFieldKind.SAFETY.value:
        rate = town.get("crime_rate_per_1000")
        score = town.get("safety_score")
        if rate is not None:
            return f"{name}: crime rate {rate}/1k, safety score {score}/10."
        return f"{name}: safety/crime data unavailable in dataset."
    if field == LookupFieldKind.COASTAL.value:
        return (
            f"{name}: {'coastal' if town.get('is_coastal') else 'not coastal'} in dataset."
        )
    if field == LookupFieldKind.REGION.value:
        return f"{name}: region {town.get('region')}, county {town.get('county')}."
    if field == LookupFieldKind.MISSING.value:
        missing = town.get("missing_fields") or []
        return f"{name}: missing fields {', '.join(missing) if missing else 'none recorded'}."
    if field == LookupFieldKind.TIER.value:
        return f"{name}: data quality tier '{town.get('data_quality_tier')}'."
    return f"{name}: see summary fields in execution payload."


async def _execute_membership(op: MembershipOp) -> OpExecutionResult:
    lookup = get_town_facts(op.town)
    found = bool(lookup.get("found"))
    town = (lookup.get("town") or {}).get("name", op.town) if found else op.town
    close = lookup.get("close_matches") or []
    if found:
        snippet = f"Yes, {town} is in the curated 200-town suburbs.json dataset."
        return OpExecutionResult(
            op="membership",
            status=ExecutionStatus.OK,
            data={
                "found": True,
                "town": town,
                "queried_town": op.town,
                "snippets": [snippet],
                "score_disclaimer": SCORE_DISCLAIMER,
            },
            errors=[],
        )
    snippet = f"No, {op.town} is not in the curated 200-town suburbs.json dataset."
    if close:
        snippet += f" Did you mean: {', '.join(close[:5])}?"
    return OpExecutionResult(
        op="membership",
        status=ExecutionStatus.NOT_FOUND,
        data={
            "found": False,
            "town": None,
            "queried_town": op.town,
            "close_matches": close,
            "snippets": [snippet],
            "score_disclaimer": SCORE_DISCLAIMER,
        },
        errors=[lookup.get("message") or f"Town '{op.town}' not in dataset."],
    )


async def _execute_commute_pair(op: CommutePairOp) -> OpExecutionResult:
    result = get_commute_minutes(op.origin_town, op.destination_town)
    dest_label = commute_destination_label(op.destination_town)
    if result.drive_minutes is None:
        return OpExecutionResult(
            op="commute_pair",
            status=ExecutionStatus.PARTIAL,
            data={
                "origin_town": op.origin_town,
                "destination_town": op.destination_town,
                "commute_destination_label": dest_label,
                "drive_minutes_to_destination": None,
                "error": result.error,
            },
            errors=[result.error or "Commute time unavailable"],
        )

    snippet = (
        f"Drive from {op.origin_town} to {dest_label}: {result.drive_minutes} min"
        + (f" ({result.drive_miles} mi)" if result.drive_miles is not None else "")
        + "."
    )
    return OpExecutionResult(
        op="commute_pair",
        status=ExecutionStatus.OK,
        data={
            "origin_town": op.origin_town,
            "destination_town": op.destination_town,
            "commute_destination_label": dest_label,
            "drive_minutes_to_destination": result.drive_minutes,
            "drive_miles_to_destination": result.drive_miles,
            "source": result.source,
            "snippets": [snippet],
            "score_disclaimer": SCORE_DISCLAIMER,
        },
        errors=[],
    )


async def _execute_lookup(op: LookupOp) -> OpExecutionResult:
    items_out: list[dict[str, Any]] = []
    errors: list[str] = []
    snippets: list[str] = []
    status = ExecutionStatus.OK
    unknown_towns: list[str] = []

    for item in op.items:
        lookup = get_town_facts(item.town)
        row: dict[str, Any] = {
            "queried_town": item.town,
            "field": item.field,
            "found": lookup.get("found", False),
        }
        if not lookup.get("found"):
            status = _merge_status(status, ExecutionStatus.NOT_FOUND)
            unknown_towns.append(item.town)
            row["message"] = lookup.get("message")
            row["close_matches"] = lookup.get("close_matches") or []
            errors.append(lookup.get("message") or f"Town '{item.town}' not in dataset.")
            items_out.append(row)
            continue

        town = lookup["town"] or {}
        name = town.get("name", item.town)
        values, missing = _extract_field_values(town, item.field)
        row["town"] = name
        row["values"] = values
        row["missing_dataset_keys"] = missing
        if missing and item.field != LookupFieldKind.SUMMARY.value:
            status = _merge_status(status, ExecutionStatus.PARTIAL)
            errors.append(f"Missing stored keys for {name} ({item.field}): {', '.join(missing)}")
        snippets.append(_lookup_snippet(name, town, item.field))
        items_out.append(row)

    return OpExecutionResult(
        op="lookup",
        status=status,
        data={
            "items": items_out,
            "snippets": snippets,
            "unknown_towns": unknown_towns,
            "score_disclaimer": SCORE_DISCLAIMER,
        },
        errors=errors,
    )


def _execute_compare(op: CompareOp) -> OpExecutionResult:
    columns = list(op.columns) if op.columns else list(DEFAULT_COMPARE_COLUMNS)
    payload = compare_suburbs_multi_tool(op.towns, columns=columns)
    if op.commute_destination_town:
        from app.commute_service import commute_destination_label, get_commute_minutes

        dest = op.commute_destination_town
        dest_label = commute_destination_label(dest)
        for row in payload.get("comparison_table") or []:
            town = row.get("town")
            if not town:
                continue
            result = get_commute_minutes(town, dest)
            row["drive_minutes_to_destination"] = result.drive_minutes
        cols = list(payload.get("columns") or [])
        if not any(c.get("key") == "drive_minutes_to_destination" for c in cols):
            cols.append(
                {
                    "key": "drive_minutes_to_destination",
                    "label": f"Drive to {dest_label} (min)",
                }
            )
        payload["columns"] = cols
        payload["commute_destination_town"] = dest
        payload["commute_destination_label"] = dest_label
    errors = list(payload.get("errors") or [])
    row_count = int(payload.get("town_count") or 0)

    if row_count == 0:
        return OpExecutionResult(
            op="compare",
            status=ExecutionStatus.NOT_FOUND,
            data=payload,
            errors=errors or ["No towns could be compared."],
        )
    if errors:
        status = ExecutionStatus.PARTIAL if row_count >= 2 else ExecutionStatus.NOT_FOUND
    else:
        status = ExecutionStatus.OK

    return OpExecutionResult(
        op="compare",
        status=status,
        data=payload,
        errors=errors,
    )


def _execute_rank(op: RankOp, *, semantic_candidates: list[str] | None) -> OpExecutionResult:
    prefs = op.preferences.model_copy(deep=True)
    if op.use_semantic_candidates and semantic_candidates:
        prefs.candidate_towns = semantic_candidates

    results = rank_suburbs(prefs, top_n=op.limit)
    no_match = not results or (
        len(results) == 1 and results[0].get("no_matches")
    )

    if no_match:
        filters = describe_active_filters(prefs)
        return OpExecutionResult(
            op="rank",
            status=ExecutionStatus.NO_ROWS,
            data={
                "top_matches": results,
                "preferences": prefs.model_dump(exclude_none=True),
                "filters_applied": filters,
                "score_disclaimer": SCORE_DISCLAIMER,
            },
            errors=["No towns matched the rank filters."],
        )

    for row in results:
        row["score_disclaimer"] = SCORE_DISCLAIMER

    return OpExecutionResult(
        op="rank",
        status=ExecutionStatus.OK,
        data={
            "top_matches": results,
            "preferences": prefs.model_dump(exclude_none=True),
            "semantic_candidate_towns": semantic_candidates,
            "score_disclaimer": SCORE_DISCLAIMER,
        },
        errors=[],
    )


async def _execute_semantic(op: SemanticSearchOp) -> OpExecutionResult:
    payload = await run_semantic_town_search(op.query_text, top_k=op.top_k)
    if payload.get("error"):
        err = str(payload.get("error"))
        if "Vector index not found" in err or "Semantic search unavailable" in err:
            return OpExecutionResult(
                op="semantic_search",
                status=ExecutionStatus.NO_ROWS,
                data=payload,
                errors=[err],
            )
        return OpExecutionResult(
            op="semantic_search",
            status=ExecutionStatus.PARTIAL,
            data=payload,
            errors=[str(payload["error"])],
        )

    names = payload.get("candidate_town_names") or []
    if not names:
        return OpExecutionResult(
            op="semantic_search",
            status=ExecutionStatus.NO_ROWS,
            data=payload,
            errors=["Semantic search returned no candidates."],
        )

    return OpExecutionResult(
        op="semantic_search",
        status=ExecutionStatus.OK,
        data=payload,
        errors=[],
    )


def _execute_unsupported(op: UnsupportedOp) -> OpExecutionResult:
    return OpExecutionResult(
        op="unsupported",
        status=ExecutionStatus.OUT_OF_SCOPE,
        data={
            "category": op.category.value,
            "reason": op.reason,
            "user_message_hint": op.user_message_hint,
        },
        errors=[op.reason],
    )


def _derive_message_code(
    status: ExecutionStatus,
    ops_results: list[OpExecutionResult],
) -> str | None:
    if status == ExecutionStatus.OUT_OF_SCOPE:
        return "unsupported_request"
    if status == ExecutionStatus.INVALID_PLAN:
        return "invalid_plan"
    if status == ExecutionStatus.NO_ROWS:
        for op_result in ops_results:
            if op_result.op == "semantic_search":
                if any("Vector index" in e for e in op_result.errors):
                    return "semantic_index_missing"
                return "semantic_no_candidates"
            if op_result.op == "rank":
                return "no_matching_towns"
        return "no_matching_towns"
    if status == ExecutionStatus.NOT_FOUND:
        for op_result in ops_results:
            if op_result.op == "membership":
                return "membership_not_found"
            if op_result.op == "compare":
                return "compare_failed"
            if op_result.op == "lookup":
                return "town_not_in_dataset"
        return "town_not_in_dataset"
    if status == ExecutionStatus.OK:
        for op_result in ops_results:
            if op_result.op == "membership":
                return "membership_found"
    if status == ExecutionStatus.PARTIAL:
        for op_result in ops_results:
            if op_result.op == "lookup" and op_result.errors:
                return "lookup_field_unavailable"
        return "partial_data"
    return None


def _build_answer_context(
    plan: QueryPlan,
    ops_results: list[OpExecutionResult],
    *,
    status: ExecutionStatus,
    message_code: str | None,
) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "user_intent_summary": plan.user_intent_summary,
        "execution_status": status.value,
        "message_code": message_code,
        "score_disclaimer": SCORE_DISCLAIMER,
        "ops": [],
    }
    unknown: list[str] = []

    for op_result in ops_results:
        entry: dict[str, Any] = {"op": op_result.op, "status": op_result.status.value}
        if op_result.op == "membership":
            entry["found"] = op_result.data.get("found")
            entry["town"] = op_result.data.get("town")
            entry["queried_town"] = op_result.data.get("queried_town")
            entry["snippets"] = op_result.data.get("snippets", [])
            entry["close_matches"] = op_result.data.get("close_matches") or []
            if not op_result.data.get("found"):
                unknown.append(op_result.data.get("queried_town") or "")
        elif op_result.op == "lookup":
            entry["items"] = op_result.data.get("items", [])
            entry["snippets"] = op_result.data.get("snippets", [])
            unknown.extend(op_result.data.get("unknown_towns") or [])
        elif op_result.op == "compare":
            entry["comparison_table"] = op_result.data.get("comparison_table", [])
            entry["columns"] = op_result.data.get("columns", [])
            entry["commute_destination_town"] = op_result.data.get("commute_destination_town")
            entry["commute_destination_label"] = op_result.data.get("commute_destination_label")
            entry["errors"] = op_result.errors
        elif op_result.op == "rank":
            entry["top_matches"] = op_result.data.get("top_matches", [])
            entry["preferences"] = op_result.data.get("preferences", {})
        elif op_result.op == "semantic_search":
            entry["candidates"] = op_result.data.get("candidates", [])
            entry["candidate_town_names"] = op_result.data.get("candidate_town_names", [])
        elif op_result.op == "commute_pair":
            entry.update(
                {
                    "origin_town": op_result.data.get("origin_town"),
                    "destination_town": op_result.data.get("destination_town"),
                    "commute_destination_label": op_result.data.get("commute_destination_label"),
                    "drive_minutes_to_destination": op_result.data.get("drive_minutes_to_destination"),
                    "drive_miles_to_destination": op_result.data.get("drive_miles_to_destination"),
                    "snippets": op_result.data.get("snippets", []),
                }
            )
        elif op_result.op == "unsupported":
            entry["reason"] = op_result.data.get("reason")
            ctx["reason"] = op_result.data.get("reason")
        if op_result.errors:
            entry["errors"] = op_result.errors
        ctx["ops"].append(entry)

    if unknown:
        ctx["unknown_towns"] = unknown
    for op_result in ops_results:
        if op_result.op == "rank":
            ctx["filters_applied"] = op_result.data.get("filters_applied")
            break

    return ctx


async def execute_plan_async(
    plan: QueryPlan | dict[str, Any],
    *,
    validate: bool = True,
) -> ExecutionResult:
    """
    Run a query plan against suburbs.json and (when needed) the local vector index.

    Does not call any answer-generation LLM.
    """
    try:
        normalized = validate_plan(plan) if validate else (
            plan if isinstance(plan, QueryPlan) else QueryPlan.model_validate(plan)
        )
    except PlanValidationError as exc:
        return ExecutionResult(
            status=ExecutionStatus.INVALID_PLAN,
            message_code="invalid_plan",
            ops_results=[],
            plan=None,
            answer_context={"error": str(exc)},
        )

    ops_results: list[OpExecutionResult] = []
    aggregate = ExecutionStatus.OK
    semantic_candidates: list[str] | None = None
    missing_fields: list[str] = []

    for op in normalized.ops:
        if isinstance(op, UnsupportedOp):
            op_result = _execute_unsupported(op)
        elif isinstance(op, MembershipOp):
            op_result = await _execute_membership(op)
        elif isinstance(op, LookupOp):
            op_result = await _execute_lookup(op)
        elif isinstance(op, CompareOp):
            op_result = _execute_compare(op)
        elif isinstance(op, SemanticSearchOp):
            op_result = await _execute_semantic(op)
            if op_result.status == ExecutionStatus.OK:
                semantic_candidates = op_result.data.get("candidate_town_names") or []
        elif isinstance(op, RankOp):
            rank_op = op
            if semantic_candidates and not rank_op.use_semantic_candidates:
                rank_op = rank_op.model_copy(update={"use_semantic_candidates": True})
            op_result = _execute_rank(rank_op, semantic_candidates=semantic_candidates)
        elif isinstance(op, CommutePairOp):
            op_result = await _execute_commute_pair(op)
        else:
            continue

        ops_results.append(op_result)
        aggregate = _merge_status(aggregate, op_result.status)

        if op_result.op == "lookup":
            for item in op_result.data.get("items", []):
                missing_fields.extend(item.get("missing_dataset_keys") or [])

    message_code = _derive_message_code(aggregate, ops_results)
    answer_context = _build_answer_context(
        normalized,
        ops_results,
        status=aggregate,
        message_code=message_code,
    )

    return ExecutionResult(
        status=aggregate,
        message_code=message_code,
        ops_results=ops_results,
        plan=normalized,
        missing_fields=sorted(set(missing_fields)),
        answer_context=answer_context,
    )


def execute_plan(
    plan: QueryPlan | dict[str, Any],
    *,
    validate: bool = True,
) -> ExecutionResult:
    """Synchronous wrapper for ``execute_plan_async`` (safe when no event loop is running)."""
    return asyncio.run(execute_plan_async(plan, validate=validate))
