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

from agent_framework_foundry_hosting import ResponsesHostServer

from app.hosted_env import bootstrap_hosted_env, query_agent_config_status
from app.hosted_query_agent import QueryPipelineHostedAgent

logger = logging.getLogger(__name__)


def create_hosted_agent() -> QueryPipelineHostedAgent:
    """SuburbScout hosted agent — full query pipeline (not legacy tool-calling)."""
    status = query_agent_config_status()
    if not status["query_agent_available"]:
        logger.warning(
            "Query agent not fully configured for hosted /responses: %s",
            {k: v for k, v in status.items() if k != "query_agent_available"},
        )
    else:
        logger.info("Query agent configured for hosted pipeline")
    return QueryPipelineHostedAgent()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    env_status = bootstrap_hosted_env()
    logger.info("Hosted env bootstrap: %s", env_status)
    server = ResponsesHostServer(create_hosted_agent())
    logger.info(
        "SuburbScout query pipeline hosted agent listening on port 8088 (/responses)"
    )
    server.run()


if __name__ == "__main__":
    main()
