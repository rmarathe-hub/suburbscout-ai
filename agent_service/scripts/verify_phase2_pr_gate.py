#!/usr/bin/env python3
"""Phase 2 Step 5 — fast PR regression gate (offline <2 min; +live smoke optional).

Default (offline):
  - Core unit tests (normalizer, fallback, trust, golden executor, query_plan)
  - Step 4 hardening checks (verify_phase2_step4, without duplicate unittest block)
  - Trust gate plan-level eval (19 cases, no Azure)
  - Executor golden manifest (14 cases, no LLM)

With --live (adds ~15–45s):
  - 3 Azure smoke prompts (app/evals/pr_gate_live_smoke.json)

Usage:
  python scripts/verify_phase2_pr_gate.py
  python scripts/verify_phase2_pr_gate.py --live
  SKIP_LIVE_AZURE_CHECKS=1 python scripts/verify_phase2_pr_gate.py  # offline only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

RESULTS_DIR = SERVICE_ROOT / "app" / "evals" / "results"
LIVE_SMOKE_PATH = SERVICE_ROOT / "app" / "evals" / "pr_gate_live_smoke.json"
TRUST_EVAL_PATH = SERVICE_ROOT / "app" / "evals" / "trust_gate_plan_eval.json"

UNITTEST_MODULES = (
    "tests.test_query_plan",
    "tests.test_plan_normalizer",
    "tests.test_plan_fallback",
    "tests.test_plan_expect_towns",
    "tests.test_plan_trust_gates",
    "tests.test_golden_plans",
    "tests.test_executor_golden_extended",
    "tests.test_planner_eval_offline",
    "tests.test_trust_gate_layer",
    "tests.test_query_agent_phase7",
)


@dataclass
class StepResult:
    name: str
    passed: bool
    elapsed_ms: int
    detail: str = ""


@dataclass
class GateReport:
    steps: list[StepResult] = field(default_factory=list)
    live_smoke_summary: dict[str, Any] | None = None

    def add(self, name: str, passed: bool, elapsed_ms: int, detail: str = "") -> None:
        self.steps.append(StepResult(name, passed, elapsed_ms, detail))
        mark = "PASS" if passed else "FAIL"
        suffix = f" — {detail}" if detail else ""
        print(f"  {mark}: {name} ({elapsed_ms}ms){suffix}")

    @property
    def ok(self) -> bool:
        return all(s.passed for s in self.steps)


def _run_subprocess(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or SERVICE_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def step_unittests(report: GateReport) -> None:
    t0 = time.perf_counter()
    cmd = [sys.executable, "-m", "unittest", *UNITTEST_MODULES]
    code, out = _run_subprocess(cmd)
    elapsed = int((time.perf_counter() - t0) * 1000)
    if code != 0:
        tail = "\n".join(out.strip().splitlines()[-20:])
        report.add("unit tests", False, elapsed, tail[:500])
    else:
        report.add("unit tests", True, elapsed, f"{len(UNITTEST_MODULES)} modules")


def step_hardening_checks(report: GateReport) -> None:
    """Step 4 structural checks without re-running the unittest block inside step4."""
    t0 = time.perf_counter()
    try:
        import inspect

        from app import plan_normalizer, query_agent_audit
        from app.evals.planner_eval_scoring import score_plan_against_expect
        from app.plan_normalizer import normalize_planned_query
        from app.query_patterns import extract_pull_up_town_name
        from app.query_plan import LookupOp, validate_plan

        src = inspect.getsource(plan_normalizer.normalize_planned_query)
        if src.find("_rewrite_hard_unsupported") > src.find("_rewrite_pull_up_lookup"):
            raise AssertionError("normalizer order wrong")

        plan = normalize_planned_query(
            "Open Reading.",
            validate_plan({"ops": [{"op": "membership", "town": "North Reading"}]}),
        )
        if not isinstance(plan.ops[0], LookupOp) or plan.ops[0].items[0].town != "Reading":
            raise AssertionError("Reading pull-up disambiguation failed")

        sig = inspect.signature(query_agent_audit.save_query_agent_turn)
        for param in ("request_id", "latency_ms", "raw_plan"):
            if param not in sig.parameters:
                raise AssertionError(f"audit missing {param}")

        score = score_plan_against_expect(
            validate_plan(
                {
                    "ops": [
                        {
                            "op": "lookup",
                            "items": [{"town": "Reading", "field": "summary"}],
                        }
                    ]
                }
            ),
            {"expected_town": "Reading", "forbidden_towns": ["North Reading"]},
        )
        if not score["passed"]:
            raise AssertionError(str(score["failure_reasons"]))

        if extract_pull_up_town_name("Pull up North Reading.") != "North Reading":
            raise AssertionError("North Reading pull-up extract failed")

        elapsed = int((time.perf_counter() - t0) * 1000)
        report.add("hardening checks", True, elapsed)
    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        report.add("hardening checks", False, elapsed, str(exc))


def step_trust_gate_offline(report: GateReport) -> None:
    t0 = time.perf_counter()
    out_path = RESULTS_DIR / "pr_gate_trust_gate_latest.json"
    code, out = _run_subprocess(
        [
            sys.executable,
            "scripts/run_trust_gate_eval.py",
            "--eval",
            str(TRUST_EVAL_PATH),
            "--out",
            str(out_path),
        ],
    )
    elapsed = int((time.perf_counter() - t0) * 1000)
    if code != 0:
        report.add("trust gate (offline)", False, elapsed, out[-400:])
        return
    try:
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        summary = payload.get("summary") or {}
        passed = int(summary.get("passed", 0))
        total = int(summary.get("total", 0))
        detail = f"{passed}/{total}"
        report.add("trust gate (offline)", passed == total and total > 0, elapsed, detail)
    except Exception as exc:
        report.add("trust gate (offline)", False, elapsed, str(exc))


async def _run_executor_golden() -> dict[str, Any]:
    from app.plan_executor import execute_plan_async
    from app.query_plan import PlanValidationError, validate_plan
    from tests.golden_plan_assertions import assert_golden_case, load_manifest, load_plan_file

    manifest = load_manifest()
    cases = manifest.get("cases") or []
    skip_semantic = os.getenv("ENABLE_SEMANTIC_GOLDEN", "").lower() not in (
        "1",
        "true",
        "yes",
    )
    failures: list[str] = []
    ran = 0
    for case in cases:
        if case.get("requires_live_embeddings") and skip_semantic:
            continue
        ran += 1
        if case.get("expect_validation_error"):
            plan_data = load_plan_file(case["plan_file"])
            try:
                validate_plan(plan_data)
                failures.append(f"{case['id']}: expected validation error but plan validated")
            except (PlanValidationError, Exception):
                pass
            continue
        plan_data = load_plan_file(case["plan_file"])
        result = await execute_plan_async(plan_data)
        failures.extend(assert_golden_case(case, result))
    return {
        "total_cases_run": ran,
        "failures": failures,
        "met_target_100pct": len(failures) == 0,
    }


async def step_executor_golden(report: GateReport) -> None:
    t0 = time.perf_counter()
    try:
        result = await _run_executor_golden()
        elapsed = int((time.perf_counter() - t0) * 1000)
        detail = f"{result.get('total_cases_run')}/{result.get('total_cases_run')} — failures={len(result.get('failures') or [])}"
        report.add(
            "executor golden",
            bool(result.get("met_target_100pct")),
            elapsed,
            detail,
        )
    except Exception as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        report.add("executor golden", False, elapsed, str(exc))


async def step_live_smoke(report: GateReport) -> None:
    t0 = time.perf_counter()
    if os.getenv("SKIP_LIVE_AZURE_CHECKS", "").lower() in ("1", "true", "yes"):
        elapsed = int((time.perf_counter() - t0) * 1000)
        report.add("live smoke (3)", True, elapsed, "SKIP_LIVE_AZURE_CHECKS")
        return

    from app import config
    from app.evals.layered_eval_checks import evaluate_e2e_case
    from app.query_agent import handle_query_v2, query_agent_available

    if not query_agent_available():
        elapsed = int((time.perf_counter() - t0) * 1000)
        report.add("live smoke (3)", False, elapsed, "query_agent_available() false")
        return

    config.USE_LLM_QUERY_AGENT = True
    payload_file = json.loads(LIVE_SMOKE_PATH.read_text(encoding="utf-8"))
    cases = payload_file.get("cases") or []
    rows: list[dict[str, Any]] = []
    failures = 0
    for case in cases:
        prompt = case["prompt"]
        try:
            payload = await handle_query_v2(prompt, save_searches=False)
            passed, reasons = evaluate_e2e_case(case, payload)
            rows.append(
                {
                    "id": case.get("id"),
                    "passed": passed,
                    "execution_status": payload.get("execution_status"),
                    "plan_ops": [
                        o.get("op") for o in (payload.get("plan") or {}).get("ops") or []
                    ],
                    "failure_reasons": reasons,
                }
            )
            if not passed:
                failures += 1
        except Exception as exc:
            failures += 1
            rows.append({"id": case.get("id"), "passed": False, "error": str(exc)})

    elapsed = int((time.perf_counter() - t0) * 1000)
    detail = f"{len(cases) - failures}/{len(cases)} passed"
    report.add("live smoke (3)", failures == 0, elapsed, detail)
    report.live_smoke_summary = {
        "cases": rows,
        "passed": len(cases) - failures,
        "total": len(cases),
    }


async def main_async(*, live: bool) -> int:
    print("=== Phase 2 PR gate ===\n")
    started = time.perf_counter()
    report = GateReport()

    print("Offline:")
    step_unittests(report)
    step_hardening_checks(report)
    step_trust_gate_offline(report)
    await step_executor_golden(report)

    if live:
        print("\nLive Azure:")
        await step_live_smoke(report)

    total_ms = int((time.perf_counter() - started) * 1000)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = RESULTS_DIR / f"pr_gate_{ts}.json"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "timestamp": ts,
        "total_elapsed_ms": total_ms,
        "live_included": live,
        "passed": report.ok,
        "steps": [
            {"name": s.name, "passed": s.passed, "elapsed_ms": s.elapsed_ms, "detail": s.detail}
            for s in report.steps
        ],
        "live_smoke": report.live_smoke_summary,
    }
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\nTotal: {total_ms}ms")
    print(f"Wrote {out_path}")
    if report.ok:
        print("\n=== Phase 2 PR gate: PASSED ===")
        return 0
    print("\n=== Phase 2 PR gate: FAILED ===")
    failed = [s.name for s in report.steps if not s.passed]
    print("Failed:", ", ".join(failed))
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 fast PR regression gate")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run 3 live Azure smoke prompts after offline gate",
    )
    args = parser.parse_args()
    live = args.live and os.getenv("SKIP_LIVE_AZURE_CHECKS", "").lower() not in (
        "1",
        "true",
        "yes",
    )
    raise SystemExit(asyncio.run(main_async(live=live)))


if __name__ == "__main__":
    main()
