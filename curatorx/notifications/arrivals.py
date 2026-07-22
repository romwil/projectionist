"""Arrival notifications when gap / watched-for titles land in the library."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Set

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.feeds import feed_recently_added
from curatorx.notifications.service import deliver_notification

logger = logging.getLogger(__name__)

ARRIVAL_CURSOR_KEY = "arrival_notifications_last_seen_at"


def _gap_tmdb_ids(db: Database) -> Set[int]:
    """Collect TMDB ids previously flagged as collection gaps."""
    ids: Set[int] = set()
    try:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT results_json FROM cached_gap_analysis WHERE analysis_key = 'director_gaps'"
            ).fetchone()
    except Exception:  # noqa: BLE001
        return ids
    if row is None:
        return ids
    try:
        gaps = json.loads(row["results_json"] or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return ids
    if not isinstance(gaps, list):
        return ids
    for gap in gaps:
        if not isinstance(gap, dict):
            continue
        missing = gap.get("missing") or gap.get("missing_titles") or []
        if isinstance(missing, list):
            for item in missing:
                if isinstance(item, dict) and item.get("tmdb_id") is not None:
                    try:
                        ids.add(int(item["tmdb_id"]))
                    except (TypeError, ValueError):
                        continue
        # Some caches store titles inline on the gap row.
        if gap.get("tmdb_id") is not None:
            try:
                ids.add(int(gap["tmdb_id"]))
            except (TypeError, ValueError):
                pass
    return ids


def _watchlist_interest_by_tmdb(db: Database) -> Dict[int, List[str]]:
    """Map tmdb_id → user ids who have the title on a watchlist pin."""
    interest: Dict[int, List[str]] = {}
    try:
        with db.connect() as conn:
            # watchlist pins table shape from watchlist mixin
            tables = {
                str(r[0])
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "watchlist_pins" not in tables:
                return interest
            rows = conn.execute(
                """
                SELECT user_id, tmdb_id FROM watchlist_pins
                WHERE tmdb_id IS NOT NULL
                """
            ).fetchall()
    except Exception:  # noqa: BLE001
        return interest
    for row in rows:
        try:
            tmdb_id = int(row["tmdb_id"])
            user_id = str(row["user_id"])
        except (TypeError, ValueError, KeyError):
            continue
        interest.setdefault(tmdb_id, []).append(user_id)
    return interest


def notify_arrivals(
    db: Database,
    settings: Settings,
    *,
    now: Optional[float] = None,
    lookback_days: int = 3,
) -> Dict[str, Any]:
    """Create arrival notifications for newly added gap / watchlist titles."""
    ts = time.time() if now is None else float(now)
    last_seen_raw = db.get_config(ARRIVAL_CURSOR_KEY) if hasattr(db, "get_config") else None
    try:
        last_seen = float(last_seen_raw) if last_seen_raw else ts - lookback_days * 86400
    except (TypeError, ValueError):
        last_seen = ts - lookback_days * 86400

    try:
        recent = feed_recently_added(db, limit=40, days=lookback_days)
    except Exception:  # noqa: BLE001
        recent = {"items": []}
    items = list(recent.get("items") or [])
    gap_ids = _gap_tmdb_ids(db)
    watchlist_interest = _watchlist_interest_by_tmdb(db)

    owners = [
        str(u["id"])
        for u in db.list_users(limit=50)
        if u.get("role") == "owner" and not u.get("disabled")
    ]
    created = 0
    emailed = 0
    newest_seen = last_seen

    for item in items:
        added_at = item.get("added_at") or item.get("created_at") or 0
        try:
            added_ts = float(added_at)
        except (TypeError, ValueError):
            added_ts = ts
        if added_ts <= last_seen:
            continue
        newest_seen = max(newest_seen, added_ts)
        tmdb_id = item.get("tmdb_id")
        try:
            tmdb_int = int(tmdb_id) if tmdb_id is not None else None
        except (TypeError, ValueError):
            tmdb_int = None
        is_gap = tmdb_int is not None and tmdb_int in gap_ids
        interested = list(watchlist_interest.get(tmdb_int or -1, []))
        if not is_gap and not interested:
            continue

        title = str(item.get("title") or "A title").strip()
        year = item.get("year")
        year_bit = f" ({year})" if year else ""
        headline = f"Now in your library: {title}{year_bit}"
        why = "A collection gap just closed." if is_gap else "Something from a watchlist just arrived."
        recipients: List[str] = []
        if is_gap:
            recipients.extend(owners)
        recipients.extend(interested)
        # de-dupe
        seen_users: Set[str] = set()
        for uid in recipients:
            if not uid or uid in seen_users:
                continue
            seen_users.add(uid)
            related = f"arrival-{item.get('rating_key') or tmdb_int or title}-{uid}"
            existing = db.find_notification_by_related(uid, kind="arrival", related_id=related)
            if existing:
                continue
            result = deliver_notification(
                db,
                settings,
                user_id=uid,
                kind="arrival",
                title=headline,
                body=why,
                payload={"source": "gap" if is_gap else "watchlist"},
                media_type=item.get("media_type"),
                tmdb_id=tmdb_int,
                rating_key=str(item["rating_key"]) if item.get("rating_key") else None,
                year=int(year) if year is not None else None,
                poster_url=item.get("poster_url"),
                related_id=related,
                email_subject=headline,
            )
            if result.get("notification"):
                created += 1
            if result.get("emailed"):
                emailed += 1

    if hasattr(db, "set_config"):
        db.set_config(ARRIVAL_CURSOR_KEY, str(newest_seen))
    return {"created": created, "emailed": emailed, "scanned": len(items)}
