"""Bootstrap env + config for Foundry Hosted Agent container."""

from __future__ import annotations

import logging
import os
from typing import Any

from app.config import SERVICE_ROOT

logger = logging.getLogger(__name__)

# Passed through at deploy time (phase6) when set in deployer environment — never hardcoded.
# Do NOT include FOUNDRY_* or AGENT_* — Azure injects those at runtime (create_version rejects them).
HOSTED_DEPLOY_ENV_KEYS: tuple[str, ...] = (
    "USE_LLM_QUERY_AGENT",
    "USE_LLM_QUERY_PLANNER",
    "USE_LLM_ANSWER",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "DATABASE_URL",
    "GOOGLE_MAPS_API_KEY",
    "COMMUTE_DESTINATION",
)

# Reserved by Foundry hosted-agent platform — must not appear in container env on create_version.
_RESERVED_CONTAINER_ENV_PREFIXES: tuple[str, ...] = ("FOUNDRY_", "AGENT_")

_TRUTHY = frozenset({"1", "true", "yes"})


def _truthy(name: str, default: str = "true") -> bool:
    return os.getenv(name, default).strip().lower() in _TRUTHY


def bootstrap_hosted_env(*, load_dotenv_file: bool = True) -> dict[str, Any]:
    """
    Align Foundry container env with local query-agent config expectations.

    Returns a small status dict for logging (no secrets).
    """
    if load_dotenv_file:
        from dotenv import load_dotenv

        load_dotenv(SERVICE_ROOT / ".env")

    model = (
        os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "").strip()
        or os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "").strip()
    )
    if model:
        os.environ.setdefault("AZURE_OPENAI_DEPLOYMENT_NAME", model)
        os.environ.setdefault("AZURE_AI_MODEL_DEPLOYMENT_NAME", model)

    os.environ.setdefault("USE_LLM_QUERY_AGENT", "true")
    os.environ.setdefault("USE_LLM_QUERY_PLANNER", "true")
    os.environ.setdefault("USE_LLM_ANSWER", "true")

    from app import config

    config.CHAT_MODEL_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "").strip()
    config.AZURE_OPENAI_DEPLOYMENT_NAME = config.CHAT_MODEL_DEPLOYMENT
    config.AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    config.AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
    config.FOUNDRY_PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").rstrip("/")
    config.DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or None
    config.USE_LLM_QUERY_AGENT = _truthy("USE_LLM_QUERY_AGENT")
    config.USE_LLM_QUERY_PLANNER = _truthy("USE_LLM_QUERY_PLANNER")
    config.USE_LLM_ANSWER = _truthy("USE_LLM_ANSWER")

    return {
        "deployment_set": bool(config.CHAT_MODEL_DEPLOYMENT),
        "api_key_set": bool(config.AZURE_OPENAI_API_KEY),
        "endpoint_set": bool(config.AZURE_OPENAI_ENDPOINT),
        "foundry_endpoint_set": bool(config.FOUNDRY_PROJECT_ENDPOINT),
        "database_set": bool(config.DATABASE_URL),
        "use_llm_query_agent": config.USE_LLM_QUERY_AGENT,
    }


def build_phase6_container_env_vars() -> dict[str, str]:
    """Env vars to inject into Foundry hosted agent version (from deployer shell / .env)."""
    model = (
        os.getenv("AZURE_AI_MODEL_DEPLOYMENT_NAME", "").strip()
        or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "").strip()
    )
    if not model:
        return {}

    env_vars: dict[str, str] = {
        "AZURE_AI_MODEL_DEPLOYMENT_NAME": model,
        "AZURE_OPENAI_DEPLOYMENT_NAME": model,
        "USE_LLM_QUERY_AGENT": os.getenv("USE_LLM_QUERY_AGENT", "true"),
        "USE_LLM_QUERY_PLANNER": os.getenv("USE_LLM_QUERY_PLANNER", "true"),
        "USE_LLM_ANSWER": os.getenv("USE_LLM_ANSWER", "true"),
    }
    for key in HOSTED_DEPLOY_ENV_KEYS:
        if key in env_vars:
            continue
        if key.startswith(_RESERVED_CONTAINER_ENV_PREFIXES):
            continue
        val = os.getenv(key, "").strip()
        if val:
            env_vars[key] = val
    return env_vars


def query_agent_config_status() -> dict[str, bool]:
    from app.query_agent import query_agent_available

    from app import config

    return {
        "query_agent_available": query_agent_available(),
        "use_llm_query_agent": config.USE_LLM_QUERY_AGENT,
        "use_llm_query_planner": config.USE_LLM_QUERY_PLANNER,
        "deployment_set": bool(config.CHAT_MODEL_DEPLOYMENT),
        "api_key_set": bool(config.AZURE_OPENAI_API_KEY),
    }
