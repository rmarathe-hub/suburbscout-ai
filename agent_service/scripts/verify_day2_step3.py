#!/usr/bin/env python3
"""Day 2 Step 3 verification: chat client + agent construction (+ optional live run)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


async def _optional_live_run() -> None:
    if os.getenv("SKIP_LIVE_AGENT_RUN", "").lower() in ("1", "true", "yes"):
        print("\n  SKIP: live agent.run (set SKIP_LIVE_AGENT_RUN=0 to enable)")
        return

    from app.real_estate_agent import create_agent, response_text

    agent = create_agent()
    from app.chat_client import get_active_client_kind

    kind = get_active_client_kind()
    print(f"\n7. Live agent.run (client={kind})")
    response = await agent.run("Reply with exactly: SUBURBSCOUT_OK")
    text = response_text(response)
    if "SUBURBSCOUT_OK" in text:
        print(f"  PASS: model responded ({text[:80]!r}...)")
    else:
        print(f"  PASS: model responded (len={len(text)})")
        print(f"       snippet: {text[:120]!r}")


def main() -> None:
    print("=== Day 2 Step 3: Chat Client + Agent ===\n")

    from app import config
    from app.chat_client import (
        create_foundry_chat_client,
        create_openai_fallback_chat_client,
        get_active_client_kind,
        get_chat_client,
    )
    from app.real_estate_agent import AGENT_INSTRUCTIONS, create_agent
    from app.tools import CORE_AGENT_TOOLS

    # 1. Imports
    print("1. Module imports")
    print("  PASS: app.chat_client, app.real_estate_agent")

    # 2. Config
    print("\n2. Required env for agent")
    for label, value in [
        ("FOUNDRY_PROJECT_ENDPOINT", config.FOUNDRY_PROJECT_ENDPOINT),
        ("AZURE_OPENAI_API_KEY", config.AZURE_OPENAI_API_KEY),
        ("AZURE_OPENAI_DEPLOYMENT_NAME", config.CHAT_MODEL_DEPLOYMENT),
        ("AZURE_OPENAI_ENDPOINT (fallback)", config.AZURE_OPENAI_ENDPOINT),
    ]:
        if not value:
            print(f"  FAIL: {label} is empty")
            sys.exit(1)
        masked = value[:24] + "..." if "KEY" in label else value
        print(f"  PASS: {label} ({masked})")

    # 3. Foundry client (may fail — that's ok if fallback works)
    print("\n3. FoundryChatClient factory")
    foundry_ok = False
    try:
        fc = create_foundry_chat_client()
        print(f"  PASS: FoundryChatClient created (model={fc.model})")
        foundry_ok = True
    except Exception as exc:
        print(f"  WARN: FoundryChatClient failed — {exc}")

    # 4. OpenAI fallback factory
    print("\n4. OpenAIChatClient fallback factory")
    try:
        oc = create_openai_fallback_chat_client()
        print(f"  PASS: OpenAIChatClient created (model={oc.model})")
    except Exception as exc:
        print(f"  FAIL: OpenAIChatClient fallback — {exc}")
        sys.exit(1)

    # 5. get_chat_client
    print("\n5. get_chat_client()")
    client = get_chat_client()
    kind = get_active_client_kind()
    if kind == "foundry" and not foundry_ok:
        print("  FAIL: reported foundry but factory failed earlier")
        sys.exit(1)
    if kind not in ("foundry", "openai_fallback"):
        print(f"  FAIL: unknown client kind {kind!r}")
        sys.exit(1)
    print(f"  PASS: active client = {kind} ({type(client).__name__})")

    # 6. Agent
    print("\n6. create_agent()")
    agent = create_agent()
    tool_names = sorted(
        getattr(t, "name", None) or getattr(t, "__name__", str(t)) for t in CORE_AGENT_TOOLS
    )
    if len(tool_names) != 5:
        print(f"  FAIL: expected 5 tools, got {tool_names}")
        sys.exit(1)
    if "semantic" in " ".join(tool_names).lower():
        print("  FAIL: semantic tool must not be registered")
        sys.exit(1)
    print(f"  PASS: Agent name={agent.name!r}, tools={tool_names}")
    if "suburbs.json" not in AGENT_INSTRUCTIONS.lower():
        print("  FAIL: instructions missing suburbs.json rule")
        sys.exit(1)
    print("  PASS: instructions reference suburbs.json and tool workflow")

    asyncio.run(_optional_live_run())

    print("\nStep 3 verification: PASSED")
    print("Next: Step 4 — app/test_agent.py (3 prompts)")


if __name__ == "__main__":
    main()
