"""Optional future idle stub: LLM theme/trope tagging → ``facet_type='theme'``.

**Production themes come from** ``keyword_theme_tagging`` (local keyword→theme
map, no LLM). This task stays registered so Admin history and Explore wiring
keep a stable name for a future LLM enrichment path.

v1 does **not** call an LLM. Without ``llm_api_key`` the task skips cleanly.
With a key it still returns ``skipped`` / ``stub_pending`` — do not rely on it
for theme facets; enable/run ``keyword_theme_tagging`` instead.

Default interval: 24 hours.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 86400  # 24 hours


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    del db
    if should_stop():
        return {"status": "interrupted", "tagged": 0}

    if not (settings.llm_api_key or "").strip():
        return {
            "status": "skipped",
            "reason": "no_llm_api_key",
            "tagged": 0,
            "note": (
                "LLM theme tagging is an unused future path. Themes are written by "
                "keyword_theme_tagging from TMDB keywords (no LLM)."
            ),
        }

    # Stub: keep non-blocking even when a key exists. Controlled-vocab LLM
    # enrichment may land later; keyword_theme_tagging remains the source of truth.
    logger.info("LLM theme tagging stub: pending implementation (key present)")
    return {
        "status": "skipped",
        "reason": "stub_pending",
        "tagged": 0,
        "note": (
            "Theme tagging via LLM is stubbed. Run keyword_theme_tagging for "
            "facet_type='theme' from local keyword maps."
        ),
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="llm_theme_tagging",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Reserved optional LLM theme enrichment (currently skips). "
                "Production themes come from keyword_theme_tagging (offline keyword map)."
            ),
        )
    )
