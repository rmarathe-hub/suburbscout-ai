"""HTTP API request/response models (Phase 2 Step 6 + Phase 7 gateway)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class QueryRequest(BaseModel):
    """POST /api/query body."""

    prompt: str | None = Field(
        default=None,
        max_length=4000,
        description="Natural language suburb question",
    )
    query: str | None = Field(
        default=None,
        max_length=4000,
        description="Alias for prompt (frontend ergonomics)",
    )
    session_id: str | None = Field(
        default=None,
        max_length=128,
        description="Optional session id for follow-up preference context",
    )
    save_audit: bool = Field(
        default=False,
        description="Append turn to query_agent_audit.jsonl when Postgres is unavailable",
    )
    debug: bool = Field(
        default=False,
        description="Include plan + full response payload in the API result",
    )

    def resolved_prompt(self) -> str:
        """Return non-empty user text from prompt or query."""
        return (self.prompt or "").strip() or (self.query or "").strip()

    @model_validator(mode="after")
    def _require_prompt_or_query(self) -> QueryRequest:
        text = self.resolved_prompt()
        if not text:
            raise ValueError("prompt or query is required")
        if len(text) > 4000:
            raise ValueError("prompt must be at most 4000 characters")
        return self


class QueryResponse(BaseModel):
    """Production-facing query result (local pipeline or Foundry hosted agent)."""

    answer: str
    execution_status: str
    request_id: str
    latency_ms: int | None = None
    message_code: str | None = None
    trust_gate: str | None = None
    trust_gate_blocks: bool | None = None
    used_answer_llm: bool = False
    top_matches: list[dict[str, Any]] = Field(default_factory=list)
    plan: dict[str, Any] | None = None
    raw_llm_plan: dict[str, Any] | None = None
    response: dict[str, Any] | None = None
    # Phase 7 — unified contract for frontend
    source: Literal["foundry_hosted_agent", "local_query_pipeline"] | None = None
    metadata: dict[str, Any] | None = None
    comparison: dict[str, Any] | None = None
    tradeoff_warning: str | None = None
    score_disclaimer: str | None = None
    error: str | None = Field(
        default=None,
        description="Error code when execution failed (e.g. foundry_agent_error)",
    )


class HealthResponse(BaseModel):
    status: str
    query_agent_configured: bool
    suburbs_dataset_loaded: bool
    database: str = Field(
        description="ok | unavailable | not_configured",
    )
    # Phase 7
    backend_agent_mode: str = "local"
    foundry_agent_configured: bool = False
    foundry_agent_endpoint: str | None = None


class WarmHealthResponse(BaseModel):
    """POST /health/warm — lightweight Foundry hosted-agent wake-up."""

    status: Literal["ok", "error", "skipped"] = "skipped"
    warmed: bool = False
    latency_ms: int | None = None
    message: str | None = None


class SearchSummary(BaseModel):
    request_id: str
    prompt: str
    execution_status: str | None = None
    message_code: str | None = None
    latency_ms: int | None = None
    session_id: str | None = None
    created_at: str | None = None


class SearchListResponse(BaseModel):
    searches: list[SearchSummary]


class SessionResponse(BaseModel):
    session_id: str
    latest_preferences: dict[str, Any] | None = None
    created_at: str | None = None
    updated_at: str | None = None
