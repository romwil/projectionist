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


def content_hash_for_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    """Build weighted/sectioned text for item embeddings.

    Plot section (summary + TMDB overview + tagline + optional LLM logline) is
    listed first and denser so semantic similarity leans on narrative.  Metadata
    (title/year/genres/keywords) is a lighter second section for grounding.
    """
    def _field(name: str) -> str:
        try:
            value = row[name]
        except (KeyError, IndexError, TypeError):
            return ""
        return str(value or "").strip()

    genres = row["genres"] if isinstance(row["genres"], str) else "[]"
    keywords = row["keywords"] if isinstance(row["keywords"], str) else "[]"

    plot_parts = [
        _field("summary"),
        _field("tmdb_overview"),
        _field("tagline"),
        _field("llm_logline"),
    ]
    # Repeat non-empty plot lines once for mild plot weighting vs metadata.
    plot_body = "\n".join(p for p in plot_parts if p)
    plot_section = "\n".join(
        part
        for part in [
            "PLOT:",
            plot_body,
            plot_body if plot_body else "",
        ]
        if part
    )

    meta_parts = [
        f"Title: {_field('title')}" if _field("title") else "",
        f"Year: {_field('year')}" if _field("year") else "",
        f"Genres: {genres}" if genres and genres != "[]" else "",
        f"Keywords: {keywords}" if keywords and keywords != "[]" else "",
    ]
    meta_section = "\n".join(
        part for part in ["METADATA:", *[p for p in meta_parts if p]] if part
    )
    return "\n\n".join(section for section in [plot_section, meta_section] if section)


def embedding_model_label(settings: Settings) -> str:
    """Stable label stored on embeddings rows for hygiene / future rebuilds."""
    if settings.llm_api_key:
        return str(settings.llm_embedding_model or "text-embedding-3-small").strip()
    return "hash-fallback"


def _embedding_progress_message(current: int, total: int, *, skipped: int = 0) -> str:
    current = max(int(current or 0), 0)
    total_n = max(int(total or 0), 0)
    if total_n <= 0:
        return "Building recommendations…"
    if current <= 0:
        return "Building recommendations…"
    if current < total_n:
        if skipped:
            return f"Building recommendations… {current} of ~{total_n} ({skipped} unchanged)"
        return f"Building recommendations… {current} of ~{total_n}"
    if skipped:
        return f"Built recommendations for {current} titles ({skipped} unchanged)"
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

    existing_hashes = db.embedding_content_hashes()
    batch = max(1, int(batch_size or DEFAULT_EMBED_BATCH_SIZE))
    skipped = 0
    embedded = 0
    last_log = 0.0
    if progress is not None:
        progress("finishing", 0, total, _embedding_progress_message(0, total))

    pending_rows: list[Any] = []
    pending_texts: list[str] = []
    pending_hashes: list[str] = []

    async def _flush_pending() -> None:
        nonlocal embedded
        if not pending_rows:
            return
        vectors = await embed_texts(pending_texts, settings)
        pairs = [
            (int(row["id"]), vector, content_hash)
            for row, vector, content_hash in zip(pending_rows, vectors, pending_hashes)
        ]
        db.set_embeddings(pairs, embedding_model=embedding_model_label(settings))
        embedded += len(pending_rows)
        pending_rows.clear()
        pending_texts.clear()
        pending_hashes.clear()

    for index, row in enumerate(rows, start=1):
        text = await build_item_embedding_text(row)
        digest = content_hash_for_text(text)
        item_id = int(row["id"])
        if existing_hashes.get(item_id) == digest:
            skipped += 1
        else:
            pending_rows.append(row)
            pending_texts.append(text)
            pending_hashes.append(digest)
            if len(pending_rows) >= batch:
                await _flush_pending()

        message = _embedding_progress_message(index, total, skipped=skipped)
        now = time.time()
        should_emit = index == 1 or index >= total or index % 25 == 0 or (now - last_log) >= 3.0
        if should_emit:
            if progress is not None:
                progress("finishing", index, total, message)
            if now - last_log >= 3.0 or index >= total:
                logger.info(
                    "Library sync: building recommendations — %s of %s titles (%s unchanged)",
                    index,
                    total,
                    skipped,
                )
                last_log = now

    await _flush_pending()
    count = embedded + skipped
    if progress is not None:
        progress(
            "finishing",
            max(total, 1),
            max(total, 1),
            _embedding_progress_message(total, total, skipped=skipped),
        )
    if skipped:
        logger.info(
            "Library sync: recommendations reuse — embedded=%s skipped_unchanged=%s total=%s",
            embedded,
            skipped,
            total,
        )
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
