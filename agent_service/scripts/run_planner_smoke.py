#!/usr/bin/env python3
"""Smoke-test LLM planner on golden manifest prompts (Phase 4, optional live)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT / "tests"))

from golden_plan_assertions import load_manifest  # noqa: E402
from app.llm_query_planner import planner_available, plan_query_with_llm  # noqa: E402
from app.plan_executor import execute_plan_async  # noqa: E402


async def _run() -> int:
    if not planner_available():
        print("Planner unavailable — configure Azure OpenAI and USE_LLM_QUERY_PLANNER=true")
        return 1

    cases = [
        c for c in load_manifest().get("cases", [])
        if c.get("prompt") and not c.get("expect_validation_error")
    ]
    if os.getenv("SKIP_SEMANTIC_GOLDEN", "").lower() in ("1", "true", "yes"):
        cases = [c for c in cases if c.get("source") != "semantic"]

    passed = 0
    rows = []
    for case in cases[:6]:
        prompt = case["prompt"]
        try:
            plan = await plan_query_with_llm(prompt)
            result = await execute_plan_async(plan, validate=False)
            ok = result.status.value == case.get("expect_status") or (
                case.get("expect_status") == "partial"
                and result.status.value in ("ok", "partial")
            )
            if ok:
                passed += 1
            rows.append({
                "id": case["id"],
                "ok": ok,
                "planned_ops": [getattr(o, "op", "?") for o in plan.ops],
                "execution_status": result.status.value,
                "expected": case.get("expect_status"),
            })
        except Exception as exc:
            rows.append({"id": case["id"], "ok": False, "error": str(exc)})

    print(json.dumps(rows, indent=2))
    print(f"\nPlanner smoke: {passed}/{len(rows)} aligned with golden execution status")
    return 0 if passed == len(rows) else 1


def main() -> None:
    raise SystemExit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
