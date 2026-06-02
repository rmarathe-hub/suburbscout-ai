#!/usr/bin/env python3
"""Run query-agent eval suite (Phase 7, live LLM + Azure required)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

DEFAULT_EVAL = SERVICE_ROOT / "app" / "evals" / "query_agent_eval.json"
RESULTS_DIR = SERVICE_ROOT / "app" / "evals" / "results"


async def run_cases(cases: list[dict], *, save_audit: bool) -> list[dict]:
    from app import config
    from app.query_agent import handle_query_v2, query_agent_available

    if not query_agent_available():
        raise SystemExit(
            "Query agent not available. Set USE_LLM_QUERY_AGENT=true, USE_LLM_QUERY_PLANNER=true, "
            "and Azure OpenAI credentials."
        )

    config.USE_LLM_QUERY_AGENT = True
    rows: list[dict] = []
    for case in cases:
        prompt = case["prompt"]
        payload = await handle_query_v2(prompt, save_searches=save_audit)
        rows.append({
            **case,
            "execution_status": payload.get("execution_status"),
            "trust_gate": payload.get("trust_gate"),
            "used_answer_llm": payload.get("used_answer_llm"),
            "final_snippet": (payload.get("response") or {}).get("final_recommendation", "")[:280],
            "plan_ops": [
                op.get("op") for op in (payload.get("plan") or {}).get("ops") or []
            ],
            "_payload": payload,
        })
    return rows


def score(rows: list[dict]) -> dict:
    from app.evals.query_agent_runner import evaluate_query_agent_case

    passed = 0
    failures: list[dict] = []
    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})

    for row in rows:
        cat = row.get("category", "?")
        by_cat[cat]["total"] += 1
        ok, reasons = evaluate_query_agent_case(row, row.pop("_payload"))
        if ok:
            passed += 1
            by_cat[cat]["passed"] += 1
        else:
            failures.append({
                "id": row.get("id"),
                "prompt": row.get("prompt"),
                "reasons": reasons,
                "execution_status": row.get("execution_status"),
                "trust_gate": row.get("trust_gate"),
            })

    total = len(rows)
    return {
        "total": total,
        "passed": passed,
        "pass_rate_pct": round(100 * passed / total, 1) if total else 0,
        "by_category": dict(by_cat),
        "failures": failures,
    }


async def main_async(args: argparse.Namespace) -> None:
    if os.getenv("SKIP_LIVE_QUERY_AGENT_EVAL", "").lower() in ("1", "true", "yes"):
        print("SKIP_LIVE_QUERY_AGENT_EVAL is set — aborting live eval.")
        sys.exit(0)

    data = json.loads(args.eval.read_text(encoding="utf-8"))
    cases = data["cases"]
    if args.limit:
        cases = cases[: args.limit]

    rows = await run_cases(cases, save_audit=args.save_audit)
    summary = score(rows)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"query_agent_eval_{stamp}.json"
    out_path.write_text(
        json.dumps({"summary": summary, "rows": [{k: v for k, v in r.items() if k != "_payload"} for r in rows]}, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    print(f"\nWrote {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run query-agent eval suite.")
    parser.add_argument("--eval", type=Path, default=DEFAULT_EVAL)
    parser.add_argument("--limit", type=int, default=0, help="Max cases (0 = all)")
    parser.add_argument("--save-audit", action="store_true", help="Append query_agent_audit.jsonl")
    args = parser.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
