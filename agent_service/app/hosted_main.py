"""Foundry Hosted Agent entrypoint — Responses protocol on port 8088.

Run locally (after az login + .env with FOUNDRY_PROJECT_ENDPOINT):
  python -m app.hosted_main

Test:
  curl -sS -H "Content-Type: application/json" -X POST http://localhost:8088/responses \\
    -d '{"input": "What is the commute from Maynard?", "stream": false}'
"""

from __future__ import annotations

import logging
import os

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from app.chat_client import FUNCTION_INVOCATION_CONFIGURATION
from app.config import AGENT_NAME, SERVICE_ROOT
from app.real_estate_agent import _build_instructions
from app.tools import AGENT_TOOLS

logger = logging.getLogger(__name__)


def _model_deployment() -> str:
    return (
        os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME")
        or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        or ""
    ).strip()


def create_hosted_agent() -> Agent:
    """SuburbScout agent for Foundry Hosted Agent (Entra auth at runtime)."""
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT", "").strip()
    if not endpoint:
        raise ValueError("FOUNDRY_PROJECT_ENDPOINT is required (platform-injected in production)")

    model = _model_deployment()
    if not model:
        raise ValueError(
            "Set AZURE_AI_MODEL_DEPLOYMENT_NAME or AZURE_OPENAI_DEPLOYMENT_NAME "
            "to your Foundry chat deployment name"
        )

    client = FoundryChatClient(
        project_endpoint=endpoint,
        model=model,
        credential=DefaultAzureCredential(),
        function_invocation_configuration=FUNCTION_INVOCATION_CONFIGURATION,
    )

    return Agent(
        client=client,
        name=AGENT_NAME,
        instructions=_build_instructions(save_searches=True),
        tools=AGENT_TOOLS,
        default_options={"store": False},
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    load_dotenv(SERVICE_ROOT / ".env")
    server = ResponsesHostServer(create_hosted_agent())
    logger.info("SuburbScout hosted agent listening on port 8088 (/responses)")
    server.run()


if __name__ == "__main__":
    main()
