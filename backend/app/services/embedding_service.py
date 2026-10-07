"""Embedding via the OpenAI-compatible /embeddings endpoint.

Returns None (never raises) when unconfigured/unavailable so every caller can
degrade gracefully to hash+simhash-only dedup. Results are L2-normalized so
cosine similarity reduces to a dot product in pure Python.
"""

import logging
import math

import httpx

from ..core.config import get_settings

logger = logging.getLogger(__name__)


def normalize_vector(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def cosine_similarity(left: list[float] | None, right: list[float] | None) -> float:
    """Full cosine (normalizes internally, so unnormalized inputs are safe)."""
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    dot = 0.0
    left_mag = 0.0
    right_mag = 0.0
    for i in range(size):
        dot += left[i] * right[i]
        left_mag += left[i] * left[i]
        right_mag += right[i] * right[i]
    if left_mag == 0 or right_mag == 0:
        return 0.0
    return dot / (left_mag ** 0.5 * right_mag ** 0.5)


def embed_texts(texts: list[str]) -> list[list[float]] | None:
    """Synchronous embedding call for worker contexts; None on any failure."""
    settings = get_settings()
    if not texts:
        return []
    if not settings.llm_api_key or not settings.llm_base_url:
        return None
    try:
        response = httpx.post(
            f"{settings.llm_base_url.rstrip('/')}/embeddings",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json={"model": settings.embedding_model, "input": texts[:64]},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or []
        return [normalize_vector(item["embedding"]) for item in data]
    except Exception:
        logger.exception("embedding request failed", extra={"count": len(texts)})
        return None


async def embed_texts_async(texts: list[str]) -> list[list[float]] | None:
    """Async embedding call for request contexts; None on any failure."""
    settings = get_settings()
    if not texts:
        return []
    if not settings.llm_api_key or not settings.llm_base_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"{settings.llm_base_url.rstrip('/')}/embeddings",
                headers={"Authorization": f"Bearer {settings.llm_api_key}"},
                json={"model": settings.embedding_model, "input": texts[:64]},
            )
            response.raise_for_status()
            data = response.json().get("data") or []
            return [normalize_vector(item["embedding"]) for item in data]
    except Exception:
        logger.exception("embedding request failed", extra={"count": len(texts)})
        return None
