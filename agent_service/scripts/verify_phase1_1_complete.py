#!/usr/bin/env python3
"""Phase 1.1 completion check — runs Steps 1–8 verification scripts."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent

STEP_SCRIPTS: tuple[tuple[int, str], ...] = (
    (1, "verify_phase1_1_step1.py"),
    (2, "verify_phase1_1_step2.py"),
    (3, "verify_phase1_1_step3.py"),
    (4, "verify_phase1_1_step4.py"),
    (5, "verify_phase1_1_step5.py"),
    (6, "verify_phase1_1_step6.py"),
    (7, "verify_phase1_1_step7.py"),
    (8, "verify_phase1_1_step8.py"),
)


def _run_step(step: int, script_name: str, *, python: str) -> tuple[bool, str]:
    script = SCRIPTS_DIR / script_name
    if not script.exists():
        return False, f"missing script {script}"

    print(f"\n{'=' * 72}")
    print(f"Phase 1.1 Step {step}: {script_name}")
    print(f"{'=' * 72}")

    result = subprocess.run(
        [python, str(script)],
        cwd=str(SERVICE_ROOT),
        text=True,
        capture_output=False,
    )
    if result.returncode == 0:
        return True, "PASSED"
    return False, f"exit code {result.returncode}"


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run all Phase 1.1 verification scripts (Steps 1–8).",
    )
    parser.add_argument(
        "--from-step",
        type=int,
        default=1,
        choices=range(1, 9),
        help="Start at this step (default: 1).",
    )
    parser.add_argument(
        "--to-step",
        type=int,
        default=8,
        choices=range(1, 9),
        help="Stop at this step (default: 8).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    if args.from_step > args.to_step:
        print("Error: --from-step must be <= --to-step.", file=sys.stderr)
        sys.exit(2)

    python = sys.executable
    print("=== Phase 1.1 Completion Verification ===")
    print(f"Service root: {SERVICE_ROOT}")
    print(f"Python: {python}")
    print(f"Steps: {args.from_step} → {args.to_step}")

    results: list[tuple[int, str, bool, str]] = []
    for step, script in STEP_SCRIPTS:
        if step < args.from_step or step > args.to_step:
            continue
        ok, detail = _run_step(step, script, python=python)
        results.append((step, script, ok, detail))
        if not ok:
            break

    print(f"\n{'=' * 72}")
    print("Summary")
    print(f"{'=' * 72}")
    for step, script, ok, detail in results:
        status = "PASS" if ok else "FAIL"
        print(f"  Step {step} ({script}): {status} — {detail}")

    failed = [r for r in results if not r[2]]
    if failed:
        print("\nPhase 1.1 completion: FAILED")
        sys.exit(1)

    print("\nPhase 1.1 completion: PASSED")
    print("\nQuick manual checks (optional):")
    print("  python -m app.chat")
    print("  python scripts/run_quality_evals.py --category lookup")
    print("\nPhase 1.1 is complete. Next: Phase 2 (FastAPI wrapper) when ready.")


if __name__ == "__main__":
    main()
