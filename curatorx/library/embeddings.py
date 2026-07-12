"""Embedding generation and vector search."""

from __future__ import annotations

import hashlib
import logging
import math
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from curatorx.config_store import Settings
from curatorx.library.db import Database

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str, int, int, str], None]]

DEFAULT_EMBED_BATCH_SIZE = 64


def _hash_embed(text: str, dims: int = 384) -> List[float]:
    """Deterministic fallback embedding when no LLM embedding API is configured."""
    vector = np.zeros(dims, dtype=np.float32)
    tokens = text.lower().split()
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for index in range(dims):
            vector[index] += (digest[index % len(digest)] / 255.0) - 0.5
    norm = np.linalg.norm(vector)
    if norm > 0:
        vector = vector / norm
    return vector.tolist()


async def embed_text(text: str, settings: Settings) -> List[float]:
    vectors = await embed_texts([text], settings)
    return vectors[0] if vectors else _hash_embed(text)


async def embed_texts(texts: Sequence[str], settings: Settings) -> List[List[float]]:
    """Embed many texts; prefers provider batch API when available."""
    if not texts:
        return []
    if not settings.llm_api_key:
        return [_hash_embed(text) for text in texts]
    try:
        from curatorx.agent.providers import get_embedding_provider

        provider = get_embedding_provider(settings)
        embed_many = getattr(provider, "embed_many", None)
        if callable(embed_many):
            return await embed_many(list(texts))
        return [await provider.embed(text) for text in texts]
    except Exception:
        logger.exception("Embedding provider failed; falling back to hash embeddings")
        return [_hash_embed(text) for text in texts]


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def build_item_embedding_text(row) -> str:
    genres = row["genres"] if isinstance(row["genres"], str) else "[]"
    keywords = row["keywords"] if isinstance(row["keywords"], str) else "[]"
    return "\n".join(
        part
        for part in [
            row["title"],
            str(row["year"] or ""),
            row["summary"] or "",
            genres,
            keywords,
        ]
        if part
    )


def _embedding_progress_message(current: int, total: int) -> str:
    current = max(int(current or 0), 0)
    total_n = max(int(total or 0), 0)
    if total_n <= 0:
        return "Building recommendations…"
    if current <= 0:
        return "Building recommendations…"
    if current < total_n:
        return f"Building recommendations… {current} of ~{total_n}"
    return f"Built recommendations for {current} titles"


async def rebuild_embeddings(
    db: Database,
    settings: Settings,
    *,
    progress: ProgressCallback = None,
    batch_size: int = DEFAULT_EMBED_BATCH_SIZE,
) -> int:
    rows = list(db.all_library_items())
    total = len(rows)
    if total == 0:
        if progress is not None:
            progress("finishing", 1, 1, "Building recommendations…")
        return 0

    batch = max(1, int(batch_size or DEFAULT_EMBED_BATCH_SIZE))
    count = 0
    last_log = 0.0
    if progress is not None:
        progress("finishing", 0, total, _embedding_progress_message(0, total))

    for start in range(0, total, batch):
        chunk = rows[start : start + batch]
        texts = [await build_item_embedding_text(row) for row in chunk]
        vectors = await embed_texts(texts, settings)
        pairs = [
            (int(row["id"]), vector)
            for row, vector in zip(chunk, vectors)
        ]
        db.set_embeddings(pairs)
        count += len(chunk)

        message = _embedding_progress_message(count, total)
        if progress is not None:
            progress("finishing", count, total, message)
        now = time.time()
        if now - last_log >= 3.0 or count >= total:
            logger.info(
                "Library sync: building recommendations — %s of %s titles",
                count,
                total,
            )
            last_log = now

    return count


def semantic_search(
    db: Database,
    query_vector: Sequence[float],
    *,
    limit: int = 20,
    media_type: Optional[str] = None,
    candidate_ids: Optional[set[int]] = None,
) -> List[Tuple[int, float]]:
    scores: List[Tuple[int, float]] = []
    items: Dict[int, Any] = {}
    if media_type:
        for row in db.all_library_items():
            items[int(row["id"])] = row
    for item_id, vector in db.get_embeddings():
        if candidate_ids is not None and item_id not in candidate_ids:
            continue
        if media_type:
            row = items.get(item_id)
            if row is None or row["media_type"] != media_type:
                continue
        score = cosine_similarity(query_vector, vector)
        scores.append((item_id, score))
    scores.sort(key=lambda item: item[1], reverse=True)
    return scores[:limit]
