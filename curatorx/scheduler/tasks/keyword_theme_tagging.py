"""Idle task: map TMDB keywords → controlled ``theme`` facets (no LLM).

Runs offline from keywords already stored on ``library_items``. Writes
``library_facets`` with ``facet_type='theme'`` via ``replace_facets_of_type``.

The optional ``llm_theme_tagging`` stub remains for a future LLM path; this
task is the supported production theme source.

Default interval: 24 hours (full-pass, like ``summary_motifs``).
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.theme_map import extract_theme_rows
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 86400  # 24 hours
TASK_NAME = "keyword_theme_tagging"


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del settings
    if should_stop():
        return {"status": "interrupted", "themes": 0}

    items = db.all_library_items()
    if should_stop():
        return {"status": "interrupted", "themes": 0}

    rows = extract_theme_rows(items)
    if should_stop():
        return {"status": "interrupted", "themes": 0}

    count = db.replace_facets_of_type("theme", rows)
    unique_items = len({r[0] for r in rows})
    logger.info(
        "Keyword theme tagging: wrote %s theme facet rows across %s titles",
        count,
        unique_items,
    )
    return {
        "status": "completed",
        "themes": count,
        "unique_items": unique_items,
        "library_size": len(items),
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name=TASK_NAME,
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Maps frequent TMDB keywords onto a small controlled theme vocabulary "
                "and writes theme facets for Plot Lab / Explore — no API key or LLM."
            ),
        )
    )
