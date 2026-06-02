"""Phase 2 — Azure NL behavior contract for the query-agent path.

Single source of truth for what LLMs may vs must not do. Referenced in docs,
verification scripts, and (by convention) planner/answer system prompts.
"""

from __future__ import annotations

# --- Roles in the pipeline ---------------------------------------------------

PIPELINE_STAGES = (
    "1. LLM planner (Azure chat) → QueryPlan JSON only",
    "2. Python normalizer + trust gates → validated plan",
    "3. plan_executor → suburbs.json + local vector index (deterministic)",
    "4. Optional LLM answer → prose from execution_results only",
)

DATA_SOURCE_OF_TRUTH = "app/data/suburbs.json (200 MA towns) + ranking.py + commute cache"

# --- LLM may -----------------------------------------------------------------

LLM_MAY: tuple[str, ...] = (
    "Convert natural language into a validated QueryPlan (ops: lookup, compare, rank, "
    "membership, semantic_search, unsupported).",
    "Paraphrase user intent and choose ops/fields supported by the plan schema.",
    "Write a final natural-language answer using only execution_results JSON.",
    "Refuse or explain limitations when trust gates block execution or data is missing.",
    "Call Azure embeddings for semantic_search candidate narrowing (profiles in vector index).",
)

# --- LLM must not -------------------------------------------------------------

LLM_MUST_NOT: tuple[str, ...] = (
    "Invent town names, home prices, commute times, school/safety scores, or crime rates.",
    "Return ranked town lists without a rank op executed on suburbs.json.",
    "Claim live Zillow/MLS, neighborhood-level, MBTA/transit, or demographic facts.",
    "Substitute a different town when lookup fails (no silent substitution).",
    "Output planner prose or markdown instead of QueryPlan JSON.",
    "Bypass trust gates or normalizer by answering from general world knowledge.",
)

# --- Azure services used ------------------------------------------------------

AZURE_SERVICES: tuple[tuple[str, str], ...] = (
    ("Chat (planner + answer)", "AZURE_OPENAI_DEPLOYMENT_NAME + AZURE_OPENAI_ENDPOINT + API key"),
    ("Embeddings (semantic search)", "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME"),
    ("Optional Foundry project", "FOUNDRY_PROJECT_ENDPOINT (chat_client tries Foundry first)"),
)

REQUIRED_ENV_FOR_LIVE_QUERY_AGENT: tuple[tuple[str, str], ...] = (
    ("AZURE_OPENAI_API_KEY", "Auth for chat + embeddings"),
    ("AZURE_OPENAI_ENDPOINT", "Azure OpenAI resource base URL (no /openai/v1 suffix)"),
    ("AZURE_OPENAI_DEPLOYMENT_NAME", "Chat deployment for planner + answer LLM"),
    ("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", "Embedding deployment for semantic_search"),
    ("USE_LLM_QUERY_PLANNER", "true — NL → QueryPlan"),
    ("USE_LLM_QUERY_AGENT", "true — default production path"),
)


def format_contract_markdown() -> str:
    """Markdown block for README / docs."""
    lines = [
        "## Azure NL behavior contract",
        "",
        "**Pipeline:**",
        "",
    ]
    for stage in PIPELINE_STAGES:
        lines.append(f"- {stage}")
    lines.append("")
    lines.append(f"**Source of truth for facts:** `{DATA_SOURCE_OF_TRUTH}`")
    lines.append("")
    lines.append("### LLM may")
    lines.append("")
    for item in LLM_MAY:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### LLM must not")
    lines.append("")
    for item in LLM_MUST_NOT:
        lines.append(f"- {item}")
    lines.append("")
    lines.append("### Azure configuration")
    lines.append("")
    for name, vars_ in AZURE_SERVICES:
        lines.append(f"- **{name}:** `{vars_}`")
    return "\n".join(lines)
