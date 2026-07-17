"""Idle trickle: cache plot neighbors + surprise scores from embeddings.

For each seed item (batch N/cycle), compute pure-Python cosine against all
stored embeddings, keep top-K, and store ``surprise_score`` = high cosine with
low genre/keyword/credits Jaccard overlap.

Architecture note: sqlite-vec (or similar ANN) can later prefilter candidates;
this task and ``item_neighbors`` stay the durable read cache for Explore /
Plot Lab / ``find_similar_titles``.

Default interval: 12 hours.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.neighbors import DEFAULT_TOP_K, refresh_neighbors_for_items
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 43200  # 12 hours
SEEDS_PER_CYCLE = 15
CURSOR_KEY = "plot_neighbors_cursor"


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted", "processed": 0}

    embeddings = db.get_embeddings()
    if len(embeddings) < 2:
        return {"status": "completed", "processed": 0, "reason": "need_at_least_two_embeddings"}

    emb_ids = sorted(item_id for item_id, _ in embeddings)
    raw_cursor = db.get_config(CURSOR_KEY) or "0"
    try:
        cursor = int(raw_cursor)
    except (TypeError, ValueError):
        cursor = 0

    # Rotate through embedding ids so every title eventually gets neighbors.
    start_idx = 0
    for idx, item_id in enumerate(emb_ids):
        if item_id > cursor:
            start_idx = idx
            break
    else:
        start_idx = 0

    seed_ids: List[int] = []
    for offset in range(SEEDS_PER_CYCLE):
        seed_ids.append(emb_ids[(start_idx + offset) % len(emb_ids)])
        if should_stop():
            break

    # Deduplicate while preserving order (small cycle wrap).
    seen: set[int] = set()
    unique_seeds = []
    for seed_id in seed_ids:
        if seed_id in seen:
            continue
        seen.add(seed_id)
        unique_seeds.append(seed_id)

    processed = refresh_neighbors_for_items(db, unique_seeds, top_k=DEFAULT_TOP_K)
    last_seed = unique_seeds[-1] if unique_seeds else cursor
    db.set_config(CURSOR_KEY, str(last_seed))

    logger.info(
        "Plot neighbors trickle: processed=%s seeds=%s library_embeddings=%s",
        processed,
        len(unique_seeds),
        len(emb_ids),
    )
    return {
        "status": "completed",
        "processed": processed,
        "seeds": len(unique_seeds),
        "top_k": DEFAULT_TOP_K,
        "cursor": last_seed,
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="plot_neighbors",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Caches plot-neighbor links and surprise scores from embeddings for Explore "
                f"and Plot Lab. Rotates through about {SEEDS_PER_CYCLE} seed titles per run "
                "until the whole embedded library has been refreshed."
            ),
            items_per_cycle=SEEDS_PER_CYCLE,
            progress_scope="embeddings_pass",
        )
    )
