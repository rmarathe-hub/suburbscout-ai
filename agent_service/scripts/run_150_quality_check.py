#!/usr/bin/env python3
"""Run the 150-prompt quality check and capture orchestrator responses for review.

Does NOT pass/fail — saves full responses so you can inspect behavior manually.
"""

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

DEFAULT_PROMPTS = SERVICE_ROOT / "app" / "evals" / "quality_check_150_prompts.json"
DEFAULT_OUT_DIR = SERVICE_ROOT / "app" / "evals" / "results"


def load_cases(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    cases = payload.get("cases", payload)
    if not isinstance(cases, list):
        raise ValueError(f"Invalid prompts file: {path}")
    return cases


def _summarize_top_matches(top_matches: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in top_matches or []:
        if not isinstance(row, dict):
            continue
        if row.get("no_matches"):
            rows.append({"no_matches": True, "message": row.get("message")})
            continue
        data = row.get("data") or {}
        rows.append({
            "name": row.get("name"),
            "score": row.get("score"),
            "price": data.get("latest_home_price", row.get("latest_home_price")),
            "commute_min": data.get("drive_minutes_to_boston", row.get("drive_minutes_to_boston")),
            "county": data.get("county", row.get("county")),
            "is_coastal": data.get("is_coastal", row.get("is_coastal")),
        })
    return rows


def _compact_response(case: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    response = payload.get("response") or {}
    route = payload.get("route") or {}
    lookup = response.get("lookup") or {}
    comparison = response.get("comparison")

    compact: dict[str, Any] = {
        "id": case["id"],
        "category": case["category"],
        "category_label": case.get("category_label"),
        "prompt": case["prompt"],
        "route_intent": route.get("intent"),
        "route_confidence": route.get("confidence"),
        "orchestrated": response.get("orchestrated"),
        "used_llm_fallback": payload.get("used_llm_fallback"),
        "classification_source": route.get("classification_source"),
        "python_confidence": route.get("python_confidence"),
        "python_intent": route.get("python_intent"),
        "llm_fallback_used": route.get("llm_fallback_used"),
        "final_recommendation": response.get("final_recommendation"),
        "tradeoff_warning": response.get("tradeoff_warning"),
        "validation": response.get("validation"),
        "strict_valid": (response.get("validation") or {}).get("valid"),
        "top_matches_summary": _summarize_top_matches(response.get("top_matches")),
    }

    if lookup:
        compact["lookup"] = {
            "found": lookup.get("found"),
            "queried_name": lookup.get("queried_name"),
            "town_name": (lookup.get("town") or {}).get("name"),
            "close_matches": lookup.get("close_matches"),
            "message": lookup.get("message"),
        }

    if comparison:
        compact["comparison"] = {
            "error": comparison.get("error"),
            "town_a": (comparison.get("town_a") or {}).get("name"),
            "town_b": (comparison.get("town_b") or {}).get("name"),
        }

    semantic = response.get("semantic_candidates")
    if semantic:
        compact["semantic_candidates"] = {
            "error": semantic.get("error"),
            "candidate_count": len(semantic.get("candidate_town_names") or []),
            "candidates_preview": (semantic.get("candidate_town_names") or [])[:8],
        }

    return compact


async def run_check(
    cases: list[dict[str, Any]],
    *,
    save_searches: bool = False,
) -> list[dict[str, Any]]:
    from app.orchestrator import handle_query

    results: list[dict[str, Any]] = []
    total = len(cases)
    for i, case in enumerate(cases, start=1):
        print(f"[{i}/{total}] {case['id']}: {case['prompt'][:70]}...", flush=True)
        payload = await handle_query(case["prompt"], save_searches=save_searches)
        compact = _compact_response(case, payload)
        compact["full_response"] = payload.get("response")
        compact["full_route"] = payload.get("route")
        results.append(compact)
    return results


def _write_markdown(results: list[dict[str, Any]], path: Path) -> None:
    lines = [
        "# SuburbScout 150-Prompt Quality Check Results",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Total prompts: {len(results)}",
        "",
    ]
    current_category = None
    for row in results:
        cat = row.get("category_label") or row.get("category")
        if cat != current_category:
            current_category = cat
            lines.extend(["", f"## {cat}", ""])
        lines.extend([
            f"### {row['id']}",
            f"**Prompt:** {row['prompt']}",
            f"**Route:** {row.get('route_intent')} (confidence {row.get('route_confidence')})",
            f"**Validation valid:** {(row.get('validation') or {}).get('valid')}",
            "",
            f"**Response:** {row.get('final_recommendation') or '(none)'}",
            "",
        ])
        top = row.get("top_matches_summary") or []
        if top:
            lines.append("**Top matches:**")
            for match in top[:5]:
                if match.get("no_matches"):
                    lines.append(f"- no matches: {match.get('message')}")
                else:
                    lines.append(
                        f"- {match.get('name')} "
                        f"(score={match.get('score')}, "
                        f"price={match.get('price')}, "
                        f"commute={match.get('commute_min')} min)"
                    )
            lines.append("")
        lookup = row.get("lookup")
        if lookup:
            lines.append(
                f"**Lookup:** found={lookup.get('found')} "
                f"town={lookup.get('town_name')} "
                f"close={lookup.get('close_matches')}"
            )
            lines.append("")
        comp = row.get("comparison")
        if comp:
            lines.append(f"**Compare:** {comp.get('town_a')} vs {comp.get('town_b')} error={comp.get('error')}")
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run 150 quality-check prompts and save orchestrator responses.",
    )
    parser.add_argument(
        "--prompts",
        type=Path,
        default=DEFAULT_PROMPTS,
        help="Path to quality_check_150_prompts.json",
    )
    parser.add_argument(
        "--category",
        action="append",
        help="Run only prompts in this category key (e.g. A_lookup, H_semantic_vibe).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Run at most N prompts (0 = all).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory for JSON + markdown output.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Enable save_search_tool during runs.",
    )
    parser.add_argument(
        "--no-full-response",
        action="store_true",
        help="Omit full_response/full_route from JSON (smaller file).",
    )
    return parser.parse_args(argv)


async def _main_async(args: argparse.Namespace) -> None:
    if not args.prompts.exists():
        print(f"Missing prompts file: {args.prompts}", file=sys.stderr)
        print("Run: python scripts/build_quality_check_150.py", file=sys.stderr)
        sys.exit(2)

    cases = load_cases(args.prompts)
    if args.category:
        allowed = set(args.category)
        cases = [c for c in cases if c.get("category") in allowed]
    if args.limit and args.limit > 0:
        cases = cases[: args.limit]

    print("=== SuburbScout 150-Prompt Quality Check ===")
    print(f"Prompts file: {args.prompts}")
    print(f"Running: {len(cases)} prompts")
    print("Mode: response capture (no pass/fail scoring)")
    print()

    results = await run_check(cases, save_searches=args.save)

    if args.no_full_response:
        for row in results:
            row.pop("full_response", None)
            row.pop("full_route", None)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = args.out_dir / f"quality_check_150_{stamp}.json"
    md_path = args.out_dir / f"quality_check_150_{stamp}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "prompt_count": len(results),
                "results": results,
            },
            f,
            indent=2,
        )

    _write_markdown(results, md_path)

    print()
    passed = sum(1 for r in results if r.get("strict_valid") is True)
    failed = sum(1 for r in results if r.get("strict_valid") is False)
    unknown = len(results) - passed - failed
    print(f"Strict validation: {passed}/{len(results)} passed ({passed/len(results):.1%})")
    if failed:
        print(f"  Failed: {failed}  Unknown: {unknown}")
    print(f"Wrote JSON: {json_path}")
    print(f"Wrote Markdown: {md_path}")
    print("Review responses in the markdown file or JSON for full detail.")


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
