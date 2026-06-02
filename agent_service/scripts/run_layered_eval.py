#!/usr/bin/env python3
"""Run all QueryPlan pipeline eval layers (offline + optional live LLM)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str], *, label: str) -> int:
    print(f"\n{'=' * 60}\n{label}\n{'=' * 60}")
    result = subprocess.run(cmd, cwd=SERVICE_ROOT)
    return result.returncode


def main() -> None:
    parser = argparse.ArgumentParser(description="Layered QueryPlan eval suite")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run Layer 1 planner + Layer 4 E2E with live Azure LLM",
    )
    parser.add_argument(
        "--skip-golden",
        action="store_true",
        help="Skip Layer 2 unittest golden executor",
    )
    args = parser.parse_args()

    py = sys.executable
    codes: list[int] = []

    # Layer 1 offline (fixture self-check)
    codes.append(
        _run(
            [py, "scripts/run_planner_eval.py", "--offline"],
            label="Layer 1 — Planner fixtures (offline)",
        )
    )

    # Layer 2 golden executor
    if not args.skip_golden:
        codes.append(
            _run(
                [
                    py,
                    "-m",
                    "unittest",
                    "tests.test_golden_plans",
                    "tests.test_executor_golden_extended",
                    "-v",
                ],
                label="Layer 2 — Executor golden plans",
            )
        )

    # Layer 3 trust gates
    codes.append(
        _run(
            [py, "scripts/run_trust_gate_eval.py"],
            label="Layer 3 — Trust gates (plan-level)",
        )
    )
    codes.append(
        _run(
            [py, "scripts/run_trust_gate_eval.py", "--full-agent"],
            label="Layer 3b — Trust gates + answer LLM skip",
        )
    )

    if args.live:
        codes.append(
            _run(
                [py, "scripts/run_planner_eval.py"],
                label="Layer 1 — Planner (live LLM, 100 prompts)",
            )
        )
        e2e = SERVICE_ROOT / "app" / "evals" / "e2e_query_agent_150.json"
        if not e2e.exists():
            _run([py, "scripts/generate_e2e_150.py"], label="Generate E2E 150")
        codes.append(
            _run(
                [py, "scripts/run_e2e_query_agent_eval.py"],
                label="Layer 4 — E2E (live LLM, 150 prompts)",
            )
        )
    else:
        print("\n(Skipping live LLM layers — pass --live to run planner + E2E)")

    codes.append(
        _run(
            [py, "-m", "unittest", "tests.test_planner_eval_offline", "tests.test_trust_gate_layer", "-v"],
            label="Unit tests — layered eval helpers",
        )
    )

    if any(c != 0 for c in codes):
        sys.exit(1)
    print("\nAll layered eval steps passed.")


if __name__ == "__main__":
    main()
