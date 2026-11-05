"""Likely pick watches: a native-Plex play after Projectionist surfaced that title (GRO-010).

This is a separate, weaker tier from the verified in-app count (GRO-014,
``telemetry/attribution.py``). A row means: the same person had this title
surfaced to them (a household share, or a recommendation / digest / nudge /
library-share notification) and then played it in Plex within seven days. It
never upgrades a play to "from a pick" and never feeds ``plays_from_picks``.

Rows are per person, exported in "Download my data", erased with that person's
memory, and pruned after ``RETENTION_DAYS``.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

LIKELY_WINDOW_SECONDS = 7 * 86400
RETENTION_DAYS = 90
NOTIFICATION_SURFACES = ("recommendation", "digest", "nudge", "library-share")

_SURFACED_SQL = """
    SELECT to_user_id AS user_id, rating_key, 'share' AS surface, created_at AS surfaced_at
    FROM user_recommendations
    WHERE rating_key IS NOT NULL AND rating_key != '' AND created_at >= ?
    UNION ALL
    SELECT user_id, rating_key, kind AS surface, created_at AS surfaced_at
    FROM user_notifications
    WHERE rating_key IS NOT NULL AND rating_key != '' AND created_at >= ?
      AND kind IN ({kinds})
""".format(kinds=", ".join("?" for _ in NOTIFICATION_SURFACES))

_MATCH_SQL = f"""
    WITH surfaced AS ({_SURFACED_SQL})
    SELECT s.user_id, s.rating_key, s.surface, s.surfaced_at,
           w.id AS watch_event_id, w.occurred_at_ms
    FROM surfaced s
    JOIN watch_events w
      ON w.user_id = s.user_id
     AND (w.rating_key = s.rating_key OR w.parent_rating_key = s.rating_key)
     AND w.duplicate_of_event_id IS NULL
     AND w.occurred_at_ms >= CAST(s.surfaced_at * 1000 AS INTEGER)
     AND w.occurred_at_ms <= CAST((s.surfaced_at + ?) * 1000 AS INTEGER)
    ORDER BY s.user_id, s.rating_key, s.surfaced_at, w.occurred_at_ms
"""


def refresh_likely_pick_watches(
    db: Any, *, now: Optional[float] = None, app_version: Optional[str] = None
) -> Dict[str, int]:
    """Record the first Plex play after each surfacing (same person, ≤7 days); prune old rows."""
    if app_version is None:
        from projectionist import __version__ as app_version
    current = float(now if now is not None else time.time())
    horizon = current - RETENTION_DAYS * 86400
    inserted = 0
    with db.connect() as conn:
        rows = conn.execute(
            _MATCH_SQL,
            (horizon, horizon, *NOTIFICATION_SURFACES, LIKELY_WINDOW_SECONDS),
        ).fetchall()
        seen: set[tuple[str, str, float]] = set()
        for row in rows:
            surfacing = (str(row["user_id"]), str(row["rating_key"]), float(row["surfaced_at"]))
            if surfacing in seen:
                continue
            seen.add(surfacing)
            watched_at = int(row["occurred_at_ms"]) / 1000.0
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO pick_watched_likely (
                    id, user_id, rating_key, surface, surfaced_at, watched_at,
                    lag_hours, watch_event_id, app_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    uuid.uuid4().hex,
                    surfacing[0],
                    surfacing[1],
                    str(row["surface"]),
                    surfacing[2],
                    watched_at,
                    round((watched_at - surfacing[2]) / 3600.0, 2),
                    str(row["watch_event_id"]),
                    app_version,
                    current,
                ),
            )
            inserted += int(cur.rowcount or 0)
        pruned = conn.execute(
            "DELETE FROM pick_watched_likely WHERE watched_at < ?", (horizon,)
        ).rowcount
    return {"inserted": inserted, "pruned": int(pruned or 0)}


def likely_pick_watch_count(db: Any, *, days: int = 7, now: Optional[float] = None) -> int:
    cutoff = float(now if now is not None else time.time()) - int(days) * 86400
    with db.connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM pick_watched_likely WHERE watched_at >= ?", (cutoff,)
        ).fetchone()
    return int(row["c"] if row else 0)
