"""Optional idle stub: LLM theme/trope tagging → ``facet_type='theme'``.

v1 does **not** call an LLM. Without ``llm_api_key`` the task skips cleanly.
With a key it still returns ``skipped`` / ``stub_pending`` so Explore and agent
tools can wire to ``theme`` facets without blocking on generation.

When implemented, write controlled-vocab theme strings via
``db.replace_facets_of_type('theme', ...)`` and/or ``title_relations`` rows with
``relation='llm_theme'``. Never invent themes from heuristics in the request path.

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
                "LLM theme tagging stays empty until an LLM is configured. "
                "Use motif facets + title_relations (collection/neighbor/shared_crew) for now."
            ),
        }

    # Stub: keep non-blocking even when a key exists. Full controlled-vocab
    # tagging lands in a later pass.
    logger.info("LLM theme tagging stub: pending implementation (key present)")
    return {
        "status": "skipped",
        "reason": "stub_pending",
        "tagged": 0,
        "note": (
            "Theme tagging stub — will write facet_type='theme' and/or "
            "relation='llm_theme' when implemented. Motifs remain available via summary_motifs."
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
                "Reserved for controlled-vocab LLM theme/trope tagging. Currently skips "
                "(no key, or stub pending) so Explore can wire to theme facets later "
                "without blocking motif and relation data."
            ),
        )
    )
