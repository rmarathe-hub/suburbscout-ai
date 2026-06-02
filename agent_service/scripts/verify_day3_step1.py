#!/usr/bin/env python3
"""Day 3 Step 1 verification: prerequisites + Azure embeddings smoke test."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


async def _live_embedding_smoke() -> None:
    if os.getenv("SKIP_LIVE_EMBEDDING_RUN", "").lower() in ("1", "true", "yes"):
        print("\n  SKIP: live embedding call (set SKIP_LIVE_EMBEDDING_RUN=0 to enable)")
        return

    from app.embeddings import embed_texts

    print("\n4. Live embedding smoke test")
    vectors = await embed_texts(["Sharon, MA — family-friendly suburb with strong schools"])
    if not vectors or len(vectors) != 1:
        print(f"  FAIL: expected 1 vector, got {len(vectors)}")
        sys.exit(1)
    dim = len(vectors[0])
    if dim < 128:
        print(f"  FAIL: vector dimension too small ({dim})")
        sys.exit(1)
    print(f"  PASS: embedded 1 text → vector dim={dim}")


def main() -> None:
    print("=== Day 3 Step 1: Prerequisites & Embeddings ===\n")

    from app import config
    from app.embeddings import create_embedding_client

    # 1. Day 1 / Day 2 artifacts
    print("1. Phase 1 prerequisites (data + agent)")
    if not config.SUBURBS_JSON_PATH.exists():
        print(f"  FAIL: missing {config.SUBURBS_JSON_PATH} — run Day 1 pipeline first")
        sys.exit(1)
    with open(config.SUBURBS_JSON_PATH, encoding="utf-8") as f:
        suburbs = json.load(f)
    print(f"  PASS: suburbs.json exists ({len(suburbs)} towns)")

    agent_files = [
        config.APP_ROOT / "tools.py",
        config.APP_ROOT / "real_estate_agent.py",
        config.APP_ROOT / "chat_client.py",
    ]
    for path in agent_files:
        if not path.exists():
            print(f"  FAIL: missing {path.name} — complete Day 2 first")
            sys.exit(1)
    print("  PASS: Day 2 agent modules present")

    if not config.VECTOR_DIR.exists():
        print(f"  FAIL: missing vector index dir {config.VECTOR_DIR}")
        sys.exit(1)
    print(f"  PASS: vector index dir ready ({config.VECTOR_DIR.name}/)")

    # 2. Embedding env
    print("\n2. Embedding environment")
    checks = [
        ("AZURE_OPENAI_ENDPOINT", config.AZURE_OPENAI_ENDPOINT),
        ("AZURE_OPENAI_API_KEY", config.AZURE_OPENAI_API_KEY),
        ("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME", config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME),
        ("AZURE_OPENAI_API_VERSION", config.AZURE_OPENAI_API_VERSION),
    ]
    for label, value in checks:
        if not value:
            print(f"  FAIL: {label} is empty — check agent_service/.env")
            sys.exit(1)
        masked = value[:24] + "..." if "KEY" in label else value
        print(f"  PASS: {label} ({masked})")

    # 3. Client factory
    print("\n3. create_embedding_client()")
    try:
        client = create_embedding_client()
        print(f"  PASS: OpenAIEmbeddingClient (model={client.model})")
    except Exception as exc:
        print(f"  FAIL: {exc}")
        sys.exit(1)

    asyncio.run(_live_embedding_smoke())

    print("\nStep 1 verification: PASSED")
    print("Next: Step 2 — scripts/build_town_profiles.py → town_profiles.json")


if __name__ == "__main__":
    main()
