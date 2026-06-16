"""Query route types for plan trust evaluation (Phase 9 — decoupled from legacy router)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

QueryIntent = Literal[
    "lookup_single_town",
    "lookup_multi_town",
    "compare_towns",
    "compare_multi_town",
    "recommend_structured",
    "recommend_semantic",
    "explain_ranking",
    "data_limit_question",
    "dataset_membership",
    "needs_clarification",
    "unsupported",
]


class QueryRoute(BaseModel):
    """Routing decision synthesized from a QueryPlan (trust/debug only)."""

    intent: QueryIntent
    confidence: float = Field(ge=0.0, le=1.0)
    query: str
    named_towns: list[str] = Field(default_factory=list)
    unknown_towns: list[str] = Field(default_factory=list)
    compare_town_a: str | None = None
    compare_town_b: str | None = None
    compare_towns: list[str] | None = None
    compare_columns: list[str] | None = None
    lookup_town: str | None = None
    lookup_specs: list[dict[str, str]] | None = None
    unsupported_field: str | None = None
    message: str | None = None
    use_semantic: bool = False
    pipeline: list[str] = Field(default_factory=list)
    classification_source: str = "llm"
