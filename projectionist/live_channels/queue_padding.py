"""Rotational queue padding for Live channels (1.37.27).

A channel's own block (the titles it resolves from its show / collection / mood)
plays first. If that block is short, the rotation would snap straight back to
its first title when it ends. Queue padding fills the *spare* slots from a
default library feed so the block has somewhere to go before the rotation
continues.

Model (not "always append N"):

* ``up_to`` — the rotation holds **up to X** items (1–5).
* Playing items occupy slots first.
* ``spare = max(0, up_to - playing)``; the spare slots are filled from the
  chosen feed — ``recently_added`` or ``recently_released``.
* Order is the playing block, then the padded items; the lineup loops after
  that, so nothing snaps back the moment the playing block ends.

Examples: 4 playing + up to 5 → 1 pad; 5 playing + up to 5 → 0 pads;
0 playing + up to 3 → 3 pads from the feed.

This module holds the pure slot math + feed candidate query. Matching feed
titles to broadcast programs lives in ``publish.apply_queue_padding``.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence

QUEUE_PAD_MIN = 1
QUEUE_PAD_MAX = 5
QUEUE_PAD_DEFAULT_UP_TO = 5
QUEUE_PAD_FEED_ADDED = "recently_added"
QUEUE_PAD_FEED_RELEASED = "recently_released"
QUEUE_PAD_FEEDS = (QUEUE_PAD_FEED_ADDED, QUEUE_PAD_FEED_RELEASED)
QUEUE_PAD_DEFAULT_FEED = QUEUE_PAD_FEED_ADDED

QUEUE_PAD_FEED_LABELS = {
    QUEUE_PAD_FEED_ADDED: "Recently added",
    QUEUE_PAD_FEED_RELEASED: "Recently released",
}

# Look at a few extra feed rows: some titles may not be in the broadcast catalog.
_CANDIDATE_MULTIPLIER = 6
_CANDIDATE_FLOOR = 12


def default_queue_pad() -> Dict[str, Any]:
    return {"up_to": QUEUE_PAD_DEFAULT_UP_TO, "feed": QUEUE_PAD_DEFAULT_FEED}


def normalize_queue_pad(value: Any) -> Dict[str, Any]:
    """Clamp a stored / incoming queue-pad setting.

    Falsy or non-mapping input means "not set" (``{}``) so existing channels keep
    their old behaviour. A mapping is clamped: ``up_to`` into 1–5, unknown feeds
    fall back to Recently added.
    """
    if not isinstance(value, Mapping) or not value:
        return {}
    try:
        up_to = int(value.get("up_to", QUEUE_PAD_DEFAULT_UP_TO))
    except (TypeError, ValueError):
        up_to = QUEUE_PAD_DEFAULT_UP_TO
    up_to = max(QUEUE_PAD_MIN, min(QUEUE_PAD_MAX, up_to))
    feed = str(value.get("feed") or QUEUE_PAD_DEFAULT_FEED).strip().lower()
    if feed not in QUEUE_PAD_FEEDS:
        feed = QUEUE_PAD_DEFAULT_FEED
    return {"up_to": up_to, "feed": feed}


def pad_slots(up_to: Any, playing_count: Any) -> int:
    """Spare slots to fill: ``max(0, up_to - playing)`` with ``up_to`` clamped 1–5."""
    try:
        cap = int(up_to)
    except (TypeError, ValueError):
        cap = QUEUE_PAD_DEFAULT_UP_TO
    cap = max(QUEUE_PAD_MIN, min(QUEUE_PAD_MAX, cap))
    try:
        playing = max(0, int(playing_count))
    except (TypeError, ValueError):
        playing = 0
    return max(0, cap - playing)


def queue_pad_plan(queue_pad: Any, playing_count: Any) -> Dict[str, Any]:
    """Slot math for a normalized setting; ``{}`` setting → zero pads."""
    setting = normalize_queue_pad(queue_pad)
    if not setting:
        return {"enabled": False, "up_to": 0, "feed": "", "playing": int(playing_count or 0), "pad": 0}
    playing = max(0, int(playing_count or 0))
    return {
        "enabled": True,
        "up_to": setting["up_to"],
        "feed": setting["feed"],
        "playing": playing,
        "pad": pad_slots(setting["up_to"], playing),
    }


def queue_pad_feed_label(feed: Any) -> str:
    return QUEUE_PAD_FEED_LABELS.get(str(feed or "").strip().lower(), "")


def queue_pad_options() -> Dict[str, Any]:
    """Owner craft-form options: the 1–5 dropdown + the two feeds."""
    return {
        "default": default_queue_pad(),
        "up_to": list(range(QUEUE_PAD_MIN, QUEUE_PAD_MAX + 1)),
        "feeds": [
            {"id": feed, "label": QUEUE_PAD_FEED_LABELS[feed]} for feed in QUEUE_PAD_FEEDS
        ],
    }


def _media_type_clause(media_scope: str) -> str:
    scope = str(media_scope or "").strip().lower()
    if scope == "movies":
        return "AND media_type = 'movie'"
    if scope == "tv":
        return "AND media_type = 'show'"
    return ""


def feed_candidates(
    db: Any,
    feed: str,
    *,
    count: int,
    media_scope: str = "both",
    exclude_rating_keys: Sequence[str] = (),
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Newest library titles for a feed, most relevant first.

    No fixed day window: a quiet library should still have somewhere to go, so
    the feed is simply "the newest N" (released titles never in the future).
    """
    wanted = max(0, int(count or 0))
    if db is None or wanted <= 0:
        return []
    feed_id = str(feed or QUEUE_PAD_DEFAULT_FEED).strip().lower()
    if feed_id not in QUEUE_PAD_FEEDS:
        feed_id = QUEUE_PAD_DEFAULT_FEED
    limit = max(_CANDIDATE_FLOOR, wanted * _CANDIDATE_MULTIPLIER)
    skip = {str(k).strip() for k in exclude_rating_keys if str(k).strip()}
    scope_sql = _media_type_clause(media_scope)
    if feed_id == QUEUE_PAD_FEED_ADDED:
        sql = f"""
            SELECT id, rating_key, title, media_type, year, added_at
            FROM library_items
            WHERE rating_key IS NOT NULL AND rating_key != ''
              AND added_at IS NOT NULL {scope_sql}
            ORDER BY added_at DESC, title ASC
            LIMIT ?
        """
        params: tuple = (limit,)
    else:
        today_iso = (today or date.today()).isoformat()
        released = (
            "COALESCE(NULLIF(CASE WHEN media_type = 'show' THEN first_air_date "
            "ELSE release_date END, ''), NULLIF(release_date, ''), "
            "NULLIF(first_air_date, ''))"
        )
        sql = f"""
            SELECT id, rating_key, title, media_type, year, {released} AS released_on
            FROM library_items
            WHERE rating_key IS NOT NULL AND rating_key != ''
              AND {released} IS NOT NULL AND {released} <= ? {scope_sql}
            ORDER BY {released} DESC, title ASC
            LIMIT ?
        """
        params = (today_iso, limit)
    try:
        with db.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
    except Exception:  # noqa: BLE001
        return []
    out: List[Dict[str, Any]] = []
    for row in rows:
        key = str(row["rating_key"] or "").strip()
        if not key or key in skip:
            continue
        out.append(
            {
                "id": int(row["id"]),
                "rating_key": key,
                "title": str(row["title"] or ""),
                "media_type": str(row["media_type"] or ""),
                "year": row["year"],
            }
        )
    return out


def order_padded_programs(
    playing: Sequence[Mapping[str, Any]],
    pads: Sequence[Mapping[str, Any]],
    *,
    shuffle_playing: bool = False,
    rng: Any = None,
) -> List[Dict[str, Any]]:
    """Playing block first, then pads. Pads are tagged ``queue_pad`` so the
    lineup builder keeps this order instead of reshuffling it.
    """
    block = [dict(p) for p in playing]
    if shuffle_playing and len(block) > 1:
        shuffler = rng
        if shuffler is None:
            import random as _random

            shuffler = _random
        shuffler.shuffle(block)
    tail = [{**dict(p), "queue_pad": True} for p in pads]
    return block + tail


def has_queue_pad(programs: Sequence[Mapping[str, Any]]) -> bool:
    return any(isinstance(p, Mapping) and p.get("queue_pad") for p in programs or ())

