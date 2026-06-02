#!/usr/bin/env python3
"""Embed town profiles and build local vector index."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

SERVICE_ROOT = Path(__file__).resolve().parent.parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import (  # noqa: E402
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME,
    TOWN_PROFILES_PATH,
    VECTOR_DIR,
    VECTOR_EMBEDDINGS_PATH,
    VECTOR_METADATA_PATH,
)
from app.embeddings import embed_texts_batched  # noqa: E402


def _profiles_fingerprint(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def _load_profiles() -> list[dict]:
    if not TOWN_PROFILES_PATH.exists():
        raise SystemExit(
            f"Missing {TOWN_PROFILES_PATH}. Run scripts/build_town_profiles.py first."
        )
    with open(TOWN_PROFILES_PATH, encoding="utf-8") as f:
        return json.load(f)


def _index_is_current(fingerprint: str) -> bool:
    if not VECTOR_EMBEDDINGS_PATH.exists() or not VECTOR_METADATA_PATH.exists():
        return False
    with open(VECTOR_METADATA_PATH, encoding="utf-8") as f:
        meta = json.load(f)
    return meta.get("profiles_fingerprint") == fingerprint


async def _build_index(*, force: bool = False) -> dict:
    profiles = _load_profiles()
    fingerprint = _profiles_fingerprint(TOWN_PROFILES_PATH)

    if not force and _index_is_current(fingerprint):
        with open(VECTOR_METADATA_PATH, encoding="utf-8") as f:
            meta = json.load(f)
        print(f"Vector index up to date ({meta.get('town_count')} towns) — skipping embed API calls.")
        return meta

    texts = [p["search_text"] for p in profiles]
    print(f"Embedding {len(texts)} town profiles via Azure OpenAI...")
    vectors = await embed_texts_batched(texts)
    if len(vectors) != len(profiles):
        raise SystemExit(f"Expected {len(profiles)} vectors, got {len(vectors)}")

    emb = np.asarray(vectors, dtype=np.float32)
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    np.save(VECTOR_EMBEDDINGS_PATH, emb)

    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "embedding_model": AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME,
        "embedding_dim": int(emb.shape[1]),
        "town_count": len(profiles),
        "profiles_fingerprint": fingerprint,
        "profiles_path": str(TOWN_PROFILES_PATH.name),
        "towns": [
            {
                "name": p["name"],
                "region": p.get("region"),
                "county": p.get("county"),
                "tags": p.get("tags") or [],
                "data_quality_tier": p.get("data_quality_tier"),
                "search_text": p.get("search_text"),
            }
            for p in profiles
        ],
    }
    with open(VECTOR_METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")

    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Build town profile vector index.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-embed even if town_profiles.json fingerprint is unchanged.",
    )
    args = parser.parse_args()

    meta = asyncio.run(_build_index(force=args.force))
    print(f"Wrote vector index → {VECTOR_DIR}")
    print(f"  towns: {meta['town_count']}, dim: {meta['embedding_dim']}, model: {meta['embedding_model']}")


if __name__ == "__main__":
    main()
