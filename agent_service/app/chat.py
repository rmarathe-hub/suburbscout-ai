#!/usr/bin/env python3
"""Interactive CLI for testing SuburbScout agent prompts locally."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

from app.chat_client import get_active_client_kind
from app.real_estate_agent import run_agent

QUIT_COMMANDS = frozenset({"quit", "exit", "q", ":q"})


def _format_summary(parsed: dict[str, Any]) -> str:
    """Human-readable summary from a parsed agent JSON response."""
    lines: list[str] = []

    if parsed.get("orchestrated"):
        intent = parsed.get("route_intent")
        if intent:
            if parsed.get("query_agent") or intent == "query_agent":
                lines.append("Route: query-agent (plan → execute → answer)")
            else:
                lines.append(f"Route: {intent} (legacy orchestrator)")

    lookup = parsed.get("lookup")
    if isinstance(lookup, dict):
        if lookup.get("found"):
            town = (lookup.get("town") or {}).get("name")
            if town:
                lines.append(f"Lookup: {town}")
        else:
            lines.append(f"Lookup: not found ({lookup.get('queried_name', '?')})")
            close = lookup.get("close_matches") or []
            if close:
                lines.append(f"  Close matches: {', '.join(close[:5])}")

    semantic = parsed.get("semantic_candidates")
    if isinstance(semantic, dict):
        names = semantic.get("candidate_town_names") or []
        if names:
            lines.append(f"Semantic candidates: {', '.join(names[:8])}")

    top = parsed.get("top_matches") or []
    if top:
        lines.append("Top matches:")
        for match in top[:5]:
            if not isinstance(match, dict):
                continue
            name = match.get("name", "?")
            score = match.get("score")
            price = match.get("latest_home_price") or (
                (match.get("data") or {}).get("latest_home_price")
            )
            bits = [name]
            if score is not None:
                bits.append(f"score {score}")
            if price is not None:
                bits.append(f"${int(price):,}")
            lines.append(f"  • {' — '.join(bits)}")

    comparison = parsed.get("comparison")
    if isinstance(comparison, dict):
        a = (comparison.get("town_a") or {}).get("name")
        b = (comparison.get("town_b") or {}).get("name")
        if a and b:
            lines.append(f"Compared: {a} vs {b}")

    rec = parsed.get("final_recommendation")
    if rec:
        lines.append(f"\nRecommendation:\n{rec}")

    warning = parsed.get("tradeoff_warning")
    if warning:
        lines.append(f"\nTradeoff: {warning}")

    disclaimer = parsed.get("score_disclaimer")
    if disclaimer:
        lines.append(f"\n({disclaimer})")

    return "\n".join(lines) if lines else json.dumps(parsed, indent=2)


def _print_response(result: dict[str, Any], *, as_json: bool) -> None:
    parsed = result.get("parsed")
    if as_json:
        if parsed:
            print(json.dumps(parsed, indent=2))
        else:
            print(result.get("text", ""))
        return

    if parsed:
        print(_format_summary(parsed))
    else:
        print(result.get("text", ""))


def _print_banner(*, save_searches: bool, as_json: bool, use_query_agent: bool = False) -> None:
    from app import config

    client = get_active_client_kind() or "unknown"
    if use_query_agent:
        save_label = "query_agent_audit.jsonl" if save_searches else "off"
    else:
        save_label = "saved_searches.jsonl" if save_searches else "off"
    output_mode = "JSON" if as_json else "summary"
    if use_query_agent:
        mode = "query-agent (plan → execute → answer)"
    else:
        mode = "orchestrator-first"
    print("SuburbScout interactive chat")
    print(f"  client={client}  output={output_mode}  save={save_label}  mode={mode}")
    if not use_query_agent:
        print("  Legacy orchestrator mode — default is query-agent (plan → execute → answer)")
        print("  Use: python -m app.chat   or set USE_LLM_QUERY_AGENT=true in .env")
    elif not config.USE_LLM_QUERY_AGENT:
        print("  Query-agent forced via --query-agent (USE_LLM_QUERY_AGENT=false in .env)")
    print("  Type a suburb question, or quit / exit / q to leave.")
    print("  Examples:")
    print("    Safe suburb under $900k with good schools")
    print("    Compare Acton and Framingham")
    print("    Quiet North Shore town with a coastal feel")
    print()


async def _chat_loop(
    *,
    save_searches: bool,
    as_json: bool,
    use_orchestrator: bool,
    use_query_agent: bool,
) -> None:
    _print_banner(
        save_searches=save_searches,
        as_json=as_json,
        use_query_agent=use_query_agent,
    )

    while True:
        try:
            prompt = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break

        if not prompt:
            continue
        if prompt.lower() in QUIT_COMMANDS:
            print("Bye.")
            break

        if use_query_agent:
            label = "query agent (plan → execute → answer)"
        elif use_orchestrator:
            label = "orchestrator"
        else:
            label = "LLM agent"
        print(f"… running {label} …")
        try:
            result = await run_agent(
                prompt,
                save_searches=save_searches,
                use_orchestrator=use_orchestrator,
                use_query_agent=use_query_agent,
            )
        except Exception as exc:
            print(f"Error: {exc}", file=sys.stderr)
            continue

        print("\nSuburbScout>")
        _print_response(result, as_json=as_json)
        print()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive SuburbScout agent CLI — type prompts until you quit.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON response instead of a short summary.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Do not call save_search_tool (default for interactive chat).",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Append each turn to saved_searches.jsonl (overrides default no-save).",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="Skip orchestrator and use the LLM agent directly (legacy path).",
    )
    parser.add_argument(
        "--query-agent",
        action="store_true",
        help="Force query agent (default when USE_LLM_QUERY_AGENT=true in .env).",
    )
    parser.add_argument(
        "--orchestrator",
        action="store_true",
        help="Force legacy orchestrator even if USE_LLM_QUERY_AGENT=true in .env",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show agent/tool INFO logs.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    level = logging.INFO if args.verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")

    if args.save and args.no_save:
        print("Use only one of --save or --no-save.", file=sys.stderr)
        sys.exit(2)

    from app import config

    save_searches = bool(args.save)
    if args.orchestrator:
        use_query_agent = False
    elif args.query_agent:
        use_query_agent = True
    else:
        use_query_agent = bool(config.USE_LLM_QUERY_AGENT)
    use_orchestrator = not args.llm and not use_query_agent

    if args.llm and (args.query_agent or use_query_agent):
        print("Use only one of --llm and query-agent mode.", file=sys.stderr)
        sys.exit(2)

    try:
        asyncio.run(
            _chat_loop(
                save_searches=save_searches,
                as_json=args.json,
                use_orchestrator=use_orchestrator,
                use_query_agent=use_query_agent,
            )
        )
    except KeyboardInterrupt:
        print("\nBye.")
        sys.exit(130)


if __name__ == "__main__":
    main()
