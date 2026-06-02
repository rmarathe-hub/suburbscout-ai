#!/usr/bin/env python3
"""Export layered eval results as a shareable Q&A report (markdown + plain text)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))

RESULTS_DIR = SERVICE_ROOT / "app" / "evals" / "results"
DEFAULT_E2E = SERVICE_ROOT / "app" / "evals" / "e2e_query_agent_150.json"


def _format_plan(plan: dict[str, Any] | None) -> str:
    if not plan:
        return "(no plan)"
    return json.dumps(plan, indent=2)


def _row_to_qa_block(row: dict[str, Any], *, include_plan: bool = True) -> list[str]:
    lines: list[str] = []
    case_id = row.get("id", "?")
    category = row.get("category", "?")
    prompt = row.get("prompt", "")
    passed = row.get("passed")
    status = row.get("execution_status") or row.get("actual_execution_status")
    gate = row.get("trust_gate")
    used_llm = row.get("used_answer_llm")

    lines.append(f"### {case_id} ({category})")
    if passed is not None:
        lines.append(f"**Passed:** {'yes' if passed else 'no'}")
    if status:
        lines.append(f"**Execution status:** `{status}`")
    if gate:
        lines.append(f"**Trust gate:** `{gate}`")
    if used_llm is not None:
        lines.append(f"**Answer LLM used:** {used_llm}")

    lines.append("")
    lines.append("**Question:**")
    lines.append(prompt)
    lines.append("")

    answer = row.get("final_answer") or row.get("final_snippet") or ""
    if row.get("response"):
        answer = (row["response"] or {}).get("final_recommendation") or answer

    lines.append("**Answer:**")
    lines.append(answer.strip() if answer else "(no answer text)")
    lines.append("")

    if include_plan and row.get("actual_plan"):
        lines.append("**QueryPlan (actual):**")
        lines.append("```json")
        lines.append(_format_plan(row["actual_plan"]))
        lines.append("```")
        lines.append("")
    elif include_plan and row.get("expected_plan"):
        lines.append("**QueryPlan (expected):**")
        lines.append("```json")
        lines.append(_format_plan(row["expected_plan"]))
        lines.append("```")
        lines.append("")

    failures = row.get("failure_reasons") or []
    if failures:
        lines.append("**Failures:**")
        for f in failures:
            lines.append(f"- {f}")
        lines.append("")

    lines.append("---")
    lines.append("")
    return lines


async def _run_e2e_rows(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from app import config
    from app.query_agent import handle_query_v2, query_agent_available

    if not query_agent_available():
        raise SystemExit(
            "Query agent unavailable. Set USE_LLM_QUERY_AGENT=true and Azure credentials in .env"
        )

    config.USE_LLM_QUERY_AGENT = True
    rows: list[dict[str, Any]] = []
    for i, case in enumerate(cases, 1):
        prompt = case["prompt"]
        print(f"  [{i}/{len(cases)}] {case.get('id', '?')} …", flush=True)
        try:
            payload = await handle_query_v2(prompt, save_searches=False)
            response = payload.get("response") or {}
            rows.append(
                {
                    **case,
                    "execution_status": payload.get("execution_status"),
                    "trust_gate": payload.get("trust_gate"),
                    "used_answer_llm": payload.get("used_answer_llm"),
                    "actual_plan": payload.get("plan"),
                    "final_answer": response.get("final_recommendation", ""),
                    "response": response,
                }
            )
        except Exception as exc:
            rows.append(
                {
                    **case,
                    "execution_status": "error",
                    "final_answer": f"Pipeline error: {exc}",
                    "failure_reasons": [str(exc)],
                    "passed": False,
                }
            )
    return rows


def _load_planner_fixture_rows(limit: int | None) -> list[dict[str, Any]]:
    manifest = json.loads(
        (SERVICE_ROOT / "app" / "evals" / "planner_eval_100.json").read_text(encoding="utf-8")
    )
    cases = manifest.get("cases") or []
    if limit:
        cases = cases[:limit]
    rows: list[dict[str, Any]] = []
    for case in cases:
        plan_path = SERVICE_ROOT / case["plan_file"]
        expected = json.loads(plan_path.read_text(encoding="utf-8"))
        rows.append(
            {
                **case,
                "final_answer": (
                    "(Planner-only fixture — run `python scripts/run_planner_eval.py` "
                    "without --offline for live LLM plans.)"
                ),
                "expected_plan": expected,
                "execution_status": "fixture",
            }
        )
    return rows


def _write_report(
    *,
    title: str,
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
    out_md: Path,
    out_txt: Path,
    include_plan: bool,
) -> None:
    md: list[str] = [
        f"# {title}",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(summary, indent=2),
        "```",
        "",
        "## Questions and answers",
        "",
    ]
    for row in rows:
        md.extend(_row_to_qa_block(row, include_plan=include_plan))

    txt_lines: list[str] = [
        title,
        "=" * len(title),
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "SUMMARY",
        json.dumps(summary, indent=2),
        "",
        "QUESTIONS AND ANSWERS",
        "=" * 40,
        "",
    ]
    for row in rows:
        txt_lines.append(f"[{row.get('id')}] ({row.get('category')})")
        if row.get("passed") is not None:
            txt_lines.append(f"Passed: {row.get('passed')}")
        if row.get("execution_status"):
            txt_lines.append(f"Status: {row.get('execution_status')}")
        txt_lines.append("")
        txt_lines.append("QUESTION:")
        txt_lines.append(row.get("prompt", ""))
        txt_lines.append("")
        answer = row.get("final_answer") or ""
        if row.get("response"):
            answer = (row["response"] or {}).get("final_recommendation") or answer
        txt_lines.append("ANSWER:")
        txt_lines.append(answer.strip() or "(no answer)")
        txt_lines.append("")
        txt_lines.append("-" * 40)
        txt_lines.append("")

    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(md), encoding="utf-8")
    out_txt.write_text("\n".join(txt_lines), encoding="utf-8")


async def main_async(args: argparse.Namespace) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    all_rows: list[dict[str, Any]] = []

    if args.mode in ("e2e", "all"):
        e2e_path = args.e2e or DEFAULT_E2E
        if not e2e_path.exists():
            raise SystemExit(f"Missing {e2e_path}. Run: python scripts/generate_e2e_150.py")
        payload = json.loads(e2e_path.read_text(encoding="utf-8"))
        cases = payload.get("cases") or []
        if args.limit:
            cases = cases[: args.limit]
        print(f"Running E2E on {len(cases)} prompts …")
        e2e_rows = await _run_e2e_rows(cases)
        for r in e2e_rows:
            r["section"] = "e2e"
        all_rows.extend(e2e_rows)

        e2e_json = RESULTS_DIR / f"e2e_qa_run_{ts}.json"
        e2e_json.write_text(json.dumps({"results": e2e_rows}, indent=2), encoding="utf-8")
        print(f"Wrote raw JSON: {e2e_json}")

    if args.mode in ("planner", "all") and not args.e2e_only:
        planner_rows = _load_planner_fixture_rows(args.planner_limit)
        for r in planner_rows:
            r["section"] = "planner_fixture"
        all_rows = planner_rows + all_rows if args.mode == "all" else planner_rows

    summary = {
        "mode": args.mode,
        "total": len(all_rows),
        "with_answers": sum(
            1
            for r in all_rows
            if r.get("final_answer")
            and "Planner-only fixture" not in str(r.get("final_answer", ""))
        ),
    }

    stem = args.out_stem or f"eval_qa_report_{ts}"
    out_md = RESULTS_DIR / f"{stem}.md"
    out_txt = RESULTS_DIR / f"{stem}.txt"
    _write_report(
        title="SuburbScout Query Agent — Eval Q&A Report",
        summary=summary,
        rows=all_rows,
        out_md=out_md,
        out_txt=out_txt,
        include_plan=args.include_plan,
    )
    print(f"\nShareable reports written:")
    print(f"  {out_md}")
    print(f"  {out_txt}")


def _export_from_json(json_path: Path, out_stem: str, include_plan: bool) -> None:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    rows = payload.get("results") or []
    summary = payload.get("summary") or {"total": len(rows), "source": str(json_path)}
    stem = out_stem
    out_md = RESULTS_DIR / f"{stem}.md"
    out_txt = RESULTS_DIR / f"{stem}.txt"
    _write_report(
        title="SuburbScout Query Agent — Eval Q&A Report",
        summary=summary,
        rows=rows,
        out_md=out_md,
        out_txt=out_txt,
        include_plan=include_plan,
    )
    print(f"\nShareable reports written:\n  {out_md}\n  {out_txt}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export eval Q&A for ChatGPT review")
    parser.add_argument(
        "--mode",
        choices=("e2e", "planner", "all"),
        default="e2e",
        help="e2e=live Q&A; planner=fixture prompts+expected plans; all=both",
    )
    parser.add_argument("--limit", type=int, default=30, help="E2E prompt count (default 30)")
    parser.add_argument("--planner-limit", type=int, default=20, help="Planner fixtures in --mode all")
    parser.add_argument("--e2e", type=Path, default=DEFAULT_E2E)
    parser.add_argument("--e2e-only", action="store_true", help="Alias for --mode e2e")
    parser.add_argument("--out-stem", type=str, default=None)
    parser.add_argument("--no-plan", action="store_true", help="Omit QueryPlan JSON from report")
    parser.add_argument(
        "--from-json",
        type=Path,
        default=None,
        help="Build report from existing eval JSON (skip live run)",
    )
    args = parser.parse_args()
    if args.from_json:
        stem = args.out_stem or args.from_json.stem
        _export_from_json(args.from_json, stem, include_plan=not args.no_plan)
        return
    if args.e2e_only:
        args.mode = "e2e"
    args.include_plan = not args.no_plan
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
