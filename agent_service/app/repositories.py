"""Postgres persistence for query-agent turns (Phase 3A)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.db import db_configured, get_db_session
from app.db_models import (
    AnswerLog,
    AuditEvent,
    QueryPlanRecord,
    RecommendationResult,
    Search,
    SessionRecord,
)

logger = logging.getLogger(__name__)

_FOLLOWUP_PRIORITY_RE = re.compile(
    r"commute.*(?:more|higher|important)|(?:more|higher|important).*commute",
    re.I,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _infer_result_type(payload: dict[str, Any]) -> str:
    response = payload.get("response") or {}
    if payload.get("trust_gate_blocks"):
        return "blocked"
    if response.get("comparison"):
        return "compare"
    if response.get("lookup"):
        return "lookup"
    if response.get("semantic_candidates"):
        return "semantic_search"
    if response.get("top_matches"):
        return "rank"
    status = str(payload.get("execution_status") or "")
    if status in {"out_of_scope", "blocked"}:
        return "blocked"
    return status or "unknown"


def _build_results_payload(payload: dict[str, Any]) -> dict[str, Any]:
    response = payload.get("response") or {}
    return {
        "top_matches": response.get("top_matches") or [],
        "comparison": response.get("comparison"),
        "lookup": response.get("lookup"),
        "semantic_candidates": response.get("semantic_candidates"),
        "execution_status": payload.get("execution_status"),
        "message_code": payload.get("message_code"),
    }


def _trust_gate_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    gate = payload.get("trust_gate")
    if gate is None and not payload.get("trust_gate_blocks"):
        return None
    return {
        "gate_type": gate,
        "blocks_pipeline": payload.get("trust_gate_blocks"),
    }


def _extract_rank_preferences(plan: dict[str, Any] | None) -> dict[str, Any]:
    if not plan:
        return {}
    for op in plan.get("ops") or []:
        if isinstance(op, dict) and op.get("op") == "rank":
            prefs = op.get("preferences")
            if isinstance(prefs, dict) and prefs:
                return dict(prefs)
    return {}


def _merge_session_preferences(
    existing: dict[str, Any] | None,
    plan: dict[str, Any] | None,
    prompt: str,
) -> dict[str, Any]:
    merged = dict(existing or {})
    rank_prefs = _extract_rank_preferences(plan)
    if rank_prefs:
        merged.update(rank_prefs)
    if _FOLLOWUP_PRIORITY_RE.search(prompt):
        merged["commute_priority"] = "high"
        if merged.get("school_priority") == "high" and "deprioritize_schools" not in merged:
            merged["school_priority"] = "medium"
    return merged


class SearchRepository:
    """Persist and read query-agent traces."""

    def get_session_context(self, session_id: str) -> dict[str, Any] | None:
        if not db_configured():
            return None
        with get_db_session() as db:
            row = db.scalar(
                select(SessionRecord).where(SessionRecord.session_id == session_id)
            )
            if not row or not row.latest_preferences:
                return None
            return {
                "session_id": session_id,
                "latest_preferences": row.latest_preferences,
            }

    def upsert_session_preferences(
        self,
        session_id: str,
        preferences: dict[str, Any],
    ) -> None:
        if not db_configured():
            return
        with get_db_session() as db:
            row = db.scalar(
                select(SessionRecord).where(SessionRecord.session_id == session_id)
            )
            now = _utcnow()
            if row is None:
                db.add(
                    SessionRecord(
                        session_id=session_id,
                        latest_preferences=preferences,
                        created_at=now,
                        updated_at=now,
                    )
                )
            else:
                row.latest_preferences = preferences
                row.updated_at = now

    def update_session_from_turn(
        self,
        session_id: str,
        *,
        prompt: str,
        plan: dict[str, Any] | None,
    ) -> None:
        if not db_configured():
            return
        existing = self.get_session_context(session_id)
        prior = (existing or {}).get("latest_preferences")
        merged = _merge_session_preferences(prior, plan, prompt)
        if merged:
            self.upsert_session_preferences(session_id, merged)

    def save_turn(
        self,
        prompt: str,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist one query-agent turn. Raises on DB errors."""
        if not db_configured():
            return {"saved": False, "reason": "database_not_configured"}

        request_id = str(payload.get("request_id") or "")
        if not request_id:
            return {"saved": False, "reason": "missing_request_id"}

        response = payload.get("response") or {}
        with get_db_session() as db:
            search = Search(
                request_id=request_id,
                prompt=prompt,
                execution_status=str(payload.get("execution_status") or ""),
                message_code=payload.get("message_code"),
                latency_ms=payload.get("latency_ms"),
                session_id=session_id,
            )
            db.add(search)
            db.flush()

            db.add(
                QueryPlanRecord(
                    search_id=search.id,
                    raw_llm_plan=payload.get("raw_llm_plan"),
                    normalized_plan=payload.get("normalized_plan") or payload.get("plan"),
                    trust_gate=_trust_gate_payload(payload),
                )
            )
            db.add(
                RecommendationResult(
                    search_id=search.id,
                    result_type=_infer_result_type(payload),
                    results=_build_results_payload(payload),
                )
            )
            db.add(
                AnswerLog(
                    search_id=search.id,
                    answer=(response.get("final_recommendation") or "")[:8000],
                    used_answer_llm=bool(payload.get("used_answer_llm")),
                )
            )
            db.add(
                AuditEvent(
                    request_id=request_id,
                    event_type="query_completed",
                    payload={
                        "execution_status": payload.get("execution_status"),
                        "message_code": payload.get("message_code"),
                        "session_id": session_id,
                    },
                )
            )

        if session_id:
            try:
                self.update_session_from_turn(
                    session_id,
                    prompt=prompt,
                    plan=payload.get("normalized_plan") or payload.get("plan"),
                )
            except Exception:
                logger.warning("session preference update failed", exc_info=True)

        return {"saved": True, "request_id": request_id}

    def list_searches(self, *, limit: int = 20) -> list[dict[str, Any]]:
        if not db_configured():
            return []
        limit = max(1, min(limit, 100))
        with get_db_session() as db:
            rows = db.scalars(
                select(Search).order_by(Search.created_at.desc()).limit(limit)
            ).all()
            return [
                {
                    "request_id": row.request_id,
                    "prompt": row.prompt,
                    "execution_status": row.execution_status,
                    "message_code": row.message_code,
                    "latency_ms": row.latency_ms,
                    "session_id": row.session_id,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                }
                for row in rows
            ]

    def get_search_trace(self, request_id: str) -> dict[str, Any] | None:
        if not db_configured():
            return None
        with get_db_session() as db:
            row = db.scalar(select(Search).where(Search.request_id == request_id))
            if row is None:
                return None
            plan = row.query_plan
            result = row.recommendation_result
            answer = row.answer_log
            events = db.scalars(
                select(AuditEvent)
                .where(AuditEvent.request_id == request_id)
                .order_by(AuditEvent.created_at.asc())
            ).all()
            return {
                "request_id": row.request_id,
                "prompt": row.prompt,
                "execution_status": row.execution_status,
                "message_code": row.message_code,
                "latency_ms": row.latency_ms,
                "session_id": row.session_id,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "query_plan": {
                    "raw_llm_plan": plan.raw_llm_plan if plan else None,
                    "normalized_plan": plan.normalized_plan if plan else None,
                    "trust_gate": plan.trust_gate if plan else None,
                },
                "recommendation_result": {
                    "result_type": result.result_type if result else None,
                    "results": result.results if result else None,
                },
                "answer": {
                    "text": answer.answer if answer else None,
                    "used_answer_llm": answer.used_answer_llm if answer else False,
                },
                "audit_events": [
                    {
                        "event_type": event.event_type,
                        "payload": event.payload,
                        "created_at": event.created_at.isoformat()
                        if event.created_at
                        else None,
                    }
                    for event in events
                ],
            }

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        if not db_configured():
            return None
        with get_db_session() as db:
            row = db.scalar(
                select(SessionRecord).where(SessionRecord.session_id == session_id)
            )
            if row is None:
                return None
            return {
                "session_id": row.session_id,
                "latest_preferences": row.latest_preferences,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }


def persist_query_turn(
    prompt: str,
    payload: dict[str, Any],
    *,
    session_id: str | None = None,
    save_jsonl: bool = False,
) -> dict[str, Any]:
    """
    Best-effort Postgres persist with optional JSONL fallback.

    Never raises — callers must not break user responses on failure.
    """
    if db_configured():
        try:
            return SearchRepository().save_turn(
                prompt, payload, session_id=session_id
            )
        except Exception:
            logger.warning("postgres save_turn failed", exc_info=True)

    if save_jsonl:
        try:
            from app.query_agent_audit import save_query_agent_turn

            return save_query_agent_turn(
                prompt,
                payload,
                plan=payload.get("plan"),
                raw_plan=payload.get("raw_llm_plan"),
                request_id=payload.get("request_id"),
                latency_ms=payload.get("latency_ms"),
            )
        except Exception:
            logger.warning("jsonl audit save failed", exc_info=True)

    return {"saved": False}


def persist_legacy_search(
    prompt: str,
    *,
    results: list[dict[str, Any]] | None = None,
    preferences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Persist orchestrator save_search_tool output (Postgres first, JSONL fallback).

    Never raises — legacy pipeline must keep working without DATABASE_URL.
    """
    import uuid

    from app.config import SAVED_SEARCHES_PATH

    prefs = preferences or {}
    matches = list(results or [])
    request_id = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "request_id": request_id,
        "execution_status": "ok",
        "message_code": "legacy_save_search",
        "latency_ms": None,
        "used_answer_llm": False,
        "plan": {"ops": [{"op": "rank", "preferences": prefs}]},
        "raw_llm_plan": None,
        "normalized_plan": {"ops": [{"op": "rank", "preferences": prefs}]},
        "response": {
            "final_recommendation": "",
            "top_matches": matches,
        },
    }

    if db_configured():
        try:
            result = SearchRepository().save_turn(prompt, payload)
            if result.get("saved"):
                return {
                    "saved": True,
                    "storage": "postgres",
                    "request_id": request_id,
                }
        except Exception:
            logger.warning("legacy save_search postgres failed", exc_info=True)

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt": prompt,
        "preferences": prefs,
        "results": matches,
        "request_id": request_id,
    }
    try:
        SAVED_SEARCHES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(SAVED_SEARCHES_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return {
            "saved": True,
            "storage": "jsonl",
            "path": str(SAVED_SEARCHES_PATH),
            "timestamp": record["timestamp"],
            "request_id": request_id,
        }
    except Exception:
        logger.warning("legacy save_search jsonl failed", exc_info=True)
        return {"saved": False, "request_id": request_id}
