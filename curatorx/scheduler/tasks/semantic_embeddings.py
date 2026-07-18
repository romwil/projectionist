"""Idle task: generate semantic embeddings over plot summaries.

Scans ``library_items`` for rows with a non-empty ``overview`` (the *summary*
column) and batch-embeds them using the configured embedding provider.  Tracks
content hashes so unchanged items are skipped on subsequent runs.

Stores vectors in the existing ``embeddings`` table (same one used by library
sync) and records the text hash in its ``content_hash`` column.

This is the heaviest idle task — default interval is 24 hours.

Trickle ingestion
~~~~~~~~~~~~~~~~~
To avoid pegging CPU/network when hundreds of items need embedding (e.g.
after an initial library sync), the task caps work at ``MAX_ITEMS_PER_CYCLE``
per scheduler invocation.  Remaining items are picked up on the next idle
cycle.  Within each cycle, items are sent to the embedding API in batches
of ``BATCH_SIZE`` and ``should_stop()`` is checked between batches for
cooperative interruption.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.embeddings import (
    build_item_embedding_text,
    content_hash_for_text,
    embed_texts,
    embedding_model_label,
)
from curatorx.scheduler.autotune import resolve_batch_size
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
MAX_ITEMS_PER_CYCLE = 50
INTERVAL_SECONDS = 86400  # 24 hours
TASK_NAME = "semantic_embeddings"


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    rows = list(db.all_library_items())
    total = len(rows)
    if total == 0:
        return {"status": "completed", "embedded": 0, "skipped": 0}

    cycle_cap = resolve_batch_size(db, TASK_NAME, MAX_ITEMS_PER_CYCLE)
    existing_hashes = db.embedding_content_hashes()
    embedded = 0
    skipped = 0
    pending_rows: list[Any] = []
    pending_texts: list[str] = []
    pending_hashes: list[str] = []

    async def _flush() -> None:
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

    for row in rows:
        if embedded >= cycle_cap:
            remaining = total - skipped - embedded
            logger.info(
                "Semantic embeddings: cycle cap reached (%d embedded, ~%d remaining); "
                "will continue on next idle cycle",
                embedded,
                remaining,
            )
            return {
                "status": "cycle_limit",
                "embedded": embedded,
                "skipped": skipped,
                "total": total,
                "remaining": remaining,
                "batch_size": cycle_cap,
                "has_more": True,
            }

        summary = str(row["summary"] or "").strip()
        if not summary:
            skipped += 1
            continue

        text = await build_item_embedding_text(row)
        digest = content_hash_for_text(text)
        item_id = int(row["id"])

        if existing_hashes.get(item_id) == digest:
            skipped += 1
            continue

        pending_rows.append(row)
        pending_texts.append(text)
        pending_hashes.append(digest)

        if len(pending_rows) >= BATCH_SIZE:
            await _flush()
            await asyncio.sleep(0)
            if should_stop():
                logger.info(
                    "Semantic embeddings interrupted after %d embedded, %d skipped",
                    embedded,
                    skipped,
                )
                return {
                    "status": "interrupted",
                    "embedded": embedded,
                    "skipped": skipped,
                    "total": total,
                }

    await _flush()

    logger.info(
        "Semantic embeddings complete: embedded=%d skipped=%d total=%d",
        embedded,
        skipped,
        total,
    )
    return {
        "status": "completed",
        "embedded": embedded,
        "skipped": skipped,
        "total": total,
        "batch_size": cycle_cap,
        "has_more": db.count_items_needing_embeddings() > 0,
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name=TASK_NAME,
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Builds semantic embeddings from plot summaries for similarity search and "
                f"Plot Lab. Caps each run at {MAX_ITEMS_PER_CYCLE} titles so large libraries "
                "catch up gradually without pegging the host (batch auto-tunes from history)."
            ),
            items_per_cycle=MAX_ITEMS_PER_CYCLE,
            progress_scope="embeddings_pending",
        )
    )
