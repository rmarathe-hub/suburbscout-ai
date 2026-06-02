"""Phase 7 / Phase 2 Step 4 — audit log for query-agent turns."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app import config


def save_query_agent_turn(
    prompt: str,
    payload: dict[str, Any],
    *,
    plan: dict[str, Any] | None = None,
    raw_plan: dict[str, Any] | None = None,
    request_id: str | None = None,
    latency_ms: int | float | None = None,
) -> dict[str, Any]:
    """Append one query-agent turn to query_agent_audit.jsonl."""
    response = payload.get("response") or {}
    rid = request_id or payload.get("request_id") or str(uuid.uuid4())
    record = {
        "request_id": rid,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "latency_ms": latency_ms if latency_ms is not None else payload.get("latency_ms"),
        "prompt": prompt,
        "execution_status": payload.get("execution_status"),
        "message_code": payload.get("message_code"),
        "trust_gate": payload.get("trust_gate"),
        "trust_gate_blocks": payload.get("trust_gate_blocks"),
        "used_answer_llm": payload.get("used_answer_llm"),
        "plan": plan or payload.get("plan"),
        "raw_llm_plan": raw_plan or payload.get("raw_llm_plan"),
        "normalized_plan": payload.get("normalized_plan") or plan or payload.get("plan"),
        "final_recommendation": (response.get("final_recommendation") or "")[:2000],
        "top_match_names": [
            m.get("name")
            for m in (response.get("top_matches") or [])
            if isinstance(m, dict) and m.get("name")
        ][:10],
    }
    path = config.QUERY_AGENT_AUDIT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
    return {"saved": True, "path": str(path), "request_id": rid}
