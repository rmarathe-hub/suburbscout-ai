"""Foundry Hosted Agent adapter — routes Responses protocol to handle_query_v2."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Sequence
from typing import Any

from agent_framework import AgentResponse, AgentResponseUpdate, Content, Message

from app.config import AGENT_NAME
from app.query_agent import handle_query_v2, query_agent_available

logger = logging.getLogger(__name__)


def _extract_user_prompt(messages: Sequence[Message] | Message | None) -> str:
    """Last user turn text from Agent Framework messages."""
    if messages is None:
        return ""
    seq = [messages] if isinstance(messages, Message) else list(messages)

    for msg in reversed(seq):
        if getattr(msg, "role", None) != "user":
            continue
        parts = [
            (content.text or "").strip()
            for content in (msg.contents or [])
            if getattr(content, "type", None) == "text" and (content.text or "").strip()
        ]
        if parts:
            return "\n".join(parts).strip()

    for msg in seq:
        if getattr(msg, "role", None) != "user":
            continue
        parts = [
            (content.text or "").strip()
            for content in (msg.contents or [])
            if getattr(content, "type", None) == "text" and (content.text or "").strip()
        ]
        if parts:
            return "\n".join(parts).strip()
    return ""


def payload_to_hosted_agent_json(payload: dict[str, Any]) -> dict[str, Any]:
    """Map handle_query_v2 output to legacy hosted-agent JSON for Foundry clients."""
    response = dict(payload.get("response") or {})
    body: dict[str, Any] = {
        **response,
        "execution_status": payload.get("execution_status"),
        "message_code": payload.get("message_code"),
        "query_agent": True,
    }
    if payload.get("trust_gate"):
        body["trust_gate"] = payload["trust_gate"]
    if payload.get("metadata"):
        body["metadata"] = payload["metadata"]
    return body


class QueryPipelineHostedAgent:
    """SupportsAgentRun wrapper — same pipeline as FastAPI BACKEND_AGENT_MODE=local."""

    id = "suburbscout-query-pipeline"
    name = AGENT_NAME
    description = "SuburbScout planner-first query pipeline (handle_query_v2)"
    context_providers: list[Any] = []

    async def run(
        self,
        messages: Sequence[Message] | Message | None = None,
        *,
        stream: bool = False,
        session: Any = None,
        **kwargs: Any,
    ) -> AgentResponse | AsyncIterator[AgentResponseUpdate]:
        if stream:
            return self._run_stream(messages, **kwargs)

        text = await self._run_once(messages, **kwargs)
        return AgentResponse(
            messages=[
                Message(
                    role="assistant",
                    contents=[Content.from_text(text)],
                )
            ]
        )

    async def _run_stream(
        self,
        messages: Sequence[Message] | Message | None,
        **kwargs: Any,
    ) -> AsyncIterator[AgentResponseUpdate]:
        text = await self._run_once(messages, **kwargs)
        yield AgentResponseUpdate(contents=[Content.from_text(text)])

    async def _run_once(
        self,
        messages: Sequence[Message] | Message | None,
        **kwargs: Any,
    ) -> str:
        prompt = _extract_user_prompt(messages)
        if not prompt:
            return json.dumps(
                {
                    "final_recommendation": "Please enter a suburb question.",
                    "execution_status": "invalid_plan",
                    "query_agent": True,
                }
            )

        if not query_agent_available():
            return json.dumps(
                {
                    "final_recommendation": (
                        "Query agent is not configured. Set Azure OpenAI credentials "
                        "and USE_LLM_QUERY_AGENT=true."
                    ),
                    "execution_status": "error",
                    "query_agent": True,
                }
            )

        save_searches = bool(kwargs.get("save_searches", True))
        session_id = kwargs.get("session_id")

        try:
            payload = await handle_query_v2(
                prompt,
                save_searches=save_searches,
                session_id=session_id,
            )
            return json.dumps(payload_to_hosted_agent_json(payload), ensure_ascii=False)
        except Exception:
            logger.exception("handle_query_v2 failed in hosted agent")
            return json.dumps(
                {
                    "final_recommendation": (
                        "Sorry, something went wrong processing your request. Please try again."
                    ),
                    "execution_status": "error",
                    "query_agent": True,
                }
            )
