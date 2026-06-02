#!/usr/bin/env python3
"""Plan a natural-language query with the LLM → QueryPlan JSON (Phase 4)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.llm_query_planner import planner_available, plan_query_with_llm  # noqa: E402
from app.plan_executor import execute_plan_async  # noqa: E402


async def _main_async() -> None:
    parser = argparse.ArgumentParser(description="LLM query planner CLI")
    parser.add_argument("prompt", help="User question in natural language")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Also run the plan against suburbs.json",
    )
    parser.add_argument(
        "--context-only",
        action="store_true",
        help="With --execute, print answer_context only",
    )
    args = parser.parse_args()

    if not planner_available():
        print(
            "Planner unavailable. Set USE_LLM_QUERY_PLANNER=true and Azure OpenAI env vars.",
            file=sys.stderr,
        )
        sys.exit(1)

    plan = await plan_query_with_llm(args.prompt)
    print(plan.model_dump_json(indent=2))

    if args.execute:
        result = await execute_plan_async(plan, validate=False)
        payload = result.answer_context if args.context_only else result.model_dump(mode="json")
        print("\n--- execution ---\n")
        print(json.dumps(payload, indent=2))


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
