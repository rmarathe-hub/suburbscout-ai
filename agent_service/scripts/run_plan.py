#!/usr/bin/env python3
"""Execute a QueryPlan JSON file against suburbs.json (Phase 2)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.plan_executor import ExecutionStatus, execute_plan  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Execute a QueryPlan against local data.")
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to plan JSON (default: stdin)",
    )
    parser.add_argument(
        "--context-only",
        action="store_true",
        help="Print answer_context JSON only (for LLM answer stage)",
    )
    parser.add_argument(
        "--refusal",
        action="store_true",
        help="If execution cannot answer, print template refusal text",
    )
    args = parser.parse_args()

    if args.path:
        raw = json.loads(Path(args.path).read_text(encoding="utf-8"))
    else:
        raw = json.load(sys.stdin)

    result = execute_plan(raw)
    if args.refusal and result.status not in (ExecutionStatus.OK, ExecutionStatus.PARTIAL):
        print(result.refusal_message())
        sys.exit(0 if result.status == "out_of_scope" else 1)

    payload = result.answer_context if args.context_only else result.model_dump(mode="json")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
