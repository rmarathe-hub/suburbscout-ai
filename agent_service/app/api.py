"""Thin FastAPI gateway for the query agent (Phase 2 Step 6 + Phase 3A persistence).

Run from agent_service/:
  uvicorn app.api:app --reload --host 127.0.0.1 --port 8000

  curl -s http://127.0.0.1:8000/health | jq
  curl -s -X POST http://127.0.0.1:8000/api/query \\
    -H 'Content-Type: application/json' \\
    -d '{"prompt":"What is the commute from Maynard?"}' | jq
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.api_schemas import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
    SearchListResponse,
    SearchSummary,
    SessionResponse,
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="SuburbScout Query Agent",
    description="Natural language → QueryPlan → deterministic execution → grounded answer",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


def payload_to_query_response(payload: dict[str, Any], *, debug: bool) -> QueryResponse:
    """Map handle_query_v2 payload to API response."""
    response = payload.get("response") or {}
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
    )


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    from app.query_agent import query_agent_available

    return HealthResponse(
        status="ok",
        query_agent_configured=query_agent_available(),
        suburbs_dataset_loaded=_suburbs_dataset_loaded(),
        database=_database_status(),
    )


@app.post("/api/query", response_model=QueryResponse)
async def query_suburbs(body: QueryRequest) -> QueryResponse:
    """Run the production query-agent pipeline on one prompt."""
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

    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="prompt cannot be empty")

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

    return payload_to_query_response(payload, debug=body.debug)


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
