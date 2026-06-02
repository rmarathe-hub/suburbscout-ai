"""Chat client factory: Foundry-first, Azure OpenAI fallback."""

from __future__ import annotations

import logging
from typing import Literal

from agent_framework import FunctionInvocationConfiguration
from agent_framework.foundry import FoundryChatClient
from agent_framework.openai import OpenAIChatClient
from azure.core.credentials import AzureKeyCredential

from app import config

logger = logging.getLogger(__name__)

ClientKind = Literal["foundry", "openai_fallback"]

_active_client_kind: ClientKind | None = None

FUNCTION_INVOCATION_CONFIGURATION: FunctionInvocationConfiguration = {
    "include_detailed_errors": True,
}


def get_active_client_kind() -> ClientKind | None:
    """Which client factory succeeded last (set by get_chat_client)."""
    return _active_client_kind


def create_foundry_chat_client() -> FoundryChatClient:
    """Build FoundryChatClient from FOUNDRY_PROJECT_ENDPOINT and deployment name."""
    if not config.FOUNDRY_PROJECT_ENDPOINT:
        raise ValueError("FOUNDRY_PROJECT_ENDPOINT is not set in .env")
    if not config.CHAT_MODEL_DEPLOYMENT:
        raise ValueError("AZURE_OPENAI_DEPLOYMENT_NAME is not set in .env")
    if not config.AZURE_OPENAI_API_KEY:
        raise ValueError("AZURE_OPENAI_API_KEY is required for Foundry local auth")

    api_key = config.AZURE_OPENAI_API_KEY
    credential = AzureKeyCredential(api_key)
    client = FoundryChatClient(
        project_endpoint=config.FOUNDRY_PROJECT_ENDPOINT,
        model=config.CHAT_MODEL_DEPLOYMENT,
        credential=credential,
        function_invocation_configuration=FUNCTION_INVOCATION_CONFIGURATION,
    )
    # Project client's default OpenAI client expects Entra ID; patch in API-key auth for local dev.
    client.client = client.project_client.get_openai_client(api_key=api_key)
    return client


def create_openai_fallback_chat_client() -> OpenAIChatClient:
    """Build OpenAIChatClient pointed at Azure OpenAI (resource base URL, no /openai/v1)."""
    if not config.AZURE_OPENAI_ENDPOINT:
        raise ValueError("AZURE_OPENAI_ENDPOINT is not set in .env")
    if not config.AZURE_OPENAI_API_KEY:
        raise ValueError("AZURE_OPENAI_API_KEY is not set in .env")
    if not config.CHAT_MODEL_DEPLOYMENT:
        raise ValueError("AZURE_OPENAI_DEPLOYMENT_NAME is not set in .env")

    # Agent Framework Responses API requires Azure "preview" API version (not chat completions dates).
    return OpenAIChatClient(
        model=config.CHAT_MODEL_DEPLOYMENT,
        azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
        api_key=config.AZURE_OPENAI_API_KEY,
        api_version="preview",
        function_invocation_configuration=FUNCTION_INVOCATION_CONFIGURATION,
    )


def get_chat_client() -> FoundryChatClient | OpenAIChatClient:
    """Return Foundry client when possible; otherwise Azure OpenAI fallback."""
    global _active_client_kind

    try:
        client = create_foundry_chat_client()
        _active_client_kind = "foundry"
        logger.info("Using FoundryChatClient (project_endpoint=%s)", config.FOUNDRY_PROJECT_ENDPOINT)
        return client
    except Exception as exc:
        logger.warning("FoundryChatClient unavailable (%s); using OpenAIChatClient fallback", exc)

    client = create_openai_fallback_chat_client()
    _active_client_kind = "openai_fallback"
    logger.info("Using OpenAIChatClient fallback (azure_endpoint=%s)", config.AZURE_OPENAI_ENDPOINT)
    return client
