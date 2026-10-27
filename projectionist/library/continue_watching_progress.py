"""In-app playback progress for the Explore Continue Watching rail.

Plex on-deck (and the hub snapshot built from it) lags a play this process just
recorded. Notes here are applied onto that rail immediately. A background
on-deck refresh may replace the row only after these notes are merged, so the
next paint is not the previous snapshot.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# Long enough for on-deck to catch the timeline we just sent, short enough
# that a later Plex session on another device can win again.
PROGRESS_NOTE_TTL_SECONDS = 15 * 60.0

_LOCK = threading.Lock()
# (db path, rating key) -> note
_NOTES: Dict[tuple[str, str], Dict[str, Any]] = {}
_REFRESHERS: list[Callable[[Any], None]] = []


def register_continue_watching_refresh(callback: Callable[[Any], None]) -> None:
    """Explore hub registers a background on-deck refresh. One callback."""
    if callback not in _REFRESHERS:
        _REFRESHERS.append(callback)


def clear_continue_watching_progress_notes() -> None:
    """Test helper."""
    with _LOCK:
        _NOTES.clear()


def _db_path(db: Any) -> str:
    path = getattr(db, "path", None)
    return str(path or id(db))


def _note_key(db: Any, rating_key: str) -> tuple[str, str]:
    return (_db_path(db), str(rating_key or "").strip())


def note_playback_progress(
    db: Any,
    rating_key: str,
    view_offset_ms: int,
    duration_ms: int = 0,
    *,
    finished: bool = False,
) -> None:
    """Remember progress this process just wrote and refresh Continue Watching."""
    key = str(rating_key or "").strip()
    if not key or db is None:
        return
    show_key = _show_rating_key_for(db, key)
    note = {
        "rating_key": key,
        "show_rating_key": show_key,
        "view_offset_ms": max(0, int(view_offset_ms or 0)),
        "duration_ms": max(0, int(duration_ms or 0)),
        "finished": bool(finished) or max(0, int(view_offset_ms or 0)) <= 0,
        "noted_at": time.time(),
    }
    with _LOCK:
        path = _db_path(db)
        if show_key:
            stale = [
                stored
                for stored, existing in _NOTES.items()
                if stored[0] == path and str(existing.get("show_rating_key") or "") == show_key
            ]
            for stored in stale:
                _NOTES.pop(stored, None)
        _NOTES[_note_key(db, key)] = note
        _drop_expired_locked()
    for callback in list(_REFRESHERS):
        try:
            callback(db)
        except Exception:  # noqa: BLE001 — rail refresh must not break playback
            logger.debug("continue watching refresh failed", exc_info=True)


def _drop_expired_locked(now: Optional[float] = None) -> None:
    stamp = time.time() if now is None else float(now)
    expired = [
        key
        for key, note in _NOTES.items()
        if stamp - float(note.get("noted_at") or 0) > PROGRESS_NOTE_TTL_SECONDS
    ]
    for key in expired:
        _NOTES.pop(key, None)


def notes_for_db(db: Any) -> list[Dict[str, Any]]:
    path = _db_path(db)
    now = time.time()
    with _LOCK:
        _drop_expired_locked(now)
        return [dict(note) for (note_path, _key), note in _NOTES.items() if note_path == path]


def _item_matches(item: Dict[str, Any], rating_key: str, *, show_rating_key: str = "") -> bool:
    play = str(item.get("play_rating_key") or "")
    key = str(item.get("rating_key") or "")
    if play == rating_key or key == rating_key:
        return True
    show_key = str(show_rating_key or "").strip()
    if show_key and (key == show_key or play == show_key):
        return True
    return False


def _continue_watching_identity(item: Dict[str, Any]) -> str:
    rating_key = str(item.get("rating_key") or "")
    play_key = str(item.get("play_rating_key") or "")
    media_type = str(item.get("media_type") or "")
    episode_like = (
        media_type in {"show", "episode"}
        or item.get("continue_season") is not None
        or item.get("continue_episode") is not None
        or (bool(play_key) and bool(rating_key) and play_key != rating_key)
    )
    if episode_like and rating_key:
        return f"show:{rating_key}"
    return f"play:{play_key or rating_key}"


def _dedupe_continue_watching(items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    seen: set[str] = set()
    out: list[Dict[str, Any]] = []
    for item in items:
        ident = _continue_watching_identity(item)
        if not ident or ident in seen:
            continue
        seen.add(ident)
        out.append(item)
    return out


def _show_rating_key_for(db: Any, rating_key: str) -> str:
    try:
        episode = _episode_context(db, rating_key)
    except Exception:  # noqa: BLE001 — notes must not break playback
        return ""
    if episode is None:
        return ""
    return str(episode["show_rating_key"] or "").strip()


def _episode_context(db: Any, rating_key: str):
    with db.connect() as conn:
        return conn.execute(
            """
            SELECT e.*, s.title AS show_title, s.rating_key AS show_rating_key,
                   s.id AS show_id
            FROM library_episodes e
            LEFT JOIN library_items s ON s.id = e.show_item_id
            WHERE e.rating_key = ?
            """,
            (rating_key,),
        ).fetchone()


def _card_for_note(db: Any, note: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from projectionist.library.feeds import (  # lazy: feeds applies notes at the end of a build
        _continue_watching_resume_label,
        _feed_item,
    )

    rating_key = str(note["rating_key"])
    offset = int(note.get("view_offset_ms") or 0)
    duration = int(note.get("duration_ms") or 0)
    row = db.library_item_by_rating_key(rating_key)
    episode = None if row is not None else _episode_context(db, rating_key)
    if row is None and episode is not None:
        show_key = str(episode["show_rating_key"] or "")
        row = db.library_item_by_rating_key(show_key) if show_key else None
    if row is None:
        return None
    media_type = "episode" if episode is not None else str(row["media_type"] or "movie")
    season = int(episode["season_number"]) if episode is not None and episode["season_number"] is not None else None
    episode_number = (
        int(episode["episode_number"]) if episode is not None and episode["episode_number"] is not None else None
    )
    episode_title = str(episode["title"] or "") if episode is not None else ""
    play_key = str(episode["rating_key"]) if episode is not None else rating_key
    if duration <= 0:
        raw_duration = row["duration_ms"] if "duration_ms" in row.keys() else None
        duration = int(raw_duration or 0)
    resume = _continue_watching_resume_label(
        media_type=media_type,
        view_offset_ms=offset,
        duration_ms=duration,
        season_number=season,
        episode_number=episode_number,
        episode_title=episode_title,
    )
    extra: Dict[str, Any] = {
        "in_library": True,
        "card_kind": "continue_watching",
        "resume_label": resume,
        "view_offset_ms": offset,
        "duration_ms": duration or None,
        "play_rating_key": play_key,
        "watch_state": "partial",
    }
    if episode is not None:
        extra["continue_episode_title"] = episode_title
        extra["continue_season"] = season
        extra["continue_episode"] = episode_number
    return _feed_item(row, **extra)


def apply_known_continue_watching(db: Any, rail: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``rail`` with in-app progress merged over a Plex or local snapshot."""
    if not isinstance(rail, dict):
        return rail
    notes = sorted(notes_for_db(db), key=lambda note: float(note.get("noted_at") or 0))
    items = [dict(item) for item in (rail.get("items") or []) if isinstance(item, dict)]
    for note in notes:
        rating_key = str(note.get("rating_key") or "")
        if not rating_key:
            continue
        if note.get("finished") or int(note.get("view_offset_ms") or 0) <= 0:
            # Drop this episode only. A later on-deck episode of the same show stays.
            items = [item for item in items if not _item_matches(item, rating_key)]
            continue
        show_key = str(note.get("show_rating_key") or "").strip()
        card = _card_for_note(db, note)
        if card is None:
            for item in items:
                if not _item_matches(item, rating_key, show_rating_key=show_key):
                    continue
                item["view_offset_ms"] = int(note.get("view_offset_ms") or 0)
                if note.get("duration_ms"):
                    item["duration_ms"] = int(note["duration_ms"])
            continue
        if not show_key:
            card_play = str(card.get("play_rating_key") or "")
            card_key = str(card.get("rating_key") or "")
            if card_play and card_key and card_play != card_key:
                show_key = card_key
        items = [item for item in items if not _item_matches(item, rating_key, show_rating_key=show_key)]
        items.insert(0, card)
    items = _dedupe_continue_watching(items)
    updated = dict(rail)
    updated["items"] = items
    updated["total"] = len(items)
    updated.pop("pending", None)
    if items:
        updated["note"] = None
    elif not updated.get("note"):
        updated["note"] = (
            "Nothing in progress — start something in Plex, or wait for watch "
            "progress to sync."
        )
    return updated
