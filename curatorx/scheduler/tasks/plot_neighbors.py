"""Idle trickle: cache plot neighbors + surprise scores from embeddings.

For each seed item (batch N/cycle), compute pure-Python cosine against all
stored embeddings, keep top-K, and store ``surprise_score`` = high cosine with
low genre/keyword/credits Jaccard overlap.

Catch-up mode prefers titles that already have embeddings but still lack
``item_neighbors`` rows, then falls back to rotating through the full embedding
set so every title eventually refreshes.

Architecture note: sqlite-vec (or similar ANN) can later prefilter candidates;
this task and ``item_neighbors`` stay the durable read cache for Explore /
Plot Lab / ``find_similar_titles``.

Default interval: 12 hours (auto-tune may shorten while backlog is large).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.neighbors import DEFAULT_TOP_K, refresh_neighbors_for_items
from curatorx.scheduler.autotune import resolve_batch_size
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 43200  # 12 hours
SEEDS_PER_CYCLE = 15
CURSOR_KEY = "plot_neighbors_cursor"
TASK_NAME = "plot_neighbors"


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del settings
    if should_stop():
        return {"status": "interrupted", "processed": 0}

    embeddings = db.get_embeddings()
    if len(embeddings) < 2:
        return {"status": "completed", "processed": 0, "reason": "need_at_least_two_embeddings"}

    batch_size = resolve_batch_size(db, TASK_NAME, SEEDS_PER_CYCLE)
    emb_ids = sorted(item_id for item_id, _ in embeddings)
    missing = db.item_ids_missing_neighbors(limit=batch_size)

    unique_seeds: List[int] = []
    seen: set[int] = set()

    # Prefer catch-up seeds that still have no neighbor rows.
    for seed_id in missing:
        if seed_id in seen:
            continue
        seen.add(seed_id)
        unique_seeds.append(seed_id)
        if len(unique_seeds) >= batch_size or should_stop():
            break

    # Fill remaining batch by rotating through embeddings (refresh pass).
    if len(unique_seeds) < batch_size and not should_stop():
        raw_cursor = db.get_config(CURSOR_KEY) or "0"
        try:
            cursor = int(raw_cursor)
        except (TypeError, ValueError):
            cursor = 0

        start_idx = 0
        for idx, item_id in enumerate(emb_ids):
            if item_id > cursor:
                start_idx = idx
                break
        else:
            start_idx = 0

        offset = 0
        while len(unique_seeds) < batch_size and offset < len(emb_ids):
            if should_stop():
                break
            seed_id = emb_ids[(start_idx + offset) % len(emb_ids)]
            offset += 1
            if seed_id in seen:
                continue
            seen.add(seed_id)
            unique_seeds.append(seed_id)

    if not unique_seeds:
        return {"status": "completed", "processed": 0, "seeds": 0, "missing_before": len(missing)}

    processed = refresh_neighbors_for_items(db, unique_seeds, top_k=DEFAULT_TOP_K)
    last_seed = unique_seeds[-1]
    db.set_config(CURSOR_KEY, str(last_seed))

    remaining_missing = db.count_items_missing_neighbors()
    logger.info(
        "Plot neighbors trickle: processed=%s seeds=%s missing=%s library_embeddings=%s",
        processed,
        len(unique_seeds),
        remaining_missing,
        len(emb_ids),
    )
    return {
        "status": "completed",
        "processed": processed,
        "seeds": len(unique_seeds),
        "top_k": DEFAULT_TOP_K,
        "cursor": last_seed,
        "batch_size": batch_size,
        "missing_neighbors": remaining_missing,
        "has_more": remaining_missing > 0,
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name=TASK_NAME,
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Caches plot-neighbor links and surprise scores from embeddings for Explore "
                f"and Plot Lab. Prefers titles still missing neighbor rows, then rotates about "
                f"{SEEDS_PER_CYCLE} seeds per run (batch auto-tunes from measured history)."
            ),
            items_per_cycle=SEEDS_PER_CYCLE,
            progress_scope="neighbors_backlog",
        )
    )
