#!/usr/bin/env python3
"""Generate 150 fresh E2E prompts for query-agent layered eval."""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

from app.evals.e2e_expect import build_e2e_expect  # noqa: E402
from app.evals.prompt_templates import generate_eval_pool, prompts_to_cases  # noqa: E402

DEFAULT_OUT = SERVICE_ROOT / "app" / "evals" / "e2e_query_agent_150.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=20260602)
    parser.add_argument("--count", type=int, default=150)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    pool = generate_eval_pool(seed=args.seed, per_category=40, min_total=200)
    cases = prompts_to_cases(pool)
    rng.shuffle(cases)
    selected = cases[: args.count]

    e2e_cases: list[dict[str, Any]] = []
    for i, case in enumerate(selected):
        e2e_cases.append(
            {
                "id": f"e2e_{args.seed}_{i+1:03d}",
                "category": case.get("category"),
                "prompt": case["prompt"],
                "source_id": case.get("id"),
                "expect": build_e2e_expect(case),
            }
        )

    by_cat: dict[str, int] = {}
    for c in e2e_cases:
        by_cat[c["category"]] = by_cat.get(c["category"], 0) + 1

    payload = {
        "description": "Layer 4 — E2E query agent eval (150 fresh NL prompts)",
        "seed": args.seed,
        "prompt_count": len(e2e_cases),
        "targets": {
            "final_pass_count": 135,
            "final_pass_rate": 0.9,
            "hallucinated_unsupported_facts": 0,
            "wrong_commute_destination_ranking": 0,
        },
        "by_category": by_cat,
        "cases": e2e_cases,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote {len(e2e_cases)} cases to {args.out}")


if __name__ == "__main__":
    main()
