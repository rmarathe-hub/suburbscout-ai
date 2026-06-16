"""Foundry Hosted Agent entrypoint — Responses protocol on port 8088.

Uses the same planner-first pipeline as FastAPI ``/api/query`` (``handle_query_v2``).

Run locally (after az login + .env with Azure credentials):
  python -m app.hosted_main

Test:
  curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \\
    -d '{"input": "Keep me below 30 minutes to Somerville and under 850k.", "stream": false}'
"""

from __future__ import annotations

import logging
import os

from agent_framework_foundry_hosting import ResponsesHostServer
from dotenv import load_dotenv

from app.config import SERVICE_ROOT
from app.hosted_query_agent import QueryPipelineHostedAgent
from app.query_agent import query_agent_available

logger = logging.getLogger(__name__)


def _bootstrap_env() -> None:
    """Align Foundry container env vars with local config expectations."""
    load_dotenv(SERVICE_ROOT / ".env")

    if not os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "").strip():
        model = (
            os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")
            or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
            or ""
        ).strip()
        if model:
            os.environ["AZURE_OPENAI_DEPLOYMENT_NAME"] = model

    os.environ.setdefault("USE_LLM_QUERY_AGENT", "true")
    os.environ.setdefault("USE_LLM_QUERY_PLANNER", "true")
    os.environ.setdefault("USE_LLM_ANSWER", "true")

    # Reload config module values after env bootstrap.
    from app import config

    config.CHAT_MODEL_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "")
    config.AZURE_OPENAI_DEPLOYMENT_NAME = config.CHAT_MODEL_DEPLOYMENT


def create_hosted_agent() -> QueryPipelineHostedAgent:
    """SuburbScout hosted agent — full query pipeline (not legacy tool-calling)."""
    if not query_agent_available():
        logger.warning(
            "Query agent not fully configured (Azure OpenAI + USE_LLM_QUERY_AGENT). "
            "Hosted /responses will return a configuration error until env is set."
        )
    return QueryPipelineHostedAgent()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    _bootstrap_env()
    server = ResponsesHostServer(create_hosted_agent())
    logger.info(
        "SuburbScout query pipeline hosted agent listening on port 8088 (/responses)"
    )
    server.run()


if __name__ == "__main__":
    main()
