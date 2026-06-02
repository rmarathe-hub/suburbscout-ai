"""Microsoft Agent Framework real-estate recommendation agent."""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_framework import Agent

from app.chat_client import ClientKind, get_active_client_kind, get_chat_client
from app.config import AGENT_NAME
from app.tools import SCORE_DISCLAIMER

logger = logging.getLogger(__name__)

_SAVE_WORKFLOW = """- Always call save_search_tool as the final step for every user query (recommend, compare, or fuzzy)."""

_NO_SAVE_WORKFLOW = """- Do not call save_search_tool (interactive chat mode — no audit log for this turn)."""


def _build_instructions(*, save_searches: bool = True) -> str:
    save_suffix = " → save_search_tool" if save_searches else ""
    compare_end = " → save_search_tool" if save_searches else ""
    save_rule = _SAVE_WORKFLOW if save_searches else _NO_SAVE_WORKFLOW
    return f"""You are SuburbScout, a Massachusetts Boston-area suburb recommendation agent.

Data rules (strict):
- Only recommend or compare towns that exist in suburbs.json (200-town curated list).
- Never invent prices, scores, crime rates, commute times, school ratings, or town names.
- All numeric facts must come from tool outputs only.
- When data is missing, say so explicitly (check missing_fields and data_quality_tier).
- {SCORE_DISCLAIMER}
- Semantic search finds candidates only; final order always comes from rank_suburbs_tool.

Workflow:
- For structured recommendation requests (budget, schools, safety, commute numbers):
  parse_preferences_tool → rank_suburbs_tool → explain_results_tool{save_suffix}.
- For fuzzy / vibe requests (e.g. "coastal feel", "like Lexington but cheaper", "walkable"):
  semantic_town_search_tool first, then parse_preferences_tool, then rank_suburbs_tool with
  candidate_towns set to candidate_town_names from semantic search, then explain{save_suffix}.
- For compare requests (e.g. "compare X and Y"): compare_suburbs_tool{compare_end}.
- Do not rank or recommend towns without calling the tools.
- Never use similarity_score as the final recommendation score.
{save_rule}

Tool argument tips:
- rank_suburbs_tool: always pass user_prompt; pass candidate_towns when semantic search ran.
- explain_results_tool / save_search_tool: pass results or top_matches alias.

Response format:
Return a single JSON object (no markdown fences) with keys:
- query: string (echo user request)
- preferences: object from parse_preferences_tool (or null for compare-only)
- semantic_candidates: object from semantic_town_search_tool when used, else null
- top_matches: array from rank_suburbs_tool (empty array for compare-only)
- comparison: object from compare_suburbs_tool when applicable, else null
- tradeoff_warning: string or null from explain_results_tool
- final_recommendation: string from explain_results_tool or a brief compare summary
- score_disclaimer: always include the disclaimer text
"""


def create_agent(*, save_searches: bool = True) -> Agent:
    """Create the Phase 1 agent with core + semantic tools."""
    from app.tools import AGENT_TOOLS, INTERACTIVE_AGENT_TOOLS

    client = get_chat_client()
    tools = AGENT_TOOLS if save_searches else INTERACTIVE_AGENT_TOOLS
    return Agent(
        client=client,
        name=AGENT_NAME,
        instructions=_build_instructions(save_searches=save_searches),
        tools=tools,
    )


def response_text(response: Any) -> str:
    """Extract assistant text from an AgentResponse."""
    if hasattr(response, "text") and response.text:
        return str(response.text)
    if hasattr(response, "value") and response.value is not None:
        return str(response.value)
    return str(response)


AGENT_INSTRUCTIONS = _build_instructions(save_searches=True)


async def run_agent(
    prompt: str,
    *,
    agent: Agent | None = None,
    save_searches: bool = True,
    use_orchestrator: bool = False,
    use_query_agent: bool | None = None,
) -> dict[str, Any]:
    """Run a user prompt; query agent is default when USE_LLM_QUERY_AGENT=true (Phase 5)."""
    from app import config

    if use_query_agent is None:
        use_query_agent = config.USE_LLM_QUERY_AGENT

    if use_query_agent:
        from app.query_agent import handle_query_v2, query_agent_available

        if not query_agent_available():
            raise ValueError(
                "USE_LLM_QUERY_AGENT is enabled but planner is not configured "
                "(Azure OpenAI + USE_LLM_QUERY_PLANNER)."
            )
        orchestrated = await handle_query_v2(prompt, save_searches=save_searches)
        response = orchestrated["response"]
        text = json.dumps(response, indent=2)
        return {
            "text": text,
            "parsed": response,
            "client_kind": get_active_client_kind(),
            "orchestrated": True,
            "query_agent": True,
            "plan": orchestrated.get("plan"),
            "execution_status": orchestrated.get("execution_status"),
            "trust_gate": orchestrated.get("trust_gate"),
            "validation": response.get("validation"),
        }

    if use_orchestrator:
        from app.orchestrator import handle_query

        orchestrated = await handle_query(prompt, save_searches=save_searches)
        response = orchestrated["response"]
        if not orchestrated.get("used_llm_fallback"):
            text = json.dumps(response, indent=2)
            return {
                "text": text,
                "parsed": response,
                "client_kind": get_active_client_kind(),
                "orchestrated": True,
                "route": orchestrated.get("route"),
                "validation": response.get("validation"),
            }
        logger.info("Orchestrator deferred to LLM fallback for unsupported query.")

    active = agent or create_agent(save_searches=save_searches)
    response = await active.run(prompt)
    text = response_text(response)
    client_kind: ClientKind | None = get_active_client_kind()

    parsed: dict[str, Any] | None = None
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            parsed = None

    return {
        "text": text,
        "parsed": parsed,
        "client_kind": client_kind,
        "orchestrated": False,
    }
