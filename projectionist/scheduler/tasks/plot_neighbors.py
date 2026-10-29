"""Idle trickle: cache plot neighbors + surprise scores from embeddings.

For each seed item (batch N/cycle), score candidates with exact cosine (+
surprise). When optional sqlite-vec is available it ANN-prefilters candidates
first; otherwise the full embedding set is scanned. Top-K rows land in
``item_neighbors`` — the durable read cache for Explore / Plot Lab /
``find_similar_titles``.

Catch-up mode prefers titles that already have embeddings but still lack
``item_neighbors`` rows, then falls back to rotating through the full embedding
set so every title eventually refreshes.

Default interval: 12 hours (auto-tune may shorten while backlog is large).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.db_io import run_db
from projectionist.library.neighbors import (
    DEFAULT_TOP_K,
    annotate_explainable_neighbors,
    refresh_neighbors_for_items,
)
from projectionist.scheduler.autotune import resolve_batch_size
from projectionist.scheduler.engine import IdleScheduler
from projectionist.scheduler.tasks.base_augmentation import register_severity_task
from projectionist.scheduler.tasks.kinship_augmentation import (
    KinshipMissAugmentationTask,
    stage_kinship_demand,
    with_stage_stats,
)
from projectionist.telemetry.kinship_miss import merge_preferred_ids, preferred_item_ids

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 43200  # 12 hours
# Paced follow-up while a backlog is draining (see scheduler/cadence.py).
CATCHUP_GAP_SECONDS = 180
SEEDS_PER_CYCLE = 15
CURSOR_KEY = "plot_neighbors_cursor"
TASK_NAME = "plot_neighbors"


class PlotNeighborsAugmentation(KinshipMissAugmentationTask):
    """Stage kinship-miss titles that still lack a neighbor cache."""

    action = "refresh_plot_neighbors"

    def __init__(self, db: Database) -> None:
        super().__init__(db, task_name=TASK_NAME)

    def item_still_needs(self, item_id: int) -> bool:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT e.item_id
                FROM embeddings e
                WHERE e.item_id = ?
                  AND NOT EXISTS (
                    SELECT 1 FROM item_neighbors n WHERE n.item_id = e.item_id
                  )
                """,
                (int(item_id),),
            ).fetchone()
        return row is not None


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del settings
    augmenter = PlotNeighborsAugmentation(db)
    stage_stats, interrupted = await stage_kinship_demand(augmenter, should_stop)
    if interrupted:
        return with_stage_stats({"status": "interrupted", "processed": 0}, stage_stats)

    # Ids only: ``db.get_embeddings()`` JSON-decodes every stored vector (hundreds
    # of MB on a large library) just to be counted and sorted. Wave 5 owns that
    # decode path — this task must keep using ``embedding_item_ids()``.
    emb_ids = db.embedding_item_ids()
    if len(emb_ids) < 2:
        return with_stage_stats(
            {"status": "completed", "processed": 0, "reason": "need_at_least_two_embeddings"},
            stage_stats,
        )

    batch_size = resolve_batch_size(db, TASK_NAME, SEEDS_PER_CYCLE)
    missing = db.item_ids_missing_neighbors(limit=batch_size)
    emb_id_set = set(emb_ids)
    # Owner demand (empty More Like This / relations / bridge) before cold catch-up.
    demand_seeds = [
        item_id
        for item_id in preferred_item_ids(db, limit=batch_size)
        if item_id in emb_id_set
    ]
    ordered = merge_preferred_ids(demand_seeds, missing, limit=batch_size)

    unique_seeds: List[int] = []
    seen: set[int] = set()

    for seed_id in ordered:
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
        return with_stage_stats(
            {
                "status": "completed",
                "processed": 0,
                "seeds": 0,
                "missing_before": len(missing),
            },
            stage_stats,
        )

    # Cosine/Jaccard over the full embedding set is CPU-heavy — leave the loop.
    processed = await run_db(
        refresh_neighbors_for_items, db, unique_seeds, top_k=DEFAULT_TOP_K
    )
    last_seed = unique_seeds[-1]
    db.set_config(CURSOR_KEY, str(last_seed))

    # Cheap pass: annotate legacy cosine-only rows with explainable + plot_link_json.
    legacy_seeds = [
        seed_id
        for seed_id in db.item_ids_needing_neighbor_explanation(limit=batch_size)
        if seed_id not in seen
    ]
    annotated = 0
    if legacy_seeds and not should_stop():
        annotated = await run_db(annotate_explainable_neighbors, db, legacy_seeds)

    remaining_missing = db.count_items_missing_neighbors()
    logger.info(
        "Plot neighbors trickle: processed=%s seeds=%s annotated=%s missing=%s library_embeddings=%s",
        processed,
        len(unique_seeds),
        annotated,
        remaining_missing,
        len(emb_ids),
    )
    return with_stage_stats(
        {
            "status": "completed",
            "processed": processed,
            "seeds": len(unique_seeds),
            "demand_prioritized": len(demand_seeds),
            "annotated_explanations": annotated,
            "top_k": DEFAULT_TOP_K,
            "cursor": last_seed,
            "batch_size": batch_size,
            "missing_neighbors": remaining_missing,
            "has_more": remaining_missing > 0 or bool(legacy_seeds),
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
        off_loop=True,
        description=(
            "Refreshes similar-title links from plot-similarity data. Prefers titles "
            "owners hit with an empty More Like This or Related shelf, then titles "
            f"that have no matches yet, then revisits about {SEEDS_PER_CYCLE} titles "
            "per run so large libraries catch up gradually."
        ),
        items_per_cycle=SEEDS_PER_CYCLE,
        catchup_gap_seconds=CATCHUP_GAP_SECONDS,
        progress_scope="neighbors_backlog",
    )
