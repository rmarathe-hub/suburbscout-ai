"""Local vector index for town profile semantic search (Day 3)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from app.config import VECTOR_DIR, VECTOR_EMBEDDINGS_PATH, VECTOR_METADATA_PATH


@dataclass
class TownSearchResult:
    """One town match from vector search."""

    name: str
    score: float
    region: str | None
    tags: list[str]
    rank: int
    snippet: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "region": self.region,
            "tags": self.tags,
            "rank": self.rank,
            "snippet": self.snippet,
        }


class TownVectorStore:
    """In-memory cosine-similarity search over town profile embeddings."""

    def __init__(
        self,
        embeddings: np.ndarray,
        towns: list[dict[str, Any]],
        *,
        embedding_model: str,
    ) -> None:
        if embeddings.ndim != 2:
            raise ValueError("embeddings must be a 2D array")
        if len(towns) != embeddings.shape[0]:
            raise ValueError("town metadata count must match embedding rows")

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        self._embeddings = embeddings.astype(np.float32)
        self._normalized = self._embeddings / norms
        self._towns = towns
        self.embedding_model = embedding_model
        self.embedding_dim = int(embeddings.shape[1])

    @classmethod
    def load(cls, vector_dir: Path | None = None) -> TownVectorStore:
        """Load index from disk."""
        base = vector_dir or VECTOR_DIR
        emb_path = base / "embeddings.npy" if vector_dir else VECTOR_EMBEDDINGS_PATH
        meta_path = base / "metadata.json" if vector_dir else VECTOR_METADATA_PATH

        if not emb_path.exists() or not meta_path.exists():
            raise FileNotFoundError(
                f"Vector index not found under {base}. Run scripts/build_vector_index.py first."
            )

        embeddings = np.load(emb_path)
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        return cls(
            embeddings=embeddings,
            towns=meta["towns"],
            embedding_model=meta.get("embedding_model", "unknown"),
        )

    def search(
        self,
        query_vector: Sequence[float],
        *,
        top_k: int = 10,
    ) -> list[TownSearchResult]:
        """Return top-k towns by cosine similarity (higher is better)."""
        if top_k < 1:
            raise ValueError("top_k must be at least 1")

        q = np.asarray(query_vector, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm == 0:
            return []
        q = q / q_norm

        scores = self._normalized @ q
        k = min(top_k, len(scores))
        top_idx = np.argpartition(-scores, k - 1)[:k]
        top_idx = top_idx[np.argsort(-scores[top_idx])]

        results: list[TownSearchResult] = []
        for rank, idx in enumerate(top_idx, start=1):
            town = self._towns[int(idx)]
            results.append(
                TownSearchResult(
                    name=town["name"],
                    score=round(float(scores[int(idx)]), 4),
                    region=town.get("region"),
                    tags=list(town.get("tags") or []),
                    rank=rank,
                    snippet=(town.get("search_text") or "")[:240] or None,
                )
            )
        return results

    @property
    def town_count(self) -> int:
        return len(self._towns)


async def search_towns_by_text(
    query: str,
    *,
    top_k: int = 10,
    store: TownVectorStore | None = None,
) -> list[TownSearchResult]:
    """Embed a query and return top matching towns from the local index."""
    from app.embeddings import embed_texts

    active = store or TownVectorStore.load()
    vector = (await embed_texts([query]))[0]
    return active.search(vector, top_k=top_k)
