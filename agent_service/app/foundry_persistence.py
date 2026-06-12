"""Phase 7 Step 4 — persist Foundry hosted-agent turns to Postgres."""

from __future__ import annotations

from typing import Any

from app.repositories import persist_query_turn


def build_persist_payload_from_foundry(
    normalized: dict[str, Any],
    *,
    latency_ms: int | None = None,
) -> dict[str, Any]:
    """Shape normalized Foundry output for SearchRepository.save_turn."""
    response_body = dict(normalized.get("response") or {})
    answer = str(normalized.get("answer") or response_body.get("final_recommendation") or "")

    response = {
        **response_body,
        "final_recommendation": answer,
        "top_matches": normalized.get("top_matches")
        if normalized.get("top_matches") is not None
        else response_body.get("top_matches") or [],
        "comparison": normalized.get("comparison")
        if "comparison" in normalized
        else response_body.get("comparison"),
        "lookup": response_body.get("lookup"),
        "semantic_candidates": response_body.get("semantic_candidates"),
        "tradeoff_warning": normalized.get("tradeoff_warning")
        if normalized.get("tradeoff_warning") is not None
        else response_body.get("tradeoff_warning"),
        "score_disclaimer": normalized.get("score_disclaimer")
        if normalized.get("score_disclaimer") is not None
        else response_body.get("score_disclaimer"),
    }

    return {
        "request_id": str(normalized.get("request_id") or ""),
        "execution_status": str(normalized.get("execution_status") or "ok"),
        "message_code": normalized.get("message_code") or "foundry_hosted_agent",
        "latency_ms": latency_ms if latency_ms is not None else normalized.get("latency_ms"),
        "used_answer_llm": bool(normalized.get("used_answer_llm", True)),
        "response": response,
        "source": normalized.get("source") or "foundry_hosted_agent",
        "metadata": normalized.get("metadata"),
    }


def persist_foundry_turn(
    prompt: str,
    normalized: dict[str, Any],
    *,
    session_id: str | None = None,
    save_audit: bool = False,
    latency_ms: int | None = None,
) -> dict[str, Any]:
    """
    Best-effort persist for a Foundry gateway turn.

    Mirrors local handle_query_v2 persistence: writes when save_audit is true.
    """
    if not save_audit:
        return {"saved": False, "reason": "save_audit_disabled"}

    payload = build_persist_payload_from_foundry(normalized, latency_ms=latency_ms)
    return persist_query_turn(
        prompt,
        payload,
        session_id=session_id,
        save_jsonl=save_audit,
    )
