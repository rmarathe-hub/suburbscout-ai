#!/usr/bin/env python3
"""Generate Phase 1.6 eval pool (500+ prompts) from templates."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.evals.prompt_templates import generate_eval_pool, prompts_to_cases  # noqa: E402

DEFAULT_OUT = SERVICE_ROOT / "app" / "evals" / "eval_pool_500.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate template eval prompt pool")
    parser.add_argument("--seed", type=int, default=160)
    parser.add_argument("--per-category", type=int, default=60)
    parser.add_argument("--min-total", type=int, default=500)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    pool = generate_eval_pool(
        seed=args.seed,
        per_category=args.per_category,
        min_total=args.min_total,
    )
    cases = prompts_to_cases(pool)
    by_cat: dict[str, int] = {}
    for case in cases:
        by_cat[case["category"]] = by_cat.get(case["category"], 0) + 1

    payload = {
        "description": "Phase 1.6 template-generated eval pool",
        "seed": args.seed,
        "per_category": args.per_category,
        "prompt_count": len(cases),
        "by_category": by_cat,
        "cases": cases,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(cases)} prompts to {args.out}")
    print("By category:", by_cat)


if __name__ == "__main__":
    main()
