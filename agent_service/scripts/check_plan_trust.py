#!/usr/bin/env python3
"""Evaluate trust gates for a QueryPlan JSON file or NL prompt (Phase 6)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.plan_trust_gates import evaluate_plan_trust_gate, plan_to_query_route  # noqa: E402
from app.query_plan import validate_plan  # noqa: E402


async def _main_async() -> None:
    parser = argparse.ArgumentParser(description="Check plan trust gates.")
    parser.add_argument("prompt", nargs="?", help="Natural language prompt")
    parser.add_argument("--plan", help="Path to QueryPlan JSON (skip LLM)")
    args = parser.parse_args()

    if args.plan:
        plan = validate_plan(json.loads(Path(args.plan).read_text(encoding="utf-8")))
        query = args.prompt or ""
    elif args.prompt:
        from app.llm_query_planner import plan_query_with_llm

        plan = await plan_query_with_llm(args.prompt)
        query = args.prompt
    else:
        parser.error("Provide a prompt or --plan path")

    route = plan_to_query_route(query, plan)
    gate = evaluate_plan_trust_gate(query, plan)
    print(json.dumps({
        "synthetic_route_intent": route.intent,
        "trust_gate": gate.gate_type if gate else None,
        "blocks_pipeline": gate.blocks_pipeline if gate else False,
        "message": gate.message if gate else None,
    }, indent=2))


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
