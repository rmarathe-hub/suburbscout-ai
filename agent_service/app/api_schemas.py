"""HTTP API request/response models (Phase 2 Step 6)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """POST /api/query body."""

    prompt: str = Field(..., min_length=1, max_length=4000, description="Natural language suburb question")
    save_audit: bool = Field(
        default=False,
        description="Append turn to query_agent_audit.jsonl",
    )
    debug: bool = Field(
        default=False,
        description="Include plan + full response payload in the API result",
    )


class QueryResponse(BaseModel):
    """Production-facing query result (matches CLI summary fields)."""

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


class HealthResponse(BaseModel):
    status: str
    query_agent_configured: bool
    suburbs_dataset_loaded: bool
