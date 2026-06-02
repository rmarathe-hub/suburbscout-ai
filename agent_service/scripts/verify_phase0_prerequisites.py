#!/usr/bin/env python3
"""Phase 0 — prerequisites for the query-plan agent (JSON + local vector index).

Checks (offline):
  - suburbs.json (200 towns, core fields)
  - town_profiles.json
  - vector_index/embeddings.npy + metadata.json (aligned with suburbs)
  - TownVectorStore loads; local cosine search works (no API)

Checks (optional live — set SKIP_LIVE_AZURE_CHECKS=1 to skip):
  - Azure embedding API (planner + semantic query embedding)
  - semantic_town_search end-to-end

Rebuild missing artifacts:
  python scripts/build_suburbs_dataset.py
  python scripts/build_town_profiles.py
  python scripts/build_vector_index.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from dotenv import load_dotenv

load_dotenv(SERVICE_ROOT / ".env")

EXPECTED_TOWN_COUNT = 200
CORE_FIELDS = (
    "name",
    "latest_home_price",
    "school_score",
    "safety_score",
    "drive_minutes_to_boston",
)


def _fail(msg: str) -> None:
    print(f"  FAIL: {msg}")
    sys.exit(1)


def _pass(msg: str) -> None:
    print(f"  PASS: {msg}")


def check_env_file() -> None:
    print("0. Environment file")
    env_path = SERVICE_ROOT / ".env"
    example_path = SERVICE_ROOT / ".env.example"
    if not env_path.exists():
        _fail(
            f"Missing {env_path}. Copy from .env.example:\n"
            f"  cp .env.example .env"
        )
    _pass(f".env exists ({env_path})")
    if not example_path.exists():
        print("  WARN: .env.example missing")
    else:
        _pass(".env.example present for reference")


def check_env_vars_for_query_agent() -> list[str]:
    """Return list of warnings (non-fatal) for unset optional vars."""
    from app import config

    print("\n1. Environment variables (values not printed)")
    warnings: list[str] = []

    required_for_llm = [
        (config.AZURE_OPENAI_API_KEY, "AZURE_OPENAI_API_KEY", "LLM planner + answer + embeddings"),
        (config.AZURE_OPENAI_ENDPOINT, "AZURE_OPENAI_ENDPOINT", "Azure OpenAI resource URL"),
        (config.CHAT_MODEL_DEPLOYMENT, "AZURE_OPENAI_DEPLOYMENT_NAME", "Chat model (planner + answer)"),
        (
            config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME,
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME",
            "Query embedding for semantic search",
        ),
    ]
    for value, var, purpose in required_for_llm:
        if value:
            _pass(f"{var} is set ({purpose})")
        else:
            warnings.append(f"{var} is not set — needed for live LLM/embeddings ({purpose})")

    if config.FOUNDRY_PROJECT_ENDPOINT:
        _pass("FOUNDRY_PROJECT_ENDPOINT is set (optional Foundry chat)")
    else:
        print("  INFO: FOUNDRY_PROJECT_ENDPOINT unset (OK if using Azure OpenAI fallback only)")

    if config.GOOGLE_MAPS_API_KEY:
        _pass("GOOGLE_MAPS_API_KEY is set (commute rebuild only)")
    else:
        print("  INFO: GOOGLE_MAPS_API_KEY unset (OK unless rebuilding commute data)")

    return warnings


def check_suburbs_json() -> list[str]:
    print("\n2. Structured dataset (suburbs.json)")
    from app.config import SUBURBS_JSON_PATH

    if not SUBURBS_JSON_PATH.exists():
        _fail(
            f"Missing {SUBURBS_JSON_PATH}. Run:\n"
            "  python scripts/build_suburbs_dataset.py"
        )

    with open(SUBURBS_JSON_PATH, encoding="utf-8") as f:
        suburbs = json.load(f)

    if not isinstance(suburbs, list):
        _fail("suburbs.json must be a JSON array of town objects")

    if len(suburbs) != EXPECTED_TOWN_COUNT:
        _fail(
            f"Expected {EXPECTED_TOWN_COUNT} towns in suburbs.json, got {len(suburbs)}. "
            "Re-run build_suburbs_dataset.py"
        )
    _pass(f"suburbs.json has {EXPECTED_TOWN_COUNT} towns")

    names = [s.get("name") for s in suburbs]
    if any(not n for n in names):
        _fail("Some suburbs entries missing 'name'")
    if len(set(names)) != len(names):
        _fail("Duplicate town names in suburbs.json")

    missing_core = 0
    for town in suburbs:
        for field in CORE_FIELDS:
            if field == "name":
                continue
            if town.get(field) is None and field not in (town.get("missing_fields") or []):
                missing_core += 1
                break
    if missing_core:
        print(f"  WARN: {missing_core} towns may lack core fields (run validate_dataset.py)")

    _pass("town names unique; core field spot-check OK")
    return [n for n in names if n]


def check_town_profiles() -> None:
    print("\n3. Town profiles (for vector index)")
    from app.config import TOWN_PROFILES_PATH

    if not TOWN_PROFILES_PATH.exists():
        _fail(
            f"Missing {TOWN_PROFILES_PATH}. Run:\n"
            "  python scripts/build_town_profiles.py"
        )

    with open(TOWN_PROFILES_PATH, encoding="utf-8") as f:
        profiles = json.load(f)

    count = len(profiles) if isinstance(profiles, list) else len(profiles.get("towns", []))
    if isinstance(profiles, dict) and "towns" in profiles:
        count = len(profiles["towns"])
    _pass(f"town_profiles.json present ({count} profile entries)")


def check_vector_index(suburb_names: list[str]) -> None:
    print("\n4. Local vector index (no vector DB server required)")
    import numpy as np

    from app.config import VECTOR_EMBEDDINGS_PATH, VECTOR_METADATA_PATH
    from app.vector_store import TownVectorStore

    if not VECTOR_EMBEDDINGS_PATH.exists() or not VECTOR_METADATA_PATH.exists():
        _fail(
            "Missing vector index files. Run:\n"
            "  python scripts/build_town_profiles.py\n"
            "  python scripts/build_vector_index.py"
        )

    embeddings = np.load(VECTOR_EMBEDDINGS_PATH)
    with open(VECTOR_METADATA_PATH, encoding="utf-8") as f:
        meta = json.load(f)

    towns_meta = meta.get("towns") or []
    if len(towns_meta) != EXPECTED_TOWN_COUNT:
        _fail(f"metadata.json expected {EXPECTED_TOWN_COUNT} towns, got {len(towns_meta)}")

    if embeddings.shape[0] != EXPECTED_TOWN_COUNT:
        _fail(
            f"embeddings.npy rows ({embeddings.shape[0]}) != "
            f"{EXPECTED_TOWN_COUNT} towns"
        )

    _pass(f"embeddings shape {embeddings.shape}, model={meta.get('embedding_model', '?')}")

    index_names = sorted(t.get("name", "") for t in towns_meta)
    suburb_sorted = sorted(suburb_names)
    if index_names != suburb_sorted:
        missing_in_index = set(suburb_names) - set(index_names)
        extra_in_index = set(index_names) - set(suburb_names)
        if missing_in_index or extra_in_index:
            _fail(
                "Vector index town names do not match suburbs.json: "
                f"missing_in_index={list(missing_in_index)[:5]} "
                f"extra_in_index={list(extra_in_index)[:5]}"
            )

    _pass("vector index town names match suburbs.json")

    store = TownVectorStore.load()
    if store.town_count != EXPECTED_TOWN_COUNT:
        _fail(f"TownVectorStore town_count={store.town_count}")

    # Offline search: use first town embedding as query (no API)
    probe = embeddings[0]
    hits = store.search(probe, top_k=3)
    if not hits or hits[0].score <= 0:
        _fail("Local cosine search returned no sensible results")
    _pass(f"offline vector search OK (top hit: {hits[0].name}, score={hits[0].score})")


async def check_live_azure() -> None:
    print("\n5. Live Azure checks (embedding + semantic search)")
    if os.getenv("SKIP_LIVE_AZURE_CHECKS", "").lower() in ("1", "true", "yes"):
        print("  SKIP: SKIP_LIVE_AZURE_CHECKS is set")
        return

    from app import config
    from app.embeddings import embed_texts
    from app.tools import run_semantic_town_search

    if not all(
        [
            config.AZURE_OPENAI_API_KEY,
            config.AZURE_OPENAI_ENDPOINT,
            config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME,
        ]
    ):
        print("  SKIP: Azure embedding env vars not fully set")
        return

    vectors = await embed_texts(["quiet suburban town near Boston"])
    if not vectors or len(vectors[0]) < 8:
        _fail("embed_texts returned empty or trivial vector")
    _pass(f"embedding API OK (dim={len(vectors[0])})")

    result = await run_semantic_town_search(
        "quiet coastal North Shore town with small-town feel",
        top_k=5,
    )
    if result.get("error"):
        _fail(f"semantic search error: {result['error']}")
    names = result.get("candidate_town_names") or []
    if not names:
        _fail("semantic search returned no candidates")
    _pass(f"semantic search OK (top candidates: {', '.join(names[:3])})")


def main() -> None:
    print("=== Phase 0 prerequisites (query-plan agent) ===\n")
    check_env_file()
    env_warnings = check_env_vars_for_query_agent()
    suburb_names = check_suburbs_json()
    check_town_profiles()
    check_vector_index(suburb_names)

    asyncio.run(check_live_azure())

    print("\n6. Dataset validation script")
    import subprocess

    proc = subprocess.run(
        [sys.executable, str(SERVICE_ROOT / "scripts" / "validate_dataset.py")],
        cwd=str(SERVICE_ROOT),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(proc.stdout)
        print(proc.stderr)
        _fail("validate_dataset.py failed")
    _pass("validate_dataset.py completed")

    print("\n=== Phase 0 complete ===")
    print("Storage model:")
    print("  - Facts:     app/data/suburbs.json (200 towns)")
    print("  - Semantic:  app/data/vector_index/ (local .npy + metadata.json)")
    print("  - No Postgres / vector DB server required for Phase 1+")
    if env_warnings:
        print("\nWarnings (fix before live LLM planner):")
        for w in env_warnings:
            print(f"  - {w}")
    else:
        print("\nAzure LLM + embedding env vars look ready for Phase 4+.")


if __name__ == "__main__":
    main()
