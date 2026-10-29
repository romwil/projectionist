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

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.db_io import run_db
from projectionist.library.embeddings import (
    build_item_embedding_text,
    content_hash_for_text,
    embed_texts,
    embedding_model_label,
)
from projectionist.scheduler.autotune import resolve_batch_size
from projectionist.scheduler.engine import IdleScheduler
from projectionist.scheduler.tasks.base_augmentation import register_severity_task
from projectionist.scheduler.tasks.coverage_signals import emit_embedding_backlog_signals
from projectionist.scheduler.tasks.kinship_augmentation import (
    KinshipMissAugmentationTask,
    stage_kinship_demand,
    with_stage_stats,
)
from projectionist.telemetry.kinship_miss import preferred_item_ids

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
SCAN_YIELD_EVERY = 250
MAX_ITEMS_PER_CYCLE = 50
INTERVAL_SECONDS = 86400  # 24 hours
# Paced follow-up while a backlog is draining (see scheduler/cadence.py).
CATCHUP_GAP_SECONDS = 300
TASK_NAME = "semantic_embeddings"


class SemanticEmbeddingsAugmentation(KinshipMissAugmentationTask):
    """Stage kinship-miss titles that still lack an embedding row."""

    action = "build_semantic_embedding"

    def __init__(self, db: Database) -> None:
        super().__init__(db, task_name=TASK_NAME)

    def item_still_needs(self, item_id: int) -> bool:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT li.id
                FROM library_items li
                WHERE li.id = ?
                  AND TRIM(COALESCE(li.summary, '')) != ''
                  AND NOT EXISTS (
                    SELECT 1 FROM embeddings e WHERE e.item_id = li.id
                  )
                """,
                (int(item_id),),
            ).fetchone()
        return row is not None


def _order_rows_for_demand(db: Database, rows: list[Any], *, limit: int) -> tuple[list[Any], int]:
    """Put kinship-miss titles first without decoding embedding vectors."""
    prefer_ids = preferred_item_ids(db, limit=limit)
    if not prefer_ids:
        return list(rows), 0
    by_id: dict[int, Any] = {}
    for row in rows:
        try:
            by_id[int(row["id"])] = row
        except (TypeError, ValueError, KeyError):
            continue
    out: list[Any] = []
    seen: set[int] = set()
    for item_id in prefer_ids:
        row = by_id.get(item_id)
        if row is None or item_id in seen:
            continue
        seen.add(item_id)
        out.append(row)
    demand_count = len(out)
    for row in rows:
        try:
            rid = int(row["id"])
        except (TypeError, ValueError, KeyError):
            continue
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
    return out, demand_count


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    augmenter = SemanticEmbeddingsAugmentation(db)
    stage_stats, interrupted = await stage_kinship_demand(augmenter, should_stop)
    if interrupted:
        return with_stage_stats(
            {"status": "interrupted", "embedded": 0, "skipped": 0},
            stage_stats,
        )

    rows = list(await run_db(db.all_library_items))
    total = len(rows)
    if total == 0:
        return with_stage_stats(
            {"status": "completed", "embedded": 0, "skipped": 0},
            stage_stats,
        )

    cycle_cap = resolve_batch_size(db, TASK_NAME, MAX_ITEMS_PER_CYCLE)
    rows, demand_prioritized = await run_db(
        _order_rows_for_demand, db, rows, limit=cycle_cap
    )
    coverage_signals = await run_db(emit_embedding_backlog_signals, db, limit=cycle_cap)
    existing_hashes = await run_db(db.embedding_content_hashes)
    embedded = 0
    skipped = 0
    pending_rows: list[Any] = []
    pending_texts: list[str] = []
    pending_hashes: list[str] = []

    async def _flush() -> None:
        nonlocal embedded
        if not pending_rows:
            return
        vectors = await embed_texts(pending_texts, settings, db=db)
        pairs = [
            (int(row["id"]), vector, content_hash)
            for row, vector, content_hash in zip(pending_rows, vectors, pending_hashes)
        ]
        await run_db(
            db.set_embeddings, pairs, embedding_model=embedding_model_label(settings)
        )
        embedded += len(pending_rows)
        pending_rows.clear()
        pending_texts.clear()
        pending_hashes.clear()

    for scanned, row in enumerate(rows, start=1):
        # The steady-state scan (nothing pending) walks the whole library; yield so
        # a 100k-title pass cannot hold the event loop, and honor ``should_stop``.
        if scanned % SCAN_YIELD_EVERY == 0:
            await asyncio.sleep(0)
            if should_stop():
                return with_stage_stats(
                    {
                        "status": "interrupted",
                        "embedded": embedded,
                        "skipped": skipped,
                        "total": total,
                    },
                    stage_stats,
                )
        if embedded >= cycle_cap:
            remaining = total - skipped - embedded
            logger.info(
                "Semantic embeddings: cycle cap reached (%d embedded, ~%d remaining); "
                "will continue on next idle cycle",
                embedded,
                remaining,
            )
            return with_stage_stats(
                {
                    "status": "cycle_limit",
                    "embedded": embedded,
                    "skipped": skipped,
                    "total": total,
                    "remaining": remaining,
                    "batch_size": cycle_cap,
                    "has_more": True,
                    "demand_prioritized": demand_prioritized,
                },
                stage_stats,
            )

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
                return with_stage_stats(
                    {
                        "status": "interrupted",
                        "embedded": embedded,
                        "skipped": skipped,
                        "total": total,
                    },
                    stage_stats,
                )

    await _flush()

    logger.info(
        "Semantic embeddings complete: embedded=%d skipped=%d total=%d",
        embedded,
        skipped,
        total,
    )
    return with_stage_stats(
        {
            "status": "completed",
            "embedded": embedded,
            "skipped": skipped,
            "total": total,
            "batch_size": cycle_cap,
            "has_more": (await run_db(db.count_items_needing_embeddings)) > 0,
            "coverage_signals": coverage_signals,
            "demand_prioritized": demand_prioritized,
        },
        stage_stats,
    )


def register(scheduler: IdleScheduler) -> None:
    register_severity_task(
        scheduler,
        name=TASK_NAME,
        priority="P2",
        run_fn=run,
        run_interval_seconds=INTERVAL_SECONDS,
        enabled=True,
        description=(
            "Builds the plot similarity index used for related-title discovery. "
            f"Checks up to {MAX_ITEMS_PER_CYCLE} titles per run so large libraries "
            "catch up gradually without overwhelming the server."
        ),
        items_per_cycle=MAX_ITEMS_PER_CYCLE,
        catchup_gap_seconds=CATCHUP_GAP_SECONDS,
        progress_scope="embeddings_pending",
    )
