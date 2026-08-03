"""Idle tasks: Year in Review tease (late Dec) and drop (early Jan)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition
from projectionist.year_in_review.delivery import (
    current_calendar_year,
    deliver_year_in_review,
    in_drop_window,
    in_tease_window,
    prior_calendar_year,
)

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 24 * 3600


async def run_tease(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}
    if not in_tease_window():
        return {"status": "skipped", "reason": "outside_tease_window"}
    year = current_calendar_year()  # tease for the year that's ending
    result = deliver_year_in_review(db, settings, year=year, status_hint="tease")
    logger.info("YIR tease year=%s delivered=%s", year, result.get("delivered"))
    return {"status": "completed", **result}


async def run_drop(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted"}
    if not in_drop_window():
        return {"status": "skipped", "reason": "outside_drop_window"}
    year = prior_calendar_year()
    result = deliver_year_in_review(db, settings, year=year, status_hint="ready")
    logger.info("YIR drop year=%s delivered=%s", year, result.get("delivered"))
    return {"status": "completed", **result}


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="year_in_review_tease",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run_tease,
            description=(
                "Late December soft tease for opted-in members with enough "
                "watch-tracker signal for the ending year."
            ),
        )
    )
    scheduler.register(
        TaskDefinition(
            name="year_in_review_drop",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run_drop,
            description=(
                "Early January Year in Review drop for the prior calendar year "
                "(inbox + email deep link)."
            ),
        )
    )
