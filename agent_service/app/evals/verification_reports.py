"""Markdown + JSON report writers for query-agent verification artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_e2e_markdown(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Query Agent E2E Verification Report",
        "",
        f"Generated: {summary.get('generated_at', '')}",
        "",
        "## Headline metrics",
        "",
        "```json",
        json.dumps(
            {k: v for k, v in summary.items() if k not in ("top_failures_detail", "by_category")},
            indent=2,
        ),
        "```",
        "",
        "## Category breakdown",
        "",
        "| Category | Total | Passed | Pass rate |",
        "|----------|-------|--------|-----------|",
    ]
    for cat, stats in sorted((summary.get("by_category") or {}).items()):
        total = stats.get("total", 0)
        passed = stats.get("passed", 0)
        rate = round(passed / total, 3) if total else 0
        lines.append(f"| {cat} | {total} | {passed} | {rate} |")

    confusion = summary.get("confusion_summary")
    if confusion:
        lines.extend(["", "## Confusion summary", "", "```json", json.dumps(confusion, indent=2), "```", ""])

    lines.extend(["", "## All cases", ""])
    for row in rows:
        lines.extend(_e2e_case_block(row))

    failures = summary.get("top_failures_detail") or []
    if failures:
        lines.extend(["", "## Top failures (detail)", ""])
        for row in failures:
            lines.extend(_e2e_case_block(row, heading_prefix="### FAIL"))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _e2e_case_block(row: dict[str, Any], *, heading_prefix: str = "###") -> list[str]:
    cid = row.get("id", "?")
    cat = row.get("category", "?")
    passed = row.get("passed")
    lines = [
        "",
        f"{heading_prefix} {cid} ({cat}) — **{'PASS' if passed else 'FAIL'}**",
        "",
        f"- **Expected category:** `{cat}`",
        f"- **Execution status:** `{row.get('execution_status', '?')}`",
        f"- **Trust gate:** `{row.get('trust_gate')}`" if row.get("trust_gate") else "- **Trust gate:** (none)",
        f"- **Answer LLM used:** {row.get('used_answer_llm')}",
        f"- **Plan validation pass:** {row.get('plan_validation_pass')}",
        f"- **Planner op accuracy (vs expect):** {row.get('planner_op_accuracy')}",
        "",
        "**Question:**",
        "",
        row.get("prompt", ""),
        "",
    ]
    if row.get("expect"):
        lines.extend(
            [
                "**Expected plan requirements:**",
                "",
                "```json",
                json.dumps(row["expect"], indent=2),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "**Final answer:**",
            "",
            row.get("final_answer") or "(none)",
            "",
        ]
    )
    if row.get("failure_reasons"):
        lines.append("**Failure reasons:**")
        for reason in row["failure_reasons"]:
            lines.append(f"- {reason}")
        lines.append("")
    for label, key in (
        ("Raw LLM plan", "raw_llm_plan"),
        ("Normalized plan", "normalized_plan"),
        ("QueryPlan (executed)", "actual_plan"),
    ):
        plan = row.get(key)
        if plan:
            lines.extend(
                [
                    f"**{label}:**",
                    "",
                    "```json",
                    json.dumps(plan, indent=2),
                    "```",
                    "",
                ]
            )
    return lines


def write_planner_markdown(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Query Agent Planner-Only Verification Report",
        "",
        f"Generated: {summary.get('generated_at', '')}",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(summary, indent=2),
        "```",
        "",
        "## Results by case",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"### {row.get('id')} ({row.get('category')}) — **{'PASS' if row.get('passed') else 'FAIL'}**",
                "",
                f"- Operation accuracy: {row.get('op_accuracy')}",
                f"- Town accuracy: {row.get('town_accuracy')}",
                f"- Field accuracy: {row.get('field_accuracy')}",
                f"- Repair attempts: {row.get('repair_count', 0)}",
                "",
                "**Prompt:**",
                "",
                row.get("prompt", ""),
                "",
            ]
        )
        if row.get("failure_reasons"):
            lines.append("**Failures:**")
            for f in row["failure_reasons"]:
                lines.append(f"- {f}")
            lines.append("")
        if row.get("actual_plan"):
            lines.extend(
                [
                    "**Actual plan:**",
                    "",
                    "```json",
                    json.dumps(row["actual_plan"], indent=2),
                    "```",
                    "",
                ]
            )
        if row.get("expect"):
            lines.extend(
                [
                    "**Expected (scoring spec):**",
                    "",
                    "```json",
                    json.dumps(row["expect"], indent=2),
                    "```",
                    "",
                ]
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_trust_gate_markdown(path: Path, summary: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    lines = [
        "# Query Agent Trust-Gate Verification Report",
        "",
        f"Generated: {summary.get('generated_at', '')}",
        "",
        "## Summary",
        "",
        "```json",
        json.dumps(summary, indent=2),
        "```",
        "",
        "## Cases",
        "",
    ]
    for row in rows:
        lines.extend(
            [
                f"### {row.get('id')} ({row.get('category')}) — **{'PASS' if row.get('passed') else 'FAIL'}**",
                "",
                f"- Expected gate: `{row.get('expect_gate')}`",
                f"- Actual gate: `{row.get('actual_gate')}`",
                f"- Blocks pipeline: {row.get('blocks')}",
                f"- Execution status (full agent): `{row.get('execution_status', 'n/a')}`",
                f"- Answer LLM used (full agent): {row.get('used_answer_llm', 'n/a')}",
                "",
                "**Prompt:**",
                "",
                row.get("prompt", ""),
                "",
            ]
        )
        if row.get("failure_reason"):
            lines.append(f"**Failure:** {row['failure_reason']}\n")
        if row.get("plan"):
            lines.extend(
                [
                    "**Plan:**",
                    "",
                    "```json",
                    json.dumps(row["plan"], indent=2),
                    "```",
                    "",
                ]
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
