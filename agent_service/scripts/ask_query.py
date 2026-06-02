#!/usr/bin/env python3
"""One-shot query agent: plan → execute → answer (Phase 5)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


async def _main_async(prompt: str, *, as_json: bool) -> None:
    from app import config

    config.USE_LLM_QUERY_AGENT = True
    from app.query_agent import handle_query_v2, query_agent_available

    if not query_agent_available():
        print(
            "Query agent unavailable. Set USE_LLM_QUERY_AGENT=true, USE_LLM_QUERY_PLANNER=true, "
            "and Azure OpenAI env vars.",
            file=sys.stderr,
        )
        sys.exit(1)

    config.USE_LLM_QUERY_AGENT = True
    payload = await handle_query_v2(prompt, save_searches=False)
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        print(payload["response"].get("final_recommendation", ""))
        status = payload.get("execution_status")
        if status:
            print(f"\n[execution_status={status}]")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Phase 5 query agent on one prompt.")
    parser.add_argument("prompt", help="Natural language question")
    parser.add_argument("--json", action="store_true", help="Print full payload JSON")
    args = parser.parse_args()
    asyncio.run(_main_async(args.prompt, as_json=args.json))


if __name__ == "__main__":
    main()
