#!/usr/bin/env python3
"""Run holdout 150 prompts and produce scored results for external review."""

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
sys.path.insert(0, str(SERVICE_ROOT / "scripts"))

DEFAULT_PROMPTS = SERVICE_ROOT / "app" / "evals" / "holdout_150_prompts.json"
DEFAULT_OUT_DIR = SERVICE_ROOT / "app" / "evals" / "results"
DEFAULT_OUT_PREFIX = "holdout_150"


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


def _tools_for_route(intent: str | None) -> list[str]:
    mapping = {
        "lookup_single_town": ["get_town_facts_tool"],
        "compare_towns": ["compare_suburbs_tool"],
        "recommend_structured": ["parse_preferences_tool", "rank_suburbs_tool", "explain_results_tool"],
        "recommend_semantic": ["semantic_town_search_tool", "rank_suburbs_tool", "explain_results_tool"],
        "explain_ranking": ["explain_results_tool"],
        "data_limit_question": [],
        "needs_clarification": [],
        "unsupported": [],
    }
    return mapping.get(intent or "", [])


def _failure_reason(
    *,
    expected: str,
    actual: str,
    strict_valid: bool | None,
    validation_errors: list[str],
    prompt: str,
    row: dict[str, Any],
) -> str | None:
    if strict_valid is False:
        return "; ".join(validation_errors) if validation_errors else "strict validation failed"
    if not _intent_compatible(expected, actual):
        return f"wrong_intent: expected {expected}, got {actual}"

    top = row.get("top_matches_summary") or []
    if expected == "lookup_single_town" and top and not top[0].get("no_matches"):
        return "lookup_returned_ranked_recommendations"

    if expected == "compare_towns":
        comp = row.get("comparison") or {}
        if top and not top[0].get("no_matches"):
            return "compare_returned_ranked_recommendations"
        if comp.get("error") and "not in suburbs" in str(comp.get("error")).lower():
            return None  # valid not-in-dataset compare error

    if expected == "refuse_out_of_scope" and top and not top[0].get("no_matches"):
        return "refusal_returned_ranked_recommendations"

    if expected in ("recommend_structured", "recommend_semantic") and top:
        if top[0].get("no_matches"):
            return None
        if "coastal" in prompt.lower() or "coast" in prompt.lower() or "ocean" in prompt.lower():
            for match in top[:3]:
                if match.get("is_coastal") is False:
                    return f"coastal_filter_violation: {match.get('name')} not coastal"

    if expected == "recommend_structured" and "high-crime" in prompt.lower() or "risky" in prompt.lower():
        if top and not top[0].get("no_matches"):
            name = top[0].get("name")
            if name in ("Sharon", "Weston", "Wayland"):
                return f"inverted_pref_defaulted_to_safe: top={name}"

    return None


async def run_holdout(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from eval_query_agent import run_query_agent_prompt
    from app.plan_trust_gates import plan_to_query_route
    from app.query_plan import validate_plan

    from run_150_quality_check import _compact_response

    results: list[dict[str, Any]] = []
    total = len(cases)
    for i, case in enumerate(cases, start=1):
        print(f"[{i}/{total}] {case['id']}: {case['prompt'][:70]}...", flush=True)
        payload = await run_query_agent_prompt(case["prompt"], save_searches=False)
        row = _compact_response(case, payload)
        plan_raw = payload.get("plan")
        if plan_raw:
            try:
                plan = validate_plan(plan_raw)
                row["route_intent"] = plan_to_query_route(case["prompt"], plan).intent
            except Exception:
                pass
        row["route_intent"] = row.get("route_intent") or payload.get("response", {}).get("route_intent")
        expected = case.get("expected_intent", "")
        actual = row.get("route_intent") or ""
        validation = row.get("validation") or {}
        strict_valid = validation.get("valid")
        errors = validation.get("errors") or []

        failure = _failure_reason(
            expected=expected,
            actual=actual,
            strict_valid=strict_valid,
            validation_errors=errors,
            prompt=case["prompt"],
            row=row,
        )
        passed = failure is None and strict_valid is not False

        row.update({
            "expected_intent": expected,
            "actual_intent": actual,
            "intent_match": _intent_compatible(expected, actual),
            "tools_used": _tools_for_route(actual),
            "passed": passed,
            "failure_reason": failure,
            "classification_source": (payload.get("route") or {}).get("classification_source"),
            "python_confidence": (payload.get("route") or {}).get("python_confidence"),
            "python_intent": (payload.get("route") or {}).get("python_intent"),
            "llm_fallback_used": (payload.get("route") or {}).get("llm_fallback_used"),
        })
        results.append(row)
    return results


def _summary_lines(results: list[dict[str, Any]]) -> list[str]:
    passed = sum(1 for r in results if r.get("passed"))
    total = len(results)
    strict = sum(1 for r in results if r.get("strict_valid") is True)
    intent_ok = sum(1 for r in results if r.get("intent_match"))
    unsupported = sum(1 for r in results if r.get("actual_intent") == "unsupported")
    llm_used = sum(1 for r in results if r.get("llm_fallback_used"))

    lines = [
        "# SuburbScout Holdout 150 — Test Results",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Total: {total} prompts",
        "",
        "## Summary",
        f"- Holdout pass (intent + rules + strict valid): {passed}/{total} ({passed/total:.1%})",
        f"- Strict validator pass: {strict}/{total} ({strict/total:.1%})",
        f"- Expected intent match: {intent_ok}/{total} ({intent_ok/total:.1%})",
        f"- Unsupported routes: {unsupported}",
        f"- LLM classify fallback used: {llm_used}/{total} ({llm_used/total:.1%})",
        "",
        "## By category",
        "",
    ]

    by_cat: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        by_cat.setdefault(r.get("category", "?"), []).append(r)

    for cat in sorted(by_cat):
        rows = by_cat[cat]
        p = sum(1 for r in rows if r.get("passed"))
        lines.append(f"- {rows[0].get('category_label', cat)}: {p}/{len(rows)} passed")

    failed = [r for r in results if not r.get("passed")]
    if failed:
        lines.extend(["", "## Top failures (up to 10)", ""])
        for r in failed[:10]:
            lines.append(
                f"- **{r['id']}** | expected={r.get('expected_intent')} "
                f"actual={r.get('actual_intent')} | source={r.get('classification_source')} "
                f"llm={r.get('llm_fallback_used')} | {r.get('failure_reason')}"
            )
            lines.append(f"  Prompt: {r.get('prompt')}")
        lines.extend(["", "## All failed prompts", ""])
        for r in failed:
            lines.append(
                f"- **{r['id']}** | expected={r.get('expected_intent')} "
                f"actual={r.get('actual_intent')} | {r.get('failure_reason')}"
            )
            lines.append(f"  Prompt: {r.get('prompt')}")
            lines.append(f"  Response: {(r.get('final_recommendation') or '')[:200]}")
            lines.append("")

    lines.extend(["", "## Full per-prompt log", ""])
    lines.append(
        "| id | prompt | expected_intent | actual_intent | tools_used | passed | failure_reason |"
    )
    lines.append("|---|---|---|---|---|---|---|")
    for r in results:
        prompt = (r.get("prompt") or "").replace("|", "\\|")[:80]
        reason = (r.get("failure_reason") or "").replace("|", "\\|")[:60]
        tools = ", ".join(r.get("tools_used") or [])
        lines.append(
            f"| {r['id']} | {prompt} | {r.get('expected_intent')} | "
            f"{r.get('actual_intent')} | {tools} | {r.get('passed')} | {reason} |"
        )

    return lines


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run holdout 150 prompt suite.")
    parser.add_argument("--prompts", type=Path, default=DEFAULT_PROMPTS)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--out-prefix", type=str, default=DEFAULT_OUT_PREFIX)
    args = parser.parse_args(argv)

    if not args.prompts.exists():
        print("Building holdout prompts...", file=sys.stderr)
        import subprocess
        subprocess.run([sys.executable, str(SERVICE_ROOT / "scripts" / "build_holdout_150.py")], check=True)

    with open(args.prompts, encoding="utf-8") as f:
        cases = json.load(f)["cases"]

    print(f"=== Holdout 150 ({len(cases)} prompts) ===\n")
    results = asyncio.run(run_holdout(cases))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = args.out_prefix
    json_path = args.out_dir / f"{prefix}_{stamp}.json"
    md_path = args.out_dir / f"{prefix}_{stamp}.md"
    txt_path = args.out_dir / f"{prefix}_{stamp}_chatgpt.txt"

    summary = _summary_lines(results)
    intent_ok = sum(1 for r in results if r.get("intent_match"))
    unsupported = sum(1 for r in results if r.get("actual_intent") == "unsupported")
    llm_used = sum(1 for r in results if r.get("llm_fallback_used"))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prompt_count": len(results),
        "passed": sum(1 for r in results if r.get("passed")),
        "intent_match": intent_ok,
        "unsupported_count": unsupported,
        "llm_fallback_count": llm_used,
        "results": results,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text("\n".join(summary), encoding="utf-8")

    # Plain-text block easy to copy into ChatGPT
    txt_lines = [
        "SUBURBSCOUT HOLDOUT 150 RESULTS",
        f"Date: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Pass rate: {payload['passed']}/{len(results)} ({payload['passed']/len(results):.1%})",
        "",
    ]
    for r in results:
        txt_lines.append(f"ID: {r['id']}")
        txt_lines.append(f"PROMPT: {r['prompt']}")
        txt_lines.append(f"EXPECTED_INTENT: {r.get('expected_intent')}")
        txt_lines.append(f"ACTUAL_INTENT: {r.get('actual_intent')}")
        txt_lines.append(f"TOOLS_USED: {', '.join(r.get('tools_used') or [])}")
        txt_lines.append(f"PASSED: {r.get('passed')}")
        txt_lines.append(f"FAILURE_REASON: {r.get('failure_reason') or 'none'}")
        txt_lines.append(f"RESPONSE: {r.get('final_recommendation') or '(none)'}")
        top = r.get("top_matches_summary") or []
        if top:
            names = [m.get("name") or "no_match" for m in top[:3]]
            txt_lines.append(f"TOP_MATCHES: {', '.join(str(n) for n in names)}")
        txt_lines.append("---")
    txt_path.write_text("\n".join(txt_lines), encoding="utf-8")

    passed = payload["passed"]
    print()
    print(f"Holdout pass: {passed}/{len(results)} ({passed/len(results):.1%})")
    print(f"Wrote: {json_path}")
    print(f"Wrote: {md_path}")
    print(f"Wrote: {txt_path}  (copy this into ChatGPT)")


if __name__ == "__main__":
    main()
