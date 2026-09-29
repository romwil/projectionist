"""Idle task: keep Live Channel lineups fed without manual Refill.

Motif / taste soft-cap stations and post-scan empties used to sit Empty until
an owner clicked Refill. This task watches Tunarr program counts and refills
any station with a stored ``station_meta`` recipe that is empty or below a
small threshold.

Default interval: 15 minutes (idle scheduler still waits for chat idle).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition
from projectionist.scheduler.run_log import emit_task_event

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 900  # 15 minutes
TASK_NAME = "live_channels_feed"
# Soft-cap motif stations often land ~30–80; treat <5 (or <1 min duration) as starved.
MIN_PROGRAMS = 5
MIN_DURATION_MS = 60_000
TASK_TIMEOUT_SECONDS = 600  # refill can scan Tunarr libraries


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}

    features = getattr(settings, "features", None)
    if not bool(getattr(features, "live_channels_enabled", False)):
        return {"status": "skipped", "reason": "live_channels_disabled"}

    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    if not url:
        return {"status": "skipped", "reason": "tunarr_url_unset"}

    emit_task_event("Checking Live Channel lineups")

    def _work() -> Dict[str, Any]:
        from projectionist.connectors.tunarr import TunarrClient
        from projectionist.live_channels.filters import maintain_live_channel_lineups

        client = TunarrClient(url, timeout=20)
        return maintain_live_channel_lineups(
            client,
            settings,
            min_programs=MIN_PROGRAMS,
            min_duration_ms=MIN_DURATION_MS,
            should_stop=should_stop,
        )

    result = await asyncio.to_thread(_work)
    refilled = list(result.get("refilled") or [])
    errors = list(result.get("errors") or [])
    logger.info(
        "live_channels_feed refilled=%s errors=%s note=%s",
        len(refilled),
        len(errors),
        result.get("note"),
    )
    emit_task_event(
        str(result.get("note") or "Live Channel feed check done"),
        refilled=len(refilled),
        errors=len(errors),
    )
    if should_stop():
        return {"status": "interrupted", **result}
    status = "completed" if result.get("ok", True) else "failed"
    if not refilled and not errors:
        status = "completed"
    return {
        "status": status,
        "refilled": len(refilled),
        "errors": len(errors),
        "detail": result,
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name=TASK_NAME,
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            timeout_seconds=TASK_TIMEOUT_SECONDS,
            run_fn=run,
            description=(
                "Keeps Live Channel lineups fed: when a station with a stored craft "
                "recipe is empty or very thin, Refill it automatically so the Guide "
                "and Plex Live TV stay airing without a daily manual Refill."
            ),
        )
    )
