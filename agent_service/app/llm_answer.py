"""Phase 5 — grounded natural-language answers from execution results only.

Behavior contract: app.llm_contract (answer LLM must not invent facts).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from app import config
from app.plan_executor import ExecutionResult, ExecutionStatus
from app.tools import SCORE_DISCLAIMER

logger = logging.getLogger(__name__)

ANSWER_STATUSES = frozenset({ExecutionStatus.OK, ExecutionStatus.PARTIAL})

ANSWER_SYSTEM_INSTRUCTIONS = f"""You are SuburbScout's answer writer for Boston-area MA suburb questions.

You receive:
1) the user's original question
2) execution_results — JSON from suburbs.json and/or semantic search (the ONLY source of facts)

Rules (strict):
- Use ONLY numbers, town names, and attributes present in execution_results.
- If execution_status is "partial", answer with available fields and explicitly state what is missing in the dataset.
- Never invent prices, commute times, scores, crime rates, school ratings, or town names.
- Never claim live Zillow/MLS data or neighborhood-level detail unless present in execution_results.
- For semantic_search results: describe matches as "semantic profile match" from stored town profiles only.
  Do NOT infer demographics, diversity, walkability, nightlife, or lifestyle traits unless those exact fields appear in execution_results.
- For membership op: give a direct yes/no about dataset inclusion using snippets in execution_results.
- Do not mention internal JSON keys or "execution_results".
- End with this disclaimer on its own line: {SCORE_DISCLAIMER}

Write a clear, helpful paragraph (or short bullet list for comparisons). No markdown code fences.
"""


class AnswerValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def should_use_answer_llm(result: ExecutionResult) -> bool:
    """Only narrate when we have some grounded execution payload."""
    if not config.USE_LLM_ANSWER:
        return False
    return result.status in ANSWER_STATUSES


def answer_llm_available() -> bool:
    return bool(
        config.USE_LLM_ANSWER
        and config.AZURE_OPENAI_API_KEY
        and config.CHAT_MODEL_DEPLOYMENT
    )


def _walk_collect_facts(obj: Any, prices: set[int], towns: set[str], floats: set[float]) -> None:
    if isinstance(obj, dict):
        name = obj.get("name") or obj.get("town")
        if isinstance(name, str) and name.strip():
            towns.add(name.strip().lower())
        for key, value in obj.items():
            if key == "latest_home_price" and value is not None:
                try:
                    prices.add(int(float(value)))
                except (TypeError, ValueError):
                    pass
            elif key in ("drive_minutes_to_boston", "drive_minutes_to_destination", "school_score", "safety_score", "crime_rate_per_1000"):
                if value is not None:
                    try:
                        floats.add(round(float(value), 2))
                    except (TypeError, ValueError):
                        pass
            else:
                _walk_collect_facts(value, prices, towns, floats)
    elif isinstance(obj, list):
        for item in obj:
            _walk_collect_facts(item, prices, towns, floats)


def collect_allowed_facts(answer_context: dict[str, Any]) -> tuple[set[int], set[str], set[float]]:
    prices: set[int] = set()
    towns: set[str] = set()
    floats: set[float] = set()
    _walk_collect_facts(answer_context, prices, towns, floats)
    return prices, towns, floats


def _parse_dollar_amounts(text: str) -> list[int]:
    amounts: list[int] = []
    for match in re.finditer(r"\$\s*([\d,]+(?:\.\d+)?)", text):
        raw = match.group(1).replace(",", "")
        try:
            amounts.append(int(float(raw)))
        except ValueError:
            continue
    return amounts


def _parse_numeric_tokens(text: str) -> list[float]:
    """Loose numeric tokens that might be scores or commute minutes."""
    tokens: list[float] = []
    for match in re.finditer(r"(?<!\w)(\d+(?:\.\d+)?)(?!\w)", text):
        try:
            tokens.append(round(float(match.group(1)), 2))
        except ValueError:
            continue
    return tokens


def validate_answer_against_context(
    answer: str,
    execution: ExecutionResult,
) -> AnswerValidationResult:
    """Reject answers that cite prices not present in execution_results."""
    if not config.USE_LLM_ANSWER_VALIDATOR:
        return AnswerValidationResult(valid=True, warnings=["Answer validator disabled."])

    ctx = execution.answer_context
    prices, towns, floats = collect_allowed_facts(ctx)
    errors: list[str] = []
    warnings: list[str] = []

    for amount in _parse_dollar_amounts(answer):
        if prices and amount not in prices:
            # Allow rounded thousands e.g. $1525k vs 1525000 — within 2% tolerance
            if not any(abs(amount - p) <= max(5000, int(p * 0.02)) for p in prices):
                errors.append(f"Answer cites price ${amount:,} not in execution results.")

    # Soft check: notable floats (scores, minutes) should appear in context if clearly stated
    for token in _parse_numeric_tokens(answer):
        if token in floats:
            continue
        if token > 50_000:
            continue
        if 0 <= token <= 10 and floats:
            # might be a score — warn only
            if not any(abs(token - f) < 0.15 for f in floats):
                warnings.append(f"Answer mentions {token} which may not match dataset floats.")

    return AnswerValidationResult(valid=not errors, errors=errors, warnings=warnings)


def template_answer_from_execution(execution: ExecutionResult) -> str:
    """Deterministic fallback using snippets and tables from execution (no LLM)."""
    parts: list[str] = []
    ctx = execution.answer_context

    for op in ctx.get("ops") or []:
        for snippet in op.get("snippets") or []:
            if snippet:
                parts.append(str(snippet))
        if op.get("op") == "compare":
            table = op.get("comparison_table") or []
            if table:
                cols = op.get("columns") or []
                header = " | ".join(c.get("label", c.get("key", "")) for c in cols)
                if header:
                    parts.append(f"Comparison ({header}):")
                for row in table:
                    town = row.get("town", "?")
                    bits = [str(town)]
                    for col in cols:
                        key = col.get("key")
                        if key and key in row:
                            bits.append(f"{col.get('label', key)}: {row[key]}")
                    parts.append("; ".join(bits))
        if op.get("op") == "rank":
            matches = op.get("top_matches") or []
            if matches and matches[0].get("name"):
                parts.append("Top matches from dataset ranking:")
                for row in matches[:5]:
                    if row.get("no_matches"):
                        continue
                    name = row.get("name")
                    score = row.get("score")
                    reasons = row.get("reasons") or []
                    line = f"{name} (score {score}/10)"
                    if reasons:
                        line += f" — {reasons[0]}"
                    parts.append(line)
        if op.get("op") == "semantic_search":
            names = op.get("candidate_town_names") or []
            if names:
                parts.append(
                    "Semantic candidates (not final ranking): "
                    + ", ".join(names[:8])
                    + "."
                )

    if parts:
        return " ".join(parts) + f" {SCORE_DISCLAIMER}"

    return execution.refusal_message()


def _build_answer_user_message(query: str, execution: ExecutionResult) -> str:
    payload = {
        "user_question": query,
        "execution_status": execution.status.value,
        "message_code": execution.message_code,
        "execution_results": execution.answer_context,
    }
    return (
        "Write the user-facing answer.\n\n"
        f"{json.dumps(payload, indent=2)}"
    )


async def _call_answer_llm(user_message: str) -> str:
    from agent_framework import Agent

    from app.chat_client import get_chat_client
    from app.real_estate_agent import response_text

    agent = Agent(
        client=get_chat_client(),
        name="SuburbScoutAnswerWriter",
        instructions=ANSWER_SYSTEM_INSTRUCTIONS,
        tools=[],
    )
    response = await agent.run(user_message)
    return response_text(response).strip()


async def generate_answer_with_llm(
    query: str,
    execution: ExecutionResult,
) -> tuple[str, AnswerValidationResult]:
    """
    Produce a natural-language answer from execution_results.

    Falls back to template_answer_from_execution if LLM unavailable or validation fails.
    """
    if execution.status not in ANSWER_STATUSES:
        return execution.refusal_message(), AnswerValidationResult(valid=True)

    if not answer_llm_available():
        text = template_answer_from_execution(execution)
        return text, AnswerValidationResult(valid=True, warnings=["Answer LLM not configured; used template."])

    try:
        user_msg = _build_answer_user_message(query, execution)
        answer = await _call_answer_llm(user_msg)
        validation = validate_answer_against_context(answer, execution)
        if validation.valid:
            return answer, validation
        logger.warning("Answer validation failed: %s", validation.errors)
        fallback = template_answer_from_execution(execution)
        return fallback, AnswerValidationResult(
            valid=False,
            errors=validation.errors,
            warnings=[*validation.warnings, "Fell back to template answer after validation failure."],
        )
    except Exception as exc:
        logger.warning("Answer LLM failed: %s", exc)
        fallback = template_answer_from_execution(execution)
        return fallback, AnswerValidationResult(
            valid=False,
            errors=[str(exc)],
            warnings=["Fell back to template answer after LLM error."],
        )
