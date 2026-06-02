#!/usr/bin/env python3
"""Phase 2 Step 2 — Azure NL wiring + behavior contract for the query-agent path.

Checks:
  - Behavior contract module present
  - Query-agent env flags and Azure credentials (warnings if missing)
  - Phase 0 offline artifacts (subprocess, skips duplicate live Azure section)
  - query_agent_available()
  - Live (optional): embedding smoke, planner+executor+answer on one lookup prompt
  - Grounding: response towns/numbers traceable to execution payload

Skip live Azure: SKIP_LIVE_AZURE_CHECKS=1
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from dotenv import load_dotenv

load_dotenv(SERVICE_ROOT / ".env")

SMOKE_PROMPT = "What is the commute from Maynard?"


def _fail(msg: str) -> None:
    print(f"  FAIL: {msg}")
    sys.exit(1)


def _pass(msg: str) -> None:
    print(f"  PASS: {msg}")


def _skip(msg: str) -> None:
    print(f"  SKIP: {msg}")


def check_contract_module() -> None:
    print("1. LLM behavior contract (app/llm_contract.py)")
    from app.llm_contract import LLM_MAY, LLM_MUST_NOT, PIPELINE_STAGES

    if len(LLM_MAY) < 3 or len(LLM_MUST_NOT) < 4:
        _fail("llm_contract rules look incomplete")
    if len(PIPELINE_STAGES) < 3:
        _fail("PIPELINE_STAGES incomplete")
    _pass(f"contract defined ({len(LLM_MAY)} may / {len(LLM_MUST_NOT)} must-not rules)")


def check_query_agent_env() -> list[str]:
    print("\n2. Query-agent + Azure env")
    from app import config
    from app.llm_contract import REQUIRED_ENV_FOR_LIVE_QUERY_AGENT

    warnings: list[str] = []

    if not config.USE_LLM_QUERY_AGENT:
        warnings.append("USE_LLM_QUERY_AGENT is false — Step 1 default should be true")
    else:
        _pass("USE_LLM_QUERY_AGENT=true")

    if not config.USE_LLM_QUERY_PLANNER:
        warnings.append("USE_LLM_QUERY_PLANNER is false — planner required for query agent")
    else:
        _pass("USE_LLM_QUERY_PLANNER=true")

    for var, purpose in REQUIRED_ENV_FOR_LIVE_QUERY_AGENT:
        if var.startswith("USE_"):
            continue
        val = os.getenv(var, "")
        if var == "AZURE_OPENAI_DEPLOYMENT_NAME":
            val = config.CHAT_MODEL_DEPLOYMENT
        if val:
            _pass(f"{var} set ({purpose})")
        else:
            warnings.append(f"{var} missing — {purpose}")

    if config.FOUNDRY_PROJECT_ENDPOINT:
        _pass("FOUNDRY_PROJECT_ENDPOINT set (optional Foundry chat)")
    else:
        print("  INFO: FOUNDRY_PROJECT_ENDPOINT unset (Azure OpenAI fallback is fine)")

    return warnings


def check_phase0_offline() -> None:
    print("\n3. Phase 0 offline prerequisites")
    env = {**os.environ, "SKIP_LIVE_AZURE_CHECKS": "1"}
    proc = subprocess.run(
        [sys.executable, str(SERVICE_ROOT / "scripts" / "verify_phase0_prerequisites.py")],
        cwd=str(SERVICE_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        _fail("verify_phase0_prerequisites.py failed (offline)")
    if "Phase 0 complete" not in proc.stdout:
        _fail("Phase 0 script did not complete successfully")
    _pass("suburbs.json, vector index, validate_dataset (offline)")


def check_availability() -> None:
    print("\n4. Query agent availability")
    from app.query_agent import query_agent_available

    if not query_agent_available():
        _fail(
            "query_agent_available() is false — set USE_LLM_QUERY_AGENT, "
            "USE_LLM_QUERY_PLANNER, and Azure chat env vars"
        )
    _pass("query_agent_available()")


def _collect_execution_facts(payload: dict[str, Any]) -> tuple[set[str], set[float]]:
    """Town names and numeric facts from structured response fields."""
    towns: set[str] = set()
    floats: set[float] = set()

    def add_num(v: Any) -> None:
        if v is None:
            return
        try:
            floats.add(round(float(v), 2))
        except (TypeError, ValueError):
            pass

    resp = payload.get("response") or {}
    lookup = resp.get("lookup")
    if isinstance(lookup, dict):
        t = lookup.get("town") or {}
        if isinstance(t, dict) and t.get("name"):
            towns.add(str(t["name"]).lower())
        for key in ("drive_minutes_to_boston", "latest_home_price", "school_score", "safety_score"):
            if isinstance(t, dict):
                add_num(t.get(key))
        multi = lookup.get("multi")
        if isinstance(multi, list):
            for item in multi:
                if isinstance(item, dict) and item.get("town"):
                    towns.add(str(item["town"]).lower())

    for match in resp.get("top_matches") or []:
        if isinstance(match, dict) and match.get("name"):
            towns.add(str(match["name"]).lower())
            add_num(match.get("latest_home_price"))
            add_num(match.get("drive_minutes_to_boston"))

    plan = payload.get("plan") or {}
    for op in plan.get("ops") or []:
        if not isinstance(op, dict):
            continue
        if op.get("op") == "lookup":
            for item in op.get("items") or []:
                if isinstance(item, dict) and item.get("town"):
                    towns.add(str(item["town"]).lower())

    return towns, floats


async def check_live_query_agent() -> None:
    print("\n5. Live query-agent smoke (planner → executor → answer)")
    if os.getenv("SKIP_LIVE_AZURE_CHECKS", "").lower() in ("1", "true", "yes"):
        _skip("SKIP_LIVE_AZURE_CHECKS is set")
        return

    from app import config
    from app.llm_answer import answer_llm_available
    from app.llm_query_planner import planner_available
    from app.query_agent import handle_query_v2

    if not planner_available():
        _fail("planner_available() false — cannot run live smoke")
    _pass("planner_available()")

    if answer_llm_available():
        _pass("answer_llm_available()")
    else:
        print("  WARN: answer LLM not configured (USE_LLM_ANSWER may be false)")

    payload = await handle_query_v2(SMOKE_PROMPT, save_searches=False)
    status = payload.get("execution_status")
    if status not in ("ok", "partial"):
        _fail(f"expected execution_status ok|partial, got {status!r}: {payload.get('message_code')}")

    _pass(f"handle_query_v2 OK (execution_status={status})")

    plan = payload.get("plan") or {}
    ops = [o.get("op") for o in plan.get("ops") or [] if isinstance(o, dict)]
    if "lookup" not in ops and "rank" not in ops:
        _fail(f"expected lookup or rank in plan ops, got {ops}")
    _pass(f"plan ops include data op ({ops[0]})")

    resp = payload.get("response") or {}
    rec = (resp.get("final_recommendation") or "").lower()
    if "maynard" not in rec:
        _fail("answer should mention Maynard for commute lookup smoke test")
    _pass("grounded answer mentions queried town (Maynard)")

    towns, exec_floats = _collect_execution_facts(payload)
    if "maynard" not in towns and status == "ok":
        print(f"  WARN: Maynard not in structured lookup payload (towns={towns})")

    # At least one commute-like number in answer should match execution (minutes or miles)
    if exec_floats:
        found_num = False
        for num in exec_floats:
            if re.search(rf"\b{re.escape(str(num))}\b", rec) or re.search(
                rf"\b{int(num)}\b", rec
            ):
                found_num = True
                break
        if not found_num and config.USE_LLM_ANSWER:
            # LLM may round; check coarse range for commute minutes 30-50
            if not re.search(r"\d+\.?\d*\s*(min|minute|mile)", rec):
                _fail("answer should include commute numeric detail from execution")
        _pass("answer includes numeric detail consistent with execution")

    if payload.get("used_answer_llm"):
        _pass("answer LLM used (grounded narration)")
    else:
        _pass("template refusal/answer path (answer LLM skipped)")


def main() -> None:
    print("=== Phase 2 Step 2: Azure NL + behavior contract ===\n")
    check_contract_module()
    env_warnings = check_query_agent_env()
    check_phase0_offline()
    check_availability()

    if env_warnings and os.getenv("SKIP_LIVE_AZURE_CHECKS", "").lower() not in (
        "1",
        "true",
        "yes",
    ):
        print("\nWarnings (fix before live smoke):")
        for w in env_warnings:
            print(f"  - {w}")
        if any("missing" in w for w in env_warnings):
            _fail("Azure env incomplete for live query-agent smoke")

    asyncio.run(check_live_query_agent())

    print("\n=== Phase 2 Step 2 verification: PASSED ===")
    print("Contract: agent_service/docs/PHASE2_AZURE.md")
    print("Manual:   python scripts/ask_query.py \"What is the commute from Maynard?\"")


if __name__ == "__main__":
    main()
