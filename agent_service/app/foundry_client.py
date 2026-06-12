"""Foundry Hosted Agent client for Phase 7 FastAPI gateway."""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

import httpx

from app import config

logger = logging.getLogger(__name__)

_FOUNDRY_SCOPE = "https://ai.azure.com/.default"
_FOUNDRY_API_VERSION = "v1"
_FOUNDRY_PREVIEW_FEATURES = "HostedAgents=V1Preview"
_DEFAULT_TIMEOUT_S = float(
    __import__("os").getenv("FOUNDRY_REQUEST_TIMEOUT_S", "120")
)
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)


class FoundryAgentError(Exception):
    """Raised when the hosted agent call fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def build_responses_endpoint() -> str | None:
    """Return hosted agent OpenAI Responses URL, or None if not configured."""
    if config.FOUNDRY_AGENT_RESPONSES_ENDPOINT:
        return config.FOUNDRY_AGENT_RESPONSES_ENDPOINT.rstrip("/")

    base = (config.FOUNDRY_PROJECT_ENDPOINT or "").rstrip("/")
    name = (config.FOUNDRY_AGENT_NAME or "").strip()
    if not base or not name:
        return None

    # Version routing is handled by Foundry's active version selector on the agent.
    # FOUNDRY_AGENT_VERSION is metadata only (pinned /versions/{n}/ URLs 404 on v1 API).
    return f"{base}/agents/{name}/endpoint/protocols/openai/responses"


def _responses_request_url(endpoint: str) -> str:
    """Append api-version query param when not already present."""
    if "api-version=" in endpoint:
        return endpoint
    sep = "&" if "?" in endpoint else "?"
    return f"{endpoint}{sep}api-version={_FOUNDRY_API_VERSION}"


def foundry_agent_configured() -> bool:
    """True when required Foundry gateway settings are present."""
    return build_responses_endpoint() is not None


def _get_bearer_token() -> str:
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:
        raise FoundryAgentError(
            "unavailable",
            "azure-identity is not installed — pip install azure-identity",
        ) from exc

    try:
        credential = DefaultAzureCredential()
        token = credential.get_token(_FOUNDRY_SCOPE)
        return token.token
    except Exception as exc:
        logger.warning("Foundry auth failed", exc_info=True)
        raise FoundryAgentError(
            "auth",
            "Azure authentication failed for Foundry Hosted Agent",
        ) from exc


def _extract_output_text(raw: dict[str, Any]) -> str:
    """Pull assistant text from an OpenAI Responses API payload."""
    if isinstance(raw.get("output_text"), str) and raw["output_text"].strip():
        return raw["output_text"].strip()

    chunks: list[str] = []
    for item in raw.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") in ("output_text", "text") and part.get("text"):
                chunks.append(str(part["text"]))
    return "\n".join(chunks).strip()


def _parse_agent_json(text: str) -> dict[str, Any]:
    """Parse agent JSON from plain text or markdown fences."""
    cleaned = text.strip()
    fence = _JSON_FENCE_RE.match(cleaned)
    if fence:
        cleaned = fence.group(1).strip()
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError("agent output is not a JSON object")
    return data


def normalize_foundry_payload(
    data: dict[str, Any],
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Map hosted agent JSON into fields for QueryResponse."""
    answer = str(
        data.get("final_recommendation") or data.get("answer") or ""
    ).strip()
    rid = request_id or str(uuid.uuid4())

    return {
        "answer": answer,
        "execution_status": "ok" if answer else "partial",
        "request_id": rid,
        "top_matches": list(data.get("top_matches") or []),
        "comparison": data.get("comparison"),
        "tradeoff_warning": data.get("tradeoff_warning"),
        "score_disclaimer": data.get("score_disclaimer"),
        "source": "foundry_hosted_agent",
        "metadata": {
            "agent_name": config.FOUNDRY_AGENT_NAME,
            "agent_version": config.FOUNDRY_AGENT_VERSION,
            "backend_agent_mode": "foundry",
        },
        "used_answer_llm": True,
        "response": data,
    }


def normalize_foundry_http_response(
    raw: dict[str, Any],
    *,
    request_id: str | None = None,
) -> dict[str, Any]:
    """Parse Responses API HTTP JSON and normalize for QueryResponse."""
    rid = request_id or str(raw.get("id") or uuid.uuid4())

    if isinstance(raw.get("final_recommendation"), str) or isinstance(raw.get("answer"), str):
        return normalize_foundry_payload(raw, request_id=rid)

    text = _extract_output_text(raw)
    if not text:
        raise FoundryAgentError("malformed", "Hosted agent returned empty output")

    try:
        agent_data = _parse_agent_json(text)
    except json.JSONDecodeError:
        return {
            "answer": text,
            "execution_status": "ok",
            "request_id": rid,
            "top_matches": [],
            "comparison": None,
            "tradeoff_warning": None,
            "score_disclaimer": None,
            "source": "foundry_hosted_agent",
            "metadata": {
                "agent_name": config.FOUNDRY_AGENT_NAME,
                "agent_version": config.FOUNDRY_AGENT_VERSION,
                "backend_agent_mode": "foundry",
            },
            "used_answer_llm": True,
            "response": {"final_recommendation": text},
        }

    return normalize_foundry_payload(agent_data, request_id=rid)


async def call_foundry_agent(
    prompt: str,
    *,
    session_id: str | None = None,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """POST user prompt to Foundry Hosted Agent Responses endpoint."""
    endpoint = build_responses_endpoint()
    if not endpoint:
        raise FoundryAgentError(
            "bad_endpoint",
            "Foundry Hosted Agent is not configured "
            "(set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_AGENT_NAME)",
        )

    token = _get_bearer_token()
    body: dict[str, Any] = {"input": prompt, "stream": False}
    if session_id:
        body["metadata"] = {"session_id": session_id}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Foundry-Features": _FOUNDRY_PREVIEW_FEATURES,
    }
    request_url = _responses_request_url(endpoint)
    timeout = timeout_s if timeout_s is not None else _DEFAULT_TIMEOUT_S

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(request_url, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise FoundryAgentError("timeout", "Foundry Hosted Agent request timed out") from exc
    except httpx.RequestError as exc:
        logger.warning("Foundry HTTP request failed", exc_info=True)
        raise FoundryAgentError(
            "unavailable",
            "Could not reach Foundry Hosted Agent endpoint",
        ) from exc

    if resp.status_code in (401, 403):
        raise FoundryAgentError("auth", f"Foundry auth failed (HTTP {resp.status_code})")
    if resp.status_code == 404:
        raise FoundryAgentError(
            "bad_endpoint",
            f"Foundry agent endpoint not found — check FOUNDRY_AGENT_NAME/VERSION ({endpoint})",
        )
    if resp.status_code >= 400:
        detail = resp.text[:500]
        raise FoundryAgentError(
            "unavailable",
            f"Foundry Hosted Agent error HTTP {resp.status_code}: {detail}",
        )

    try:
        raw = resp.json()
    except json.JSONDecodeError as exc:
        raise FoundryAgentError(
            "malformed",
            "Foundry Hosted Agent returned non-JSON response",
        ) from exc

    if not isinstance(raw, dict):
        raise FoundryAgentError("malformed", "Foundry Hosted Agent returned unexpected payload")

    return normalize_foundry_http_response(raw)
