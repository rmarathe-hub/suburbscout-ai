#!/usr/bin/env python3
"""Run randomized 150-prompt samples from the Phase 1.6 eval pool."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))
sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

DEFAULT_POOL = SERVICE_ROOT / "app" / "evals" / "eval_pool_500.json"
DEFAULT_OUT_DIR = SERVICE_ROOT / "app" / "evals" / "results"


def _intent_compatible(expected: str, actual: str) -> bool:
    if expected == actual:
        return True
    if expected in ("lookup_single_town", "dataset_membership") and actual == "lookup_single_town":
        return True
    if expected == "recommend_structured" and actual == "recommend_semantic":
        return True
    if expected == "recommend_semantic" and actual == "recommend_structured":
        return True
    if expected == "refuse_out_of_scope" and actual in (
        "unsupported",
        "needs_clarification",
        "data_limit_question",
    ):
        return True
    if expected == "lookup_single_town" and actual == "data_limit_question":
        return True
    return False


def _failure_bucket(reason: str | None) -> str:
    if not reason:
        return "pass"
    if reason.startswith("wrong_intent"):
        return "wrong_intent"
    if "Route intent" in reason:
        return "strict_route_mismatch"
    if "Lookup question returned ranked" in reason:
        return "lookup_returned_ranked"
    if "Comparison question returned" in reason:
        return "compare_shape"
    if "unsupported" in reason.lower():
        return "unsupported"
    if "coastal" in reason.lower():
        return "coastal_filter"
    if "inverted" in reason.lower() or "high-crime" in reason.lower() or "safety" in reason.lower():
        return "inverted_ranking"
    return "other_validation"


async def _run_routing_only(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app.hybrid_intent_router import classify_query_hybrid, should_use_llm_intent_fallback
    from app.intent_classifier import classify_user_intent
    from app.llm_intent_classifier import llm_fallback_available

    rows: list[dict[str, Any]] = []
    for case in cases:
        prompt = case["prompt"]
        expected = case["expected_intent"]
        py = classify_user_intent(prompt)
        route = await classify_query_hybrid(prompt)
        actual = route.intent
        intent_match = _intent_compatible(expected, actual)
        rows.append({
            **case,
            "python_intent": py.intent,
            "python_confidence": py.confidence,
            "actual_intent": actual,
            "intent_match": intent_match,
            "llm_fallback_used": route.llm_fallback_used,
            "classification_source": route.classification_source,
            "would_llm_fallback": should_use_llm_intent_fallback(py),
            "passed": intent_match and actual != "unsupported",
            "failure_reason": None
            if intent_match and actual != "unsupported"
            else f"wrong_intent: expected {expected}, got {actual}",
            "mode": "routing_only",
            "llm_available": llm_fallback_available(),
        })
    return rows


def _summarize(results: list[dict[str, Any]], *, sample_seed: int) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.get("passed"))
    intent_ok = sum(1 for r in results if r.get("intent_match"))
    unsupported = sum(1 for r in results if r.get("actual_intent") == "unsupported")
    llm_used = sum(1 for r in results if r.get("llm_fallback_used"))

    by_cat: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0, "intent_ok": 0})
    failures: Counter[str] = Counter()
    for row in results:
        cat = row.get("category", "?")
        by_cat[cat]["total"] += 1
        if row.get("passed"):
            by_cat[cat]["passed"] += 1
        if row.get("intent_match"):
            by_cat[cat]["intent_ok"] += 1
        if not row.get("passed"):
            failures[_failure_bucket(row.get("failure_reason"))] += 1
            failures[f"cat:{cat}"] += 1

    top_failures = Counter(
        r.get("failure_reason") or "unknown"
        for r in results
        if not r.get("passed")
    ).most_common(15)

    return {
        "sample_seed": sample_seed,
        "total": total,
        "passed": passed,
        "pass_rate_pct": round(100 * passed / total, 1) if total else 0,
        "intent_match": intent_ok,
        "intent_match_pct": round(100 * intent_ok / total, 1) if total else 0,
        "unsupported_count": unsupported,
        "llm_fallback_count": llm_used,
        "llm_fallback_pct": round(100 * llm_used / total, 1) if total else 0,
        "by_category": dict(by_cat),
        "failure_buckets": dict(failures),
        "top_failures": top_failures,
    }


async def main_async(args: argparse.Namespace) -> None:
    pool_path = args.pool
    if not pool_path.exists():
        raise SystemExit(f"Pool not found: {pool_path}. Run scripts/generate_eval_pool.py first.")

    pool_data = json.loads(pool_path.read_text(encoding="utf-8"))
    all_cases = pool_data["cases"]

    from app.evals.prompt_templates import EvalPrompt, sample_prompts

    eval_pool = [
        EvalPrompt(c["category"], c["expected_intent"], c["prompt"])
        for c in all_cases
    ]

    aggregate: list[dict[str, Any]] = []
    for run_idx in range(args.samples):
        seed = args.seed + run_idx
        sampled = sample_prompts(eval_pool, n=args.sample_size, seed=seed)
        counters: dict[str, int] = {}
        cases: list[dict[str, Any]] = []
        for item in sampled:
            counters[item.category] = counters.get(item.category, 0) + 1
            cases.append({
                "id": f"sample{run_idx}_{item.category}_{counters[item.category]:03d}",
                "category": item.category,
                "category_label": item.category,
                "expected_intent": item.expected_intent,
                "prompt": item.prompt,
            })

        if args.mode == "full":
            from run_holdout_150 import run_holdout

            results = await run_holdout(cases)
            for row in results:
                row["mode"] = "full"
            summary = _summarize(results, sample_seed=seed)
            summary["strict_pass"] = sum(1 for r in results if r.get("passed"))
        else:
            results = await _run_routing_only(cases)
            summary = _summarize(results, sample_seed=seed)

        aggregate.append(summary)
        print(
            f"Sample {run_idx + 1}/{args.samples} seed={seed}: "
            f"pass={summary['passed']}/{summary['total']} "
            f"intent={summary['intent_match']}/{summary['total']} "
            f"unsupported={summary['unsupported_count']} "
            f"llm={summary['llm_fallback_pct']}%"
        )

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = args.out_prefix or f"randomized_eval_{args.sample_size}"
    out_path = out_dir / f"{prefix}_{ts}.json"
    payload = {
        "description": "Phase 1.6 randomized eval samples",
        "pool": str(pool_path),
        "sample_size": args.sample_size,
        "samples": args.samples,
        "base_seed": args.seed,
        "mode": args.mode,
        "aggregate": aggregate,
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")

    avg_pass = sum(s["passed"] for s in aggregate) / len(aggregate)
    print(f"Average pass across {args.samples} samples: {avg_pass:.1f}/{args.sample_size}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Randomized eval from template pool")
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    parser.add_argument("--sample-size", type=int, default=150)
    parser.add_argument("--samples", type=int, default=3, help="Number of random 150-draws")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--mode", choices=("routing", "full"), default="routing")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--out-prefix", type=str, default="")
    args = parser.parse_args()
    if args.mode == "full":
        args.mode = "full"
    else:
        args.mode = "routing"
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
