#!/usr/bin/env python3
"""Write QueryPlan JSON Schema for LLM prompts / tooling."""

from __future__ import annotations

import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.query_plan import plan_json_schema, plan_schema_prompt_block  # noqa: E402

OUT_PATH = SERVICE_ROOT / "app" / "data" / "query_plan_schema.json"


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = plan_json_schema()
    OUT_PATH.write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print("\n--- Prompt hint ---\n")
    print(plan_schema_prompt_block())


if __name__ == "__main__":
    main()
