#!/usr/bin/env python3
"""Layer 1 — planner-only eval: NL → QueryPlan vs expected fixtures (live LLM)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

DEFAULT_EVAL = SERVICE_ROOT / "app" / "evals" / "planner_eval_100.json"
RESULTS_DIR = SERVICE_ROOT / "app" / "evals" / "results"


def _load_cases(path: Path, *, limit: int | None) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases") or []
    if limit:
        cases = cases[:limit]
    return cases


async def _run_live(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.evals.planner_eval_scoring import plan_from_dict, score_plan_against_expect
    from app.llm_query_planner import plan_query_with_llm, planner_available

    if not planner_available():
        raise SystemExit(
            "Planner not available. Set USE_LLM_QUERY_PLANNER=true and Azure credentials."
        )

    rows: list[dict[str, Any]] = []
    for case in cases:
        prompt = case["prompt"]
        expect = case.get("expect") or {}
        repair_count = 0
        try:
            plan = await plan_query_with_llm(prompt)
        except Exception as exc:
            rows.append(
                {
                    **case,
                    "passed": False,
                    "op_accuracy": 0.0,
                    "town_accuracy": 0.0,
                    "field_accuracy": 0.0,
                    "failure_reasons": [f"planner_error: {exc}"],
                    "repair_count": repair_count,
                }
            )
            continue

        if case.get("plan_file"):
            expected_plan = plan_from_dict(
                json.loads((SERVICE_ROOT / case["plan_file"]).read_text(encoding="utf-8"))
            )
            # Score against manifest expect block (derived from fixture)
            score = score_plan_against_expect(plan, expect)
        else:
            score = score_plan_against_expect(plan, expect)

        rows.append(
            {
                **case,
                **score,
                "actual_plan": plan.model_dump(mode="json"),
                "repair_count": repair_count,
            }
        )
    return rows


def _run_offline(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Score expected fixtures against themselves (sanity) + optional plan_file replay."""
    from app.evals.planner_eval_scoring import plan_from_dict, score_plan_against_expect

    rows: list[dict[str, Any]] = []
    for case in cases:
        plan_path = SERVICE_ROOT / case["plan_file"]
        plan = plan_from_dict(json.loads(plan_path.read_text(encoding="utf-8")))
        score = score_plan_against_expect(plan, case.get("expect") or {})
        rows.append({**case, **score, "mode": "offline_fixture"})
    return rows


def _summarize(rows: list[dict[str, Any]], targets: dict[str, float]) -> dict[str, Any]:
    n = len(rows)
    passed = sum(1 for r in rows if r.get("passed"))
    op_acc = sum(r.get("op_accuracy", 0) for r in rows) / n if n else 0
    town_acc = sum(r.get("town_accuracy", 0) for r in rows) / n if n else 0
    field_acc = sum(r.get("field_accuracy", 0) for r in rows) / n if n else 0

    by_cat: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "passed": 0, "op_acc": 0.0}
    )
    for r in rows:
        cat = r.get("category", "?")
        by_cat[cat]["total"] += 1
        if r.get("passed"):
            by_cat[cat]["passed"] += 1
        by_cat[cat]["op_acc"] += r.get("op_accuracy", 0)

    for cat in by_cat:
        t = by_cat[cat]["total"]
        by_cat[cat]["op_acc"] = round(by_cat[cat]["op_acc"] / t, 3) if t else 0
        by_cat[cat]["pass_rate"] = round(by_cat[cat]["passed"] / t, 3) if t else 0

    return {
        "layer": "planner_only",
        "total": n,
        "passed": passed,
        "pass_rate": round(passed / n, 3) if n else 0,
        "operation_accuracy": round(op_acc, 3),
        "town_extraction_accuracy": round(town_acc, 3),
        "field_constraint_accuracy": round(field_acc, 3),
        "targets": targets,
        "met_targets": {
            "operation_accuracy": op_acc >= targets.get("operation_accuracy", 0.9),
            "town_extraction_accuracy": town_acc >= targets.get("town_extraction_accuracy", 0.9),
            "field_constraint_accuracy": field_acc >= targets.get("field_constraint_accuracy", 0.9),
        },
        "by_category": dict(by_cat),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run planner-only eval (Layer 1)")
    parser.add_argument("--eval", type=Path, default=DEFAULT_EVAL)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Validate fixtures only (no LLM calls)",
    )
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    payload = json.loads(args.eval.read_text(encoding="utf-8"))
    cases = _load_cases(args.eval, limit=args.limit)
    targets = payload.get("targets") or {
        "operation_accuracy": 0.9,
        "town_extraction_accuracy": 0.9,
        "field_constraint_accuracy": 0.9,
    }

    if args.offline:
        rows = _run_offline(cases)
    else:
        rows = asyncio.run(_run_live(cases))

    summary = _summarize(rows, targets)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = args.out or RESULTS_DIR / f"planner_eval_100_{ts}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"summary": summary, "results": rows}, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    print(f"\nWrote {out}")
    if not summary["met_targets"]["operation_accuracy"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
