"""Idle task: scan for release-date anniversaries and "watched on this day".

Finds library items whose release month+day matches today, producing
"On This Day" entries like "Released 10 years ago today."  Also detects
"You watched X exactly N months ago today."

Results are stored in a ``daily_anniversaries`` table, cleared and rebuilt
each run for the current date.

Default interval: 24 hours (run once daily).
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 86400  # 24 hours
WATCHED_LOOKBACK_MONTHS = (1, 3, 6, 12)


def _ensure_table(db: Database) -> None:
    with db.connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_anniversaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER NOT NULL,
                anniversary_type TEXT NOT NULL,
                anniversary_text TEXT NOT NULL,
                scanned_date TEXT NOT NULL,
                FOREIGN KEY(item_id) REFERENCES library_items(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_anniversaries_date ON daily_anniversaries(scanned_date)"
        )


def _parse_year_from_item(row: Any) -> int | None:
    """Extract release year from the library item."""
    y = row["year"]
    if y is not None:
        try:
            return int(y)
        except (ValueError, TypeError):
            pass
    return None


def _months_ago(today: date, months: int) -> date:
    """Return the date *months* months before *today*, clamping day to month max."""
    month = today.month - months
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    import calendar

    max_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(today.day, max_day))


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    _ensure_table(db)
    today = date.today()
    scanned_date = today.isoformat()

    with db.connect() as conn:
        conn.execute(
            "DELETE FROM daily_anniversaries WHERE scanned_date = ?",
            (scanned_date,),
        )

    rows = list(db.all_library_items())
    anniversaries: List[Dict[str, Any]] = []

    for idx, row in enumerate(rows):
        if idx % 100 == 0 and should_stop():
            return {"status": "interrupted", "found": len(anniversaries)}

        item_id = int(row["id"])
        year = _parse_year_from_item(row)

        # Release date anniversary (month+day match, different year).
        if year is not None and year != today.year:
            try:
                release = date(year, today.month, today.day)
            except ValueError:
                release = None
            if release is not None and release.month == today.month and release.day == today.day:
                age = today.year - year
                label = f"Released {age} year{'s' if age != 1 else ''} ago today"
                anniversaries.append(
                    {
                        "item_id": item_id,
                        "anniversary_type": "release_anniversary",
                        "anniversary_text": label,
                    }
                )

        # "Watched N months ago today" detection.
        last_viewed = row["last_viewed_at"]
        if last_viewed is not None:
            try:
                viewed_dt = datetime.fromtimestamp(int(last_viewed)).date()
            except (ValueError, TypeError, OSError):
                viewed_dt = None
            if viewed_dt is not None:
                for m in WATCHED_LOOKBACK_MONTHS:
                    target = _months_ago(today, m)
                    if viewed_dt == target:
                        label = f"Watched {m} month{'s' if m != 1 else ''} ago today"
                        anniversaries.append(
                            {
                                "item_id": item_id,
                                "anniversary_type": "watched_anniversary",
                                "anniversary_text": label,
                            }
                        )
                        break

    if anniversaries:
        with db.connect() as conn:
            conn.executemany(
                """
                INSERT INTO daily_anniversaries (item_id, anniversary_type, anniversary_text, scanned_date)
                VALUES (:item_id, :anniversary_type, :anniversary_text, :scanned_date)
                """,
                [{**a, "scanned_date": scanned_date} for a in anniversaries],
            )

    logger.info("Anniversary scanner: found %d items for %s", len(anniversaries), scanned_date)
    return {"status": "completed", "found": len(anniversaries), "date": scanned_date}


def register(scheduler: IdleScheduler) -> None:
    _ensure_table_at_import = True
    scheduler.register(
        TaskDefinition(
            name="anniversary_scanner",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
        )
    )
