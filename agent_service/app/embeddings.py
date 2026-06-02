"""Azure OpenAI embeddings for Day 3 town vector search."""

from __future__ import annotations

from typing import Sequence

from agent_framework.openai import OpenAIEmbeddingClient

from app import config


def create_embedding_client() -> OpenAIEmbeddingClient:
    """Build Azure OpenAI embedding client from config / .env."""
    if not config.AZURE_OPENAI_ENDPOINT:
        raise ValueError("AZURE_OPENAI_ENDPOINT is not set in .env")
    if not config.AZURE_OPENAI_API_KEY:
        raise ValueError("AZURE_OPENAI_API_KEY is not set in .env")
    if not config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME:
        raise ValueError("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME is not set in .env")

    return OpenAIEmbeddingClient(
        model=config.AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME,
        azure_endpoint=config.AZURE_OPENAI_ENDPOINT,
        api_key=config.AZURE_OPENAI_API_KEY,
        api_version=config.AZURE_OPENAI_API_VERSION,
    )


async def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """Embed one or more strings; returns vectors in the same order."""
    if not texts:
        return []

    client = create_embedding_client()
    response = await client.get_embeddings(list(texts))
    return [item.vector for item in response]


async def embed_texts_batched(
    texts: Sequence[str],
    *,
    batch_size: int | None = None,
) -> list[list[float]]:
    """Embed many strings in API batches."""
    if not texts:
        return []

    size = batch_size or config.EMBEDDING_BATCH_SIZE
    vectors: list[list[float]] = []
    for start in range(0, len(texts), size):
        chunk = list(texts[start : start + size])
        vectors.extend(await embed_texts(chunk))
    return vectors
