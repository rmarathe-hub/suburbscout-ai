"""Phase 5 — full query agent: plan → execute → grounded answer."""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from app.llm_answer import (
    AnswerValidationResult,
    generate_answer_with_llm,
    should_use_answer_llm,
)
from app.llm_query_planner import plan_query_with_llm, planner_available
from app.plan_executor import ExecutionResult, execute_plan_async
from app.plan_trust_gates import evaluate_plan_trust_gate, plan_to_query_route
from app.query_plan import QueryPlan
from app.tools import SCORE_DISCLAIMER
from app.trust_gates import TrustGateResult

logger = logging.getLogger(__name__)


def _commute_metadata(query: str, plan: QueryPlan | None = None) -> dict[str, Any]:
    from app.commute_intent import resolve_commute_intent

    dest = resolve_commute_intent(
        query,
        plan.commute_intent if plan else None,
        plan=plan,
    ).to_destination_result()
    return {
        "commute_destination": dest.label,
        "commute_destination_is_default": dest.is_default,
        "commute_destination_town": dest.commute_destination_town,
    }


def query_agent_available() -> bool:
    from app import config

    return bool(config.USE_LLM_QUERY_AGENT and planner_available())


def _extract_structured_fields(execution: ExecutionResult) -> dict[str, Any]:
    """Map execution ops into orchestrator-compatible response keys."""
    top_matches: list[dict[str, Any]] = []
    comparison: dict[str, Any] | None = None
    lookup_payload: dict[str, Any] | None = None
    semantic_candidates: dict[str, Any] | None = None

    for op_result in execution.ops_results:
        if op_result.op == "rank":
            top_matches = list(op_result.data.get("top_matches") or [])
        elif op_result.op == "compare":
            comparison = {
                "comparison_table": op_result.data.get("comparison_table"),
                "columns": op_result.data.get("columns"),
                "towns": op_result.data.get("towns"),
                "errors": op_result.data.get("errors"),
            }
        elif op_result.op == "lookup":
            items = op_result.data.get("items") or []
            if len(items) == 1:
                item = items[0]
                lookup_payload = {
                    "found": item.get("found"),
                    "queried_name": item.get("queried_town"),
                    "town": {"name": item.get("town"), **(item.get("values") or {})}
                    if item.get("found")
                    else None,
                    "close_matches": item.get("close_matches") or [],
                }
            else:
                lookup_payload = {"multi": items}
        elif op_result.op == "commute_pair":
            data = op_result.data
            lookup_payload = {
                "found": data.get("drive_minutes_to_destination") is not None,
                "queried_name": data.get("origin_town"),
                "town": {
                    "name": data.get("origin_town"),
                    "drive_minutes_to_destination": data.get("drive_minutes_to_destination"),
                    "commute_destination_label": data.get("commute_destination_label"),
                    "commute_destination_town": data.get("destination_town"),
                },
            }
        elif op_result.op == "semantic_search":
            semantic_candidates = {
                k: op_result.data.get(k)
                for k in (
                    "query",
                    "candidates",
                    "candidate_town_names",
                    "usage_note",
                    "error",
                )
                if op_result.data.get(k) is not None
            }

    return {
        "top_matches": top_matches,
        "comparison": comparison,
        "lookup": lookup_payload,
        "semantic_candidates": semantic_candidates,
    }


async def handle_query_v2(
    prompt: str,
    *,
    save_searches: bool = False,
    session_id: str | None = None,
) -> dict[str, Any]:
    """
    Two-stage query agent: LLM plan → dataset execution → grounded answer (or refusal).

    Does not call save_search_tool (Phase 7 can add audit logging).
    """
    query = prompt.strip()
    if not query:
        return _empty_response(query)

    if not query_agent_available():
        raise ValueError(
            "Query agent is not available. Enable USE_LLM_QUERY_AGENT and configure Azure OpenAI."
        )

    session_context: dict[str, Any] | None = None
    if session_id:
        try:
            from app.repositories import SearchRepository

            session_context = SearchRepository().get_session_context(session_id)
        except Exception:
            logger.warning("failed to load session context", exc_info=True)

    request_id = str(uuid.uuid4())
    started = time.perf_counter()

    raw_plan: QueryPlan = await plan_query_with_llm(
        query,
        apply_normalizer=False,
        session_context=session_context,
    )
    from app.plan_normalizer import normalize_planned_query

    plan = normalize_planned_query(query, raw_plan)
    trust_gate = evaluate_plan_trust_gate(query, plan)

    if trust_gate and trust_gate.blocks_pipeline:
        latency_ms = int((time.perf_counter() - started) * 1000)
        payload = _trust_gate_response(
            query,
            plan,
            trust_gate,
            raw_plan=raw_plan,
            request_id=request_id,
            latency_ms=latency_ms,
        )
        _persist_turn(query, payload, session_id=session_id, save_searches=save_searches)
        return payload

    execution: ExecutionResult = await execute_plan_async(plan, validate=False)

    answer_validation: AnswerValidationResult | None = None
    used_answer_llm = False
    tradeoff_warning: str | None = None
    if trust_gate and not trust_gate.blocks_pipeline:
        tradeoff_warning = trust_gate.message

    if should_use_answer_llm(execution):
        final, answer_validation = await generate_answer_with_llm(query, execution)
        used_answer_llm = True
    else:
        final = execution.refusal_message()

    structured = _extract_structured_fields(execution)
    warnings = list(answer_validation.warnings if answer_validation else [])
    if trust_gate and trust_gate.gate_type:
        warnings.append(f"trust_gate:{trust_gate.gate_type}")
    validation_payload = {
        "valid": answer_validation.valid if answer_validation else True,
        "errors": answer_validation.errors if answer_validation else [],
        "warnings": warnings,
    }

    response: dict[str, Any] = {
        "query": query,
        "preferences": None,
        "semantic_candidates": structured["semantic_candidates"],
        "top_matches": structured["top_matches"],
        "comparison": structured["comparison"],
        "lookup": structured["lookup"],
        "tradeoff_warning": tradeoff_warning,
        "final_recommendation": final,
        "score_disclaimer": SCORE_DISCLAIMER,
        "route_intent": "query_agent",
        "orchestrated": True,
        "query_agent": True,
        "execution_status": execution.status.value,
        "message_code": execution.message_code,
        "validation": validation_payload,
    }

    latency_ms = int((time.perf_counter() - started) * 1000)

    payload: dict[str, Any] = {
        "response": response,
        "request_id": request_id,
        "latency_ms": latency_ms,
        "plan": plan.model_dump(mode="json"),
        "raw_llm_plan": raw_plan.model_dump(mode="json"),
        "normalized_plan": plan.model_dump(mode="json"),
        "execution_status": execution.status.value,
        "message_code": execution.message_code,
        "used_answer_llm": used_answer_llm,
        "query_agent": True,
        "metadata": _commute_metadata(query, plan),
    }
    if trust_gate:
        payload["trust_gate"] = trust_gate.gate_type
        payload["trust_gate_blocks"] = trust_gate.blocks_pipeline

    _persist_turn(query, payload, session_id=session_id, save_searches=save_searches)

    return payload


def _persist_turn(
    prompt: str,
    payload: dict[str, Any],
    *,
    session_id: str | None,
    save_searches: bool,
) -> None:
    from app.db import db_configured
    from app.repositories import persist_query_turn

    if not db_configured() and not save_searches:
        return
    persist_query_turn(
        prompt,
        payload,
        session_id=session_id,
        save_jsonl=save_searches,
    )


def _trust_gate_response(
    query: str,
    plan: QueryPlan,
    gate: TrustGateResult,
    *,
    raw_plan: QueryPlan | None = None,
    request_id: str | None = None,
    latency_ms: int | None = None,
) -> dict[str, Any]:
    route = plan_to_query_route(query, plan)
    rid = request_id or str(uuid.uuid4())
    return {
        "request_id": rid,
        "latency_ms": latency_ms,
        "response": {
            "query": query,
            "preferences": None,
            "semantic_candidates": None,
            "top_matches": [],
            "comparison": None,
            "lookup": None,
            "tradeoff_warning": None,
            "final_recommendation": gate.message,
            "score_disclaimer": SCORE_DISCLAIMER,
            "route_intent": route.intent,
            "orchestrated": True,
            "query_agent": True,
            "trust_gate": gate.gate_type,
            "validation": {
                "valid": True,
                "errors": [],
                "warnings": [f"trust_gate:{gate.gate_type}"],
            },
        },
        "plan": plan.model_dump(mode="json"),
        "raw_llm_plan": (raw_plan or plan).model_dump(mode="json"),
        "normalized_plan": plan.model_dump(mode="json"),
        "execution_status": "blocked",
        "message_code": gate.gate_type,
        "used_answer_llm": False,
        "query_agent": True,
        "trust_gate": gate.gate_type,
        "trust_gate_blocks": gate.blocks_pipeline,
        "metadata": _commute_metadata(query, plan),
    }


def _empty_response(query: str) -> dict[str, Any]:
    return {
        "response": {
            "query": query,
            "final_recommendation": "Please enter a suburb question.",
            "orchestrated": True,
            "query_agent": True,
            "validation": {"valid": True, "errors": [], "warnings": []},
        },
        "plan": None,
        "execution_status": "invalid_plan",
        "query_agent": True,
    }
