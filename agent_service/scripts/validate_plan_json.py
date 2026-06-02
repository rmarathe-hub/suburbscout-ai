#!/usr/bin/env python3
"""Validate a QueryPlan JSON file or stdin. Phase 1 helper."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.query_plan import PlanValidationError, plan_schema_prompt_block, validate_plan  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate QueryPlan JSON.")
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to JSON plan file (default: read stdin)",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Print normalized plan JSON on success",
    )
    parser.add_argument(
        "--schema-hint",
        action="store_true",
        help="Print compact schema hint and exit",
    )
    args = parser.parse_args()

    if args.schema_hint:
        print(plan_schema_prompt_block())
        return

    if args.path:
        raw = json.loads(Path(args.path).read_text(encoding="utf-8"))
    else:
        raw = json.load(sys.stdin)

    try:
        plan = validate_plan(raw)
    except PlanValidationError as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"INVALID: {exc}", file=sys.stderr)
        sys.exit(1)

    print("VALID")
    if args.pretty:
        print(plan.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
