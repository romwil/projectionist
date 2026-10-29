"""Idle task: map TMDB keywords → controlled ``theme`` facets (no LLM).

Runs offline from keywords already stored on ``library_items``. Writes
``library_facets`` with ``facet_type='theme'`` via ``replace_facets_of_type``.

This task is the supported production theme source.

Default interval: 24 hours (full-pass, like ``summary_motifs``).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.theme_map import extract_theme_rows
from projectionist.scheduler.engine import IdleScheduler
from projectionist.scheduler.tasks.base_augmentation import register_severity_task
from projectionist.scheduler.tasks.coverage_signals import emit_unmapped_keyword_signals
from projectionist.scheduler.tasks.kinship_augmentation import (
    KinshipMissAugmentationTask,
    stage_kinship_demand,
    with_stage_stats,
)
from projectionist.telemetry.kinship_miss import preferred_item_ids

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 86400  # 24 hours
TASK_NAME = "keyword_theme_tagging"


class KeywordThemeAugmentation(KinshipMissAugmentationTask):
    """Consume kinship-miss demand; unmapped keywords stay on coverage_deficit_audit."""

    action = "map_keyword_themes"
    stage_when_needed = False

    def __init__(self, db: Database) -> None:
        super().__init__(db, task_name=TASK_NAME)


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del settings
    augmenter = KeywordThemeAugmentation(db)
    stage_stats, interrupted = await stage_kinship_demand(augmenter, should_stop)
    if interrupted:
        return with_stage_stats({"status": "interrupted", "themes": 0}, stage_stats)

    items = db.all_library_items()
    if should_stop():
        return with_stage_stats({"status": "interrupted", "themes": 0}, stage_stats)

    prefer_ids = preferred_item_ids(db, limit=25)
    if prefer_ids:
        order = {int(item_id): idx for idx, item_id in enumerate(prefer_ids)}
        items = sorted(
            items,
            key=lambda row: order.get(int(row["id"]), 10_000_000),
        )

    rows = extract_theme_rows(items)
    if should_stop():
        return with_stage_stats({"status": "interrupted", "themes": 0}, stage_stats)

    count = db.replace_facets_of_type("theme", rows)
    unique_items = len({r[0] for r in rows})
    signals = emit_unmapped_keyword_signals(items)
    logger.info(
        "Keyword theme tagging: wrote %s theme facet rows across %s titles; emitted %s keyword signals",
        count,
        unique_items,
        signals,
    )
    return with_stage_stats(
        {
            "status": "completed",
            "themes": count,
            "unique_items": unique_items,
            "library_size": len(items),
            "coverage_signals": signals,
            "demand_prioritized": len(prefer_ids),
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
            "Maps frequent TMDB keywords onto a small controlled theme vocabulary "
            "and writes theme facets for Plot Lab / Explore — no API key or LLM."
        ),
    )
