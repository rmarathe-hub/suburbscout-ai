"""Phase 4 — LLM produces validated QueryPlan JSON from natural language.

Behavior contract (what the planner may/must not do): app.llm_contract
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import ValidationError

from app import config
from app.entity_extractor import ExtractedEntities, extract_entities
from app.plan_preferences import validate_planner_plan_semantics
from app.query_plan import (
    PlanValidationError,
    QueryPlan,
    plan_schema_prompt_block,
    validate_plan,
)

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_INSTRUCTIONS = f"""You are the query planner for SuburbScout (Boston-area MA suburbs).

Your job: convert the user message into a QueryPlan JSON object that describes which dataset operations to run.
Do NOT answer the user. Do NOT invent prices, scores, commute times, or town names.

Dataset scope:
- 200 curated towns in suburbs.json only
- Commute data is drive time to {config.COMMUTE_DESTINATION}
- Live Zillow/MLS, neighborhood-level detail, MBTA/transit, demographics, forecasts → op "unsupported"

{plan_schema_prompt_block()}

Op selection guide:
- Dataset scope only ("Is X in your dataset?", "Do you track X?", "Would X be accepted?", "Would X resolve correctly?") → "membership" with town (NOT summary lookup).
- Typo or misspelled town + factual question (coastal, price, schools, safety, tier, partial-data, expensive, summary) → "lookup" with items[{{town, field}}], NOT membership.
- One or more town+field factual questions → "lookup" with items[{{town, field}}]. Fields: summary, commute, price, school, safety, coastal, region, missing, tier.
- Compare 2–20 towns on columns → "compare" with towns[] and optional columns.
- List/find coastal or waterfront towns → "rank" with requires_coastal=true (NOT semantic_search).
- Recommend / find / rank with budget, commute, schools, exclude → "rank" with preferences and limit (default 10).
- Vibe / feel / "like X" / "similar to X" (even with coastal or budget hints) → "semantic_search" then "rank" with use_semantic_candidates=true; put coastal/budget prefs on rank when stated.
- Out of scope → single "unsupported" op with category from: live_market, neighborhood, safety_granular, school_detail, demographics, transit, lifestyle, other.
- Deprioritize schools / ignore school quality / weaker schools OK / focus on price → "rank" with deprioritize_schools=true (NOT unsupported).

Preferences for rank (use exact string enums high|medium|low for *_priority, booleans for requires_coastal, deprioritize_safety, deprioritize_schools, prefer_high_crime, allow_low_safety):
budget_max, max_commute_minutes, min_commute_minutes, requires_coastal, school_priority, safety_priority,
commute_priority, affordability_priority, deprioritize_safety, deprioritize_schools, prefer_high_crime, allow_low_safety,
exclude_towns, named_towns, candidate_towns, region_preference, county_preference.
Never use school_priority=high when user accepts weaker schools. Never invent placeholder town names (town_name_*, example_town).

Rules:
- Max 20 towns per compare; max 20 lookup items; max 12 ops.
- Use canonical MA town names when possible (e.g. Westborough not Westboro in items).
- Never output prose or markdown — JSON only.

Few-shot examples (operation selection only):

Q: "Would Boxford be accepted as a town name?"
A: {{"ops":[{{"op":"membership","town":"Boxford"}}]}}

Q: "Pull up Chelmsfrd."
A: {{"ops":[{{"op":"lookup","items":[{{"town":"Chelmsford","field":"summary"}}]}}]}}

Q: "Marlborugh versus Burlington for safety."
A: {{"ops":[{{"op":"compare","towns":["Marlborough","Burlington"],"columns":["safety_score"]}}]}}

Q: "Crime can be higher if homes are cheap."
A: {{"ops":[{{"op":"rank","preferences":{{"affordability_priority":"high","allow_low_safety":true,"deprioritize_safety":true,"prefer_high_crime":true}},"limit":10}}]}}

Q: "Which neighborhood in Brookline is best for kids?"
A: {{"ops":[{{"op":"unsupported","category":"neighborhood","reason":"neighborhood-level detail"}}]}}

Q: "Places similar to Newton for young families."
A: {{"ops":[{{"op":"semantic_search","query_text":"similar to Newton young families","top_k":10}},{{"op":"rank","preferences":{{}},"limit":10,"use_semantic_candidates":true}}]}}

Q: "Compare Bedford and Lexington if my job is in Providence."
A: {{"commute_intent":{{"commute_destination_town":"Providence","commute_context":"unsupported","compare_towns":["Bedford","Lexington"]}},"ops":[{{"op":"compare","towns":["Bedford","Lexington"]}}]}}

Q: "Acton or Burlington if my office is in Cambridge?"
A: {{"commute_intent":{{"commute_destination_town":"Cambridge","commute_context":"destination_town","compare_towns":["Acton","Burlington"]}},"ops":[{{"op":"compare","towns":["Acton","Burlington"]}}]}}

Q: "My job is in Cambridge, and I want safe towns below 900k."
A: {{"commute_intent":{{"commute_destination_town":"Cambridge","commute_context":"destination_town"}},"ops":[{{"op":"rank","preferences":{{"budget_max":900000,"safety_priority":"high"}},"limit":10}}]}}

Q: "Waltham commute under 25 minutes, good schools, under 1M."
A: {{"commute_intent":{{"commute_destination_town":"Waltham","commute_context":"destination_town"}},"ops":[{{"op":"rank","preferences":{{"max_commute_minutes":25,"school_priority":"high","budget_max":1000000}},"limit":10}}]}}

Q: "Keep me below 30 minutes to Somerville and under 850k."
A: {{"commute_intent":{{"commute_destination_town":"Somerville","commute_context":"destination_town"}},"ops":[{{"op":"rank","preferences":{{"max_commute_minutes":30,"budget_max":850000}},"limit":10}}]}}

Q: "Quincy drive under 30, affordable towns only."
A: {{"commute_intent":{{"commute_destination_town":"Quincy","commute_context":"destination_town"}},"ops":[{{"op":"rank","preferences":{{"max_commute_minutes":30,"affordability_priority":"high"}},"limit":10}}]}}

Q: "Compare Brookline and Cambridge on price and schools."
A: {{"commute_intent":{{"commute_context":"default_boston"}},"ops":[{{"op":"compare","towns":["Brookline","Cambridge"],"columns":["price","school_score"]}}]}}

Q: "Compare Newton and Wellesley on schools and home price."
A: {{"commute_intent":{{"commute_context":"default_boston"}},"ops":[{{"op":"compare","towns":["Newton","Wellesley"],"columns":["school_score","price"]}}]}}

Q: "Salem commute below 35 minutes, safe towns."
A: {{"commute_intent":{{"commute_destination_town":"Salem","commute_context":"destination_town"}},"ops":[{{"op":"rank","preferences":{{"max_commute_minutes":35,"safety_priority":"high"}},"limit":10}}]}}

Q: "Brookline within 25 minutes, good schools."
A: {{"commute_intent":{{"commute_destination_town":"Brookline","commute_context":"destination_town"}},"ops":[{{"op":"rank","preferences":{{"max_commute_minutes":25,"school_priority":"high"}},"limit":10}}]}}

Q: "Cambridge commute less than 35, affordable."
A: {{"commute_intent":{{"commute_destination_town":"Cambridge","commute_context":"destination_town","max_commute_minutes":35}},"ops":[{{"op":"rank","preferences":{{"max_commute_minutes":35,"affordability_priority":"high"}},"limit":10}}]}}

Q: "Waltham below 25 min commute and affordable."
A: {{"commute_intent":{{"commute_destination_town":"Waltham","commute_context":"destination_town","max_commute_minutes":25}},"ops":[{{"op":"rank","preferences":{{"max_commute_minutes":25,"affordability_priority":"high"}},"limit":10}}]}}

Q: "Somerville commute cap 30 minutes, homes below 900k."
A: {{"commute_intent":{{"commute_destination_town":"Somerville","commute_context":"destination_town","max_commute_minutes":30}},"ops":[{{"op":"rank","preferences":{{"max_commute_minutes":30,"budget_max":900000}},"limit":10}}]}}

Q: "Newton 30 minute commute max, safer towns only."
A: {{"commute_intent":{{"commute_destination_town":"Newton","commute_context":"destination_town","max_commute_minutes":30}},"ops":[{{"op":"rank","preferences":{{"max_commute_minutes":30,"safety_priority":"high"}},"limit":10}}]}}

Q: "Compare Lexington and Bedford on schools, safety, and price."
A: {{"commute_intent":{{"commute_context":"default_boston","compare_towns":["Lexington","Bedford"]}},"ops":[{{"op":"compare","towns":["Lexington","Bedford"],"columns":["school_score","safety_score","price"]}}]}}

Q: "Commute anchor Bedford; max 35 min; prefer coastal towns."
A: {{"commute_intent":{{"commute_destination_town":"Bedford","commute_context":"destination_town","max_commute_minutes":35}},"ops":[{{"op":"rank","preferences":{{"max_commute_minutes":35,"requires_coastal":true}},"limit":10}}]}}

Q: "Peabody hub, 33 minute commute max, family-friendly towns around 800k."
A: {{"commute_intent":{{"commute_destination_town":"Peabody","commute_context":"destination_town","max_commute_minutes":33}},"ops":[{{"op":"rank","preferences":{{"max_commute_minutes":33,"budget_max":800000,"school_priority":"high"}},"limit":10}}]}}

Q: "Just accepted an offer in Needham — suburbs with strong schools, budget 1.1M."
A: {{"commute_intent":{{"commute_destination_town":"Needham","commute_context":"destination_town"}},"ops":[{{"op":"rank","preferences":{{"budget_max":1100000,"school_priority":"high"}},"limit":10}}]}}

Q: "Starting at a company in Burlington next month — towns under 900k, 30 min max."
A: {{"commute_intent":{{"commute_destination_town":"Burlington","commute_context":"destination_town","max_commute_minutes":30}},"ops":[{{"op":"rank","preferences":{{"budget_max":900000,"max_commute_minutes":30}},"limit":10}}]}}

Q: "Is Manchestr-by-the-Sea coastal?"
A: {{"ops":[{{"op":"lookup","items":[{{"town":"Manchester-by-the-Sea","field":"coastal"}}]}}]}}

Q: "Is Wilmington a partial-data town?"
A: {{"ops":[{{"op":"lookup","items":[{{"town":"Wilmington","field":"tier"}}]}}]}}

Q: "Would Lexingtn resolve correctly?"
A: {{"ops":[{{"op":"membership","town":"Lexington"}}]}}

Q: "Feels like Concord — coastal preferred."
A: {{"ops":[{{"op":"semantic_search","query_text":"towns like Concord coastal feel","top_k":10}},{{"op":"rank","preferences":{{"requires_coastal":true}},"limit":10,"use_semantic_candidates":true}}]}}

Q: "Ignore school quality and focus on price."
A: {{"ops":[{{"op":"rank","preferences":{{"deprioritize_schools":true,"affordability_priority":"high","school_priority":"low"}},"limit":10}}]}}

Q: "We're fine with weaker schools if commute to Burlington is under 25 min."
A: {{"commute_intent":{{"commute_destination_town":"Burlington","commute_context":"destination_town","max_commute_minutes":25}},"ops":[{{"op":"rank","preferences":{{"deprioritize_schools":true,"max_commute_minutes":25}},"limit":10}}]}}

Rules for preferences:
- max_commute_minutes is drive TIME in minutes (never dollars). Put it in rank preferences AND commute_intent.max_commute_minutes when user states a cap.
- budget_max is home price in dollars (e.g. 850000 for 850k). Never set budget_max=30000 for "under 30 minutes" or "drive under 30".
- Plain compare with no workplace/commute mention → commute_intent.commute_context="default_boston" only (no commute_destination_town).
- Multi-field compare ("on schools, safety, and price") → op "compare" with columns, NOT lookup.
- Shorthand "under 30" after drive/commute/minutes → max_commute_minutes:30; "under 850k" → budget_max:850000 — both can appear in the same rank preferences.
- Workplace phrasing ("job/office/work in X", "commute anchor X", "X hub", "accepted an offer in X", "starting at a company in X") → set commute_intent.commute_destination_town to that dataset town and commute_context="destination_town" (NOT default_boston).
- Typo town names: still choose the correct op (lookup for facts, membership only for scope/resolve/accepted, compare for X vs Y).
- "Feels like" / "similar to" / vibe language → semantic_search + rank with use_semantic_candidates=true.
- "Ignore schools" / "weaker schools" / "focus on price" → rank with deprioritize_schools=true, never unsupported.
"""


def _extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped, re.I)
    if fence:
        stripped = fence.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object in LLM planner response")
    return json.loads(stripped[start : end + 1])


def plan_from_llm_response(text: str) -> QueryPlan:
    """Parse and validate planner model output (for tests and repair loop)."""
    raw = _extract_json_object(text)
    return validate_plan(raw)


def _build_user_message(
    query: str,
    entities: ExtractedEntities,
    *,
    repair_error: str | None = None,
    previous_json: dict[str, Any] | None = None,
    session_context: dict[str, Any] | None = None,
) -> str:
    ctx: dict[str, Any] = {
        "user_query": query,
        "valid_towns": entities.valid_towns,
        "unknown_town_candidates": entities.unknown_town_candidates,
        "compare_pair": list(entities.compare_pair) if entities.compare_pair else None,
    }
    if session_context:
        ctx["session_context"] = session_context
    parts = ["Build a QueryPlan for this suburb query.\n", json.dumps(ctx, indent=2)]
    if repair_error:
        parts.append(
            f"\n\nPREVIOUS PLAN INVALID:\n{repair_error}\n"
            f"Previous JSON:\n{json.dumps(previous_json or {}, indent=2)}\n"
            "Return corrected JSON only."
        )
    else:
        parts.append("\n\nReturn QueryPlan JSON only.")
    return "".join(parts)


async def _call_planner_llm(user_message: str) -> str:
    from agent_framework import Agent

    from app.chat_client import get_chat_client
    from app.real_estate_agent import response_text

    agent = Agent(
        client=get_chat_client(),
        name="SuburbScoutQueryPlanner",
        instructions=PLANNER_SYSTEM_INSTRUCTIONS,
        tools=[],
    )
    response = await agent.run(user_message)
    return response_text(response)


async def plan_query_with_llm(
    query: str,
    *,
    entities: ExtractedEntities | None = None,
    max_repair_attempts: int | None = None,
    apply_normalizer: bool = True,
    session_context: dict[str, Any] | None = None,
) -> QueryPlan:
    """
    Use the chat model to produce a validated QueryPlan.

    Raises:
        ValueError: planner unavailable or LLM returned unusable output
        PlanValidationError: validation failed after repair attempts
    """
    if not planner_available():
        raise ValueError(
            "LLM query planner is not configured (set AZURE_OPENAI_API_KEY and "
            "AZURE_OPENAI_DEPLOYMENT_NAME, and USE_LLM_QUERY_PLANNER=true)."
        )

    text = query.strip()
    if not text:
        raise PlanValidationError("Empty query cannot be planned.")

    entities = entities or extract_entities(text)
    repairs = (
        max_repair_attempts
        if max_repair_attempts is not None
        else config.LLM_QUERY_PLANNER_MAX_REPAIR_ATTEMPTS
    )

    repair_error: str | None = None
    previous: dict[str, Any] | None = None
    last_exc: Exception | None = None

    raw_text = ""
    for attempt in range(repairs + 1):
        user_msg = _build_user_message(
            text,
            entities,
            repair_error=repair_error,
            previous_json=previous,
            session_context=session_context,
        )
        try:
            raw_text = await _call_planner_llm(user_msg)
            plan = plan_from_llm_response(raw_text)
            validate_planner_plan_semantics(plan, text)
            if apply_normalizer:
                from app.plan_normalizer import normalize_planned_query

                plan = normalize_planned_query(text, plan)
            logger.info(
                "LLM query plan (%d ops, attempt %d): %s",
                len(plan.ops),
                attempt + 1,
                [getattr(o, "op", type(o).__name__) for o in plan.ops],
            )
            return plan
        except (PlanValidationError, ValidationError, ValueError, json.JSONDecodeError) as exc:
            last_exc = exc
            repair_error = str(exc)
            try:
                previous = _extract_json_object(raw_text) if raw_text else {}
            except Exception:
                previous = {"raw": (raw_text or "")[:500]}
            logger.warning("Planner attempt %d failed: %s", attempt + 1, exc)
            if attempt >= repairs:
                break

    from app.plan_fallback import plan_with_rule_fallback

    fallback = plan_with_rule_fallback(
        text,
        entities=entities,
        apply_normalizer=apply_normalizer,
    )
    if fallback is not None:
        logger.info(
            "Rule fallback plan (%d ops): %s",
            len(fallback.ops),
            [getattr(o, "op", type(o).__name__) for o in fallback.ops],
        )
        return fallback

    raise PlanValidationError(
        f"Could not produce a valid QueryPlan after {repairs + 1} attempt(s): {last_exc}"
    ) from last_exc


def planner_available() -> bool:
    return bool(
        config.USE_LLM_QUERY_PLANNER
        and config.AZURE_OPENAI_API_KEY
        and config.CHAT_MODEL_DEPLOYMENT
    )
