"""Shared query-agent eval runner (Phase 9 — unified on handle_query_v2)."""

from __future__ import annotations

from typing import Any


async def run_query_agent_prompt(
    prompt: str,
    *,
    save_searches: bool = False,
) -> dict[str, Any]:
    """Execute one prompt through the live query-agent pipeline."""
    from app.query_agent import handle_query_v2, query_agent_available

    if not query_agent_available():
        raise RuntimeError(
            "Query agent unavailable — set AZURE_OPENAI_API_KEY and CHAT_MODEL_DEPLOYMENT"
        )
    return await handle_query_v2(prompt, save_searches=save_searches)


def plan_primary_op(plan: dict[str, Any] | None) -> str | None:
    """Best-effort primary op label from a QueryPlan dict."""
    if not plan:
        return None
    ops = plan.get("ops") or []
    if not ops:
        return None
    first = ops[0]
    if isinstance(first, dict):
        return str(first.get("op") or "")
    return None


def comparison_row_count(payload: dict[str, Any]) -> int:
    response = payload.get("response") or {}
    comp = response.get("comparison") or {}
    table = comp.get("comparison_table") or []
    return len(table)
