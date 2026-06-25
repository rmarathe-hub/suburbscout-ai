"""Thin FastAPI gateway for the query agent (Phase 2 Step 6 + Phase 7 gateway).

Run from agent_service/:
  uvicorn app.api:app --reload --host 127.0.0.1 --port 8000

  curl -s http://127.0.0.1:8000/health | jq
  curl -s -X POST http://127.0.0.1:8000/api/query \\
    -H 'Content-Type: application/json' \\
    -d '{"prompt":"What is the commute from Maynard?"}' | jq
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.api_schemas import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
    SearchListResponse,
    SearchSummary,
    SessionResponse,
    WarmHealthResponse,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SuburbScout Query Agent",
    description="Natural language → QueryPlan → deterministic execution → grounded answer",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.FRONTEND_ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _suburbs_dataset_loaded() -> bool:
    from app.suburb_store import suburbs_dataset_available

    return suburbs_dataset_available()


def _database_status() -> str:
    from app.db import db_available, db_configured

    if not db_configured():
        return "not_configured"
    return "ok" if db_available() else "unavailable"


def payload_to_query_response(
    payload: dict[str, Any],
    *,
    debug: bool,
    source: str = "local_query_pipeline",
) -> QueryResponse:
    """Map handle_query_v2 payload to API response."""
    response = payload.get("response") or {}
    metadata = payload.get("metadata") or {
        "backend_agent_mode": config.BACKEND_AGENT_MODE,
    }
    return QueryResponse(
        answer=response.get("final_recommendation") or "",
        execution_status=str(payload.get("execution_status") or "unknown"),
        request_id=str(payload.get("request_id") or ""),
        latency_ms=payload.get("latency_ms"),
        message_code=payload.get("message_code"),
        trust_gate=payload.get("trust_gate"),
        trust_gate_blocks=payload.get("trust_gate_blocks"),
        used_answer_llm=bool(payload.get("used_answer_llm")),
        top_matches=list(response.get("top_matches") or [])[:10],
        plan=payload.get("plan") if debug else None,
        raw_llm_plan=payload.get("raw_llm_plan") if debug else None,
        response=response if debug else None,
        source=source,
        metadata=metadata,
        comparison=response.get("comparison"),
        tradeoff_warning=response.get("tradeoff_warning"),
        score_disclaimer=response.get("score_disclaimer"),
    )


def normalized_to_query_response(
    normalized: dict[str, Any],
    *,
    debug: bool,
) -> QueryResponse:
    """Map Foundry normalized dict to API response."""
    response = normalized.get("response") if debug else None
    return QueryResponse(
        answer=str(normalized.get("answer") or ""),
        execution_status=str(normalized.get("execution_status") or "unknown"),
        request_id=str(normalized.get("request_id") or ""),
        latency_ms=normalized.get("latency_ms"),
        message_code=normalized.get("message_code"),
        trust_gate=normalized.get("trust_gate"),
        trust_gate_blocks=normalized.get("trust_gate_blocks"),
        used_answer_llm=bool(normalized.get("used_answer_llm")),
        top_matches=list(normalized.get("top_matches") or [])[:10],
        comparison=normalized.get("comparison"),
        tradeoff_warning=normalized.get("tradeoff_warning"),
        score_disclaimer=normalized.get("score_disclaimer"),
        source=normalized.get("source") or "foundry_hosted_agent",
        metadata=normalized.get("metadata"),
        response=response,
        error=normalized.get("error"),
    )


def foundry_error_response(exc: Any) -> QueryResponse:
    """Clean client-facing error when Foundry gateway fails."""
    from app.foundry_client import FoundryAgentError

    message = (
        "The hosted agent is unavailable right now. Try again later or "
        "switch BACKEND_AGENT_MODE=local."
    )
    if isinstance(exc, FoundryAgentError):
        message = exc.message or message

    return QueryResponse(
        answer=message,
        execution_status="error",
        request_id=str(uuid.uuid4()),
        source="foundry_hosted_agent",
        metadata={
            "backend_agent_mode": "foundry",
            "foundry_error_code": getattr(exc, "code", "unknown"),
        },
        error="foundry_agent_error",
    )


async def _query_via_local(body: QueryRequest) -> QueryResponse:
    from app.query_agent import handle_query_v2, query_agent_available

    if not _suburbs_dataset_loaded():
        raise HTTPException(
            status_code=503,
            detail=(
                "Suburb dataset unavailable — run scripts/build_suburbs_dataset.py "
                "and scripts/seed_suburbs.py (or ensure suburbs.json is present)"
            ),
        )

    if not query_agent_available():
        raise HTTPException(
            status_code=503,
            detail=(
                "Query agent not configured. Set USE_LLM_QUERY_AGENT=true, "
                "USE_LLM_QUERY_PLANNER=true, and Azure OpenAI env vars in .env"
            ),
        )

    prompt = body.resolved_prompt()
    try:
        payload = await handle_query_v2(
            prompt,
            save_searches=body.save_audit,
            session_id=body.session_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("query agent failed")
        raise HTTPException(status_code=500, detail="query agent internal error") from exc

    out = payload_to_query_response(payload, debug=body.debug, source="local_query_pipeline")
    if out.metadata is None:
        out.metadata = {"backend_agent_mode": "local"}
    else:
        out.metadata.setdefault("backend_agent_mode", "local")
    return out


async def _query_via_foundry(body: QueryRequest) -> QueryResponse:
    from app.foundry_client import FoundryAgentError, call_foundry_agent, foundry_agent_configured
    from app.foundry_persistence import persist_foundry_turn

    if not foundry_agent_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Foundry Hosted Agent not configured. Set FOUNDRY_PROJECT_ENDPOINT, "
                "FOUNDRY_AGENT_NAME, and optionally FOUNDRY_AGENT_VERSION."
            ),
        )

    prompt = body.resolved_prompt()
    t0 = time.perf_counter()
    try:
        normalized = await call_foundry_agent(prompt, session_id=body.session_id)
    except FoundryAgentError as exc:
        raise exc

    latency_ms = int((time.perf_counter() - t0) * 1000)
    normalized["latency_ms"] = latency_ms
    persist_foundry_turn(
        prompt,
        normalized,
        session_id=body.session_id,
        save_audit=body.save_audit,
        latency_ms=latency_ms,
    )
    return normalized_to_query_response(normalized, debug=body.debug)


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    from app.foundry_client import build_responses_endpoint, foundry_agent_configured
    from app.query_agent import query_agent_available

    return HealthResponse(
        status="ok",
        query_agent_configured=query_agent_available(),
        suburbs_dataset_loaded=_suburbs_dataset_loaded(),
        database=_database_status(),
        backend_agent_mode=config.BACKEND_AGENT_MODE,
        foundry_agent_configured=foundry_agent_configured(),
        foundry_agent_endpoint=build_responses_endpoint(),
    )


@app.post("/health/warm", response_model=WarmHealthResponse)
async def warm_health() -> WarmHealthResponse:
    """Wake the Foundry hosted agent after ACA is up (reduces first-query cold start)."""
    if config.BACKEND_AGENT_MODE != "foundry":
        return WarmHealthResponse(status="skipped", warmed=False, message="local backend mode")

    from app.foundry_client import (
        FoundryAgentError,
        foundry_agent_configured,
        warm_foundry_agent,
    )

    if not foundry_agent_configured():
        return WarmHealthResponse(
            status="skipped",
            warmed=False,
            message="foundry hosted agent not configured",
        )

    t0 = time.perf_counter()
    try:
        await warm_foundry_agent()
        latency_ms = int((time.perf_counter() - t0) * 1000)
        return WarmHealthResponse(status="ok", warmed=True, latency_ms=latency_ms)
    except FoundryAgentError as exc:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.warning("Foundry warm-up failed: %s", exc.code)
        return WarmHealthResponse(
            status="error",
            warmed=False,
            latency_ms=latency_ms,
            message=exc.message,
        )


@app.post("/api/query", response_model=QueryResponse)
async def query_suburbs(body: QueryRequest) -> QueryResponse:
    """Run query via local pipeline or Foundry Hosted Agent (BACKEND_AGENT_MODE)."""
    from app.foundry_client import FoundryAgentError

    if config.BACKEND_AGENT_MODE == "foundry":
        try:
            return await _query_via_foundry(body)
        except FoundryAgentError as exc:
            logger.warning("Foundry gateway failed: %s", exc.code, exc_info=True)
            if config.FALLBACK_TO_LOCAL:
                return await _query_via_local(body)
            return foundry_error_response(exc)

    return await _query_via_local(body)


@app.get("/api/searches", response_model=SearchListResponse)
async def list_searches(limit: int = Query(default=20, ge=1, le=100)) -> SearchListResponse:
    """Return recent persisted searches (requires DATABASE_URL)."""
    from app.db import db_configured
    from app.repositories import SearchRepository

    if not db_configured():
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
    try:
        rows = SearchRepository().list_searches(limit=limit)
    except Exception as exc:
        logger.exception("list searches failed")
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    return SearchListResponse(searches=[SearchSummary(**row) for row in rows])


@app.get("/api/searches/{request_id}")
async def get_search(request_id: str) -> dict[str, Any]:
    """Return one full search trace by request_id."""
    from app.db import db_configured
    from app.repositories import SearchRepository

    if not db_configured():
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
    try:
        trace = SearchRepository().get_search_trace(request_id)
    except Exception as exc:
        logger.exception("get search failed")
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    if trace is None:
        raise HTTPException(status_code=404, detail="search not found")
    return trace


@app.get("/api/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str) -> SessionResponse:
    """Return stored session preferences."""
    from app.db import db_configured
    from app.repositories import SearchRepository

    if not db_configured():
        raise HTTPException(status_code=503, detail="DATABASE_URL is not configured")
    try:
        row = SearchRepository().get_session(session_id)
    except Exception as exc:
        logger.exception("get session failed")
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    if row is None:
        raise HTTPException(status_code=404, detail="session not found")
    return SessionResponse(**row)
