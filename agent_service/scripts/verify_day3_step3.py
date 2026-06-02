#!/usr/bin/env python3
"""Day 3 Step 3 verification: embed profiles and vector search."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_ROOT))


async def _search_query(store, query: str, top_k: int = 5) -> list:
    from app.embeddings import embed_texts

    vector = (await embed_texts([query]))[0]
    return store.search(vector, top_k=top_k)


def main() -> None:
    print("=== Day 3 Step 3: Vector Index & Search ===\n")

    from app.config import TOWN_PROFILES_PATH, VECTOR_EMBEDDINGS_PATH, VECTOR_METADATA_PATH
    from app.vector_store import TownVectorStore

    if not TOWN_PROFILES_PATH.exists():
        print(f"  FAIL: missing {TOWN_PROFILES_PATH} — run Step 2 first")
        sys.exit(1)
    print("1. Prerequisites")
    print("  PASS: town_profiles.json exists")

    print("\n2. build_vector_index.py")
    import subprocess

    result = subprocess.run(
        [sys.executable, str(SERVICE_ROOT / "scripts" / "build_vector_index.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"  FAIL: build exited {result.returncode}")
        print(result.stderr or result.stdout)
        sys.exit(1)
    print("  PASS: build_vector_index.py completed")
    for line in (result.stdout or "").strip().splitlines():
        print(f"       {line}")

    print("\n3. Index files")
    for path in (VECTOR_EMBEDDINGS_PATH, VECTOR_METADATA_PATH):
        if not path.exists():
            print(f"  FAIL: missing {path}")
            sys.exit(1)
        print(f"  PASS: {path.name} exists")

    with open(VECTOR_METADATA_PATH, encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("town_count") != 200:
        print(f"  FAIL: expected town_count=200, got {meta.get('town_count')}")
        sys.exit(1)
    if meta.get("embedding_dim", 0) < 128:
        print(f"  FAIL: unexpected embedding_dim {meta.get('embedding_dim')}")
        sys.exit(1)
    print(f"  PASS: metadata town_count=200, dim={meta.get('embedding_dim')}")

    print("\n4. TownVectorStore.load()")
    store = TownVectorStore.load()
    if store.town_count != 200:
        print(f"  FAIL: store has {store.town_count} towns")
        sys.exit(1)
    print(f"  PASS: loaded store ({store.town_count} towns, model={store.embedding_model})")

    if os.getenv("SKIP_LIVE_EMBEDDING_RUN", "").lower() in ("1", "true", "yes"):
        print("\n  SKIP: live search queries (set SKIP_LIVE_EMBEDDING_RUN=0 to enable)")
        print("\nStep 3 verification: PASSED")
        print("Next: Step 4 — semantic_town_search_tool + agent integration")
        return

    print("\n5. Semantic search smoke tests")

    north_shore = asyncio.run(
        _search_query(store, "quiet coastal North Shore town with small-town feel", top_k=5)
    )
    ns_names = [r.name for r in north_shore]
    ns_regions = [r.region or "" for r in north_shore]
    if not any("North Shore" in r for r in ns_regions):
        print(f"  FAIL: North Shore query missing North Shore towns — got {ns_names}")
        sys.exit(1)
    print(f"  PASS: North Shore query → {', '.join(ns_names[:3])}")

    schools = asyncio.run(
        _search_query(store, "family-friendly suburb with strong schools and low crime", top_k=5)
    )
    school_names = [r.name for r in schools]
    if not school_names:
        print("  FAIL: schools query returned no results")
        sys.exit(1)
    print(f"  PASS: schools query → {', '.join(school_names[:3])}")

    print("\nStep 3 verification: PASSED")
    print("Next: Step 4 — semantic_town_search_tool + agent integration")


if __name__ == "__main__":
    main()
