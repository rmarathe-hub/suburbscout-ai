"""Phase 1.5 — LLM classify-only fallback (intent JSON, no ranking)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app import config
from app.constraint_parser import parse_constraints
from app.entity_extractor import ExtractedEntities, extract_entities
from app.intent_classifier import ClassifiedIntent

logger = logging.getLogger(__name__)

ALLOWED_LLM_INTENTS = frozenset({
    "lookup_single_town",
    "dataset_membership",
    "compare_towns",
    "recommend_structured",
    "recommend_semantic",
    "refuse_out_of_scope",
    "unsupported",
})

CLASSIFY_SYSTEM_INSTRUCTIONS = """You are the intent classifier for SuburbScout, a Boston-area MA suburb dataset agent.

Classify the user message ONLY. Do not recommend towns, rank suburbs, or invent data.

Dataset scope:
- 200 curated Massachusetts Boston-area towns in suburbs.json
- Commute data is to South Station, Boston only
- Providence, Nashua, Springfield MA, Amherst, Cape Cod as a region, and non-MA places are out of scope

Intent definitions:
- lookup_single_town: one town's stored facts (price, safety, schools, commute, coastal tag, missing fields)
- dataset_membership: is a town/alias in the dataset, spelling, alias mapping, searchable
- compare_towns: compare exactly two towns on price/safety/schools/commute/coastal
- recommend_structured: list/rank towns with numeric constraints (budget, commute minutes, coastal filter).
  Examples: "towns within 30 minutes", "under 700k", "coastal only", tradeoff/inverted affordability prompts.
- recommend_semantic: vibe/similar-town preference without strict numbers only
- refuse_out_of_scope: outside dataset, non-MA, Cape Cod region question, missing town meta
- unsupported: not a suburb query

Rules:
- Never output final town recommendations
- compare_towns requires exactly 2 towns in "towns"
- lookup_single_town or dataset_membership: usually 1 town; scope questions may have 0 towns
- Use refuse_out_of_scope for Providence, Nashua, Springfield, Amherst, Cape Cod communities, non-MA

Return ONLY valid JSON (no markdown) with this schema:
{
  "intent": "<one of the intents above>",
  "towns": ["Town Name"],
  "field": null,
  "constraints": {},
  "confidence": 0.0,
  "reason": "short explanation"
}

"field" is optional: commute, safety, school, price, coastal, missing, dataset, summary.
"constraints" may include budget_max, max_commute_minutes, min_commute_minutes, coastal_only when explicit.
"""


class LlmIntentPayload(BaseModel):
    intent: str
    towns: list[str] = Field(default_factory=list)
    field: str | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.0
    reason: str = ""


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped, re.I)
    if fence:
        stripped = fence.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object in LLM response")
    return json.loads(stripped[start : end + 1])


def _build_user_message(
    query: str,
    entities: ExtractedEntities,
    python_hint: ClassifiedIntent,
) -> str:
    constraints = parse_constraints(query)
    hint = {
        "intent": python_hint.intent,
        "confidence": python_hint.confidence,
        "reason": python_hint.reason,
        "lookup_town": python_hint.lookup_town,
        "compare": [python_hint.compare_town_a, python_hint.compare_town_b],
    }
    ctx = {
        "user_query": query,
        "python_classifier_hint": hint,
        "valid_towns": entities.valid_towns,
        "unknown_town_candidates": entities.unknown_town_candidates,
        "compare_pair": list(entities.compare_pair) if entities.compare_pair else None,
        "parsed_constraints": constraints.model_dump(exclude_none=True),
    }
    return (
        "Classify this suburb query.\n\n"
        f"{json.dumps(ctx, indent=2)}\n\n"
        "Return JSON only."
    )


async def classify_intent_with_llm(
    query: str,
    *,
    entities: ExtractedEntities | None = None,
    python_hint: ClassifiedIntent | None = None,
) -> LlmIntentPayload:
    """Call chat model for classify-only JSON."""
    from agent_framework import Agent

    from app.chat_client import get_chat_client
    from app.real_estate_agent import response_text

    entities = entities or extract_entities(query)
    python_hint = python_hint or ClassifiedIntent(
        intent="unsupported", confidence=0.0, reason="no python hint"
    )

    agent = Agent(
        client=get_chat_client(),
        name="SuburbScoutIntentClassifier",
        instructions=CLASSIFY_SYSTEM_INSTRUCTIONS,
        tools=[],
    )
    user_msg = _build_user_message(query, entities, python_hint)
    response = await agent.run(user_msg)
    text = response_text(response)
    raw = _extract_json_object(text)
    payload = LlmIntentPayload.model_validate(raw)
    if payload.intent not in ALLOWED_LLM_INTENTS:
        raise ValueError(f"LLM returned disallowed intent: {payload.intent}")
    payload.confidence = max(0.0, min(1.0, float(payload.confidence)))
    return payload


def llm_fallback_available() -> bool:
    return bool(
        config.LLM_INTENT_FALLBACK_ENABLED
        and config.AZURE_OPENAI_API_KEY
        and config.CHAT_MODEL_DEPLOYMENT
    )
