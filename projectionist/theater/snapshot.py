"""Build privacy-minimized lobby theater board snapshots."""

from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from projectionist.config_store import Settings, TheaterSettings
from projectionist.connectors.plex import PlexActiveSession, PlexClient
from projectionist.library.db import Database
from projectionist.library.feeds import feed_recently_added
from projectionist.theater.normalize import normalize_theater_settings

logger = logging.getLogger(__name__)

_PLAYING_STATES = frozenset({"playing", "paused"})


def _opaque_session_id(session: PlexActiveSession) -> str:
    raw = ":".join(
        (
            session.session_key or "",
            session.rating_key,
            session.source_user_key,
            session.client_identifier or "",
        )
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def household_source_keys(db: Database) -> Set[str]:
    """Plex session user keys that belong to linked Projectionist household members."""
    keys: Set[str] = set()
    try:
        for user in db.list_users(limit=500):
            if user.get("disabled"):
                continue
            plex_id = str(user.get("plex_user_id") or "").strip()
            if plex_id:
                keys.add(plex_id)
    except Exception:  # noqa: BLE001
        logger.debug("theater household user list failed", exc_info=True)
    try:
        from projectionist.watch_tracker.identity import list_mapped_source_keys

        for row in list_mapped_source_keys(db):
            key = str(row.get("source_user_key") or "").strip()
            if key:
                keys.add(key)
    except Exception:  # noqa: BLE001
        logger.debug("theater household alias list failed", exc_info=True)
    return keys


def _library_poster_row(
    db: Database,
    *,
    rating_key: str,
    parent_rating_key: Optional[str],
    media_type: str,
) -> Optional[Mapping[str, Any]]:
    """Resolve movie/show library art; episodes prefer the parent show poster."""
    keys: List[str] = []
    if media_type == "episode" and parent_rating_key:
        keys.append(str(parent_rating_key))
    keys.append(str(rating_key))
    for key in keys:
        if not key:
            continue
        try:
            row = db.library_item_by_rating_key(key)
        except Exception:  # noqa: BLE001
            row = None
        if row is not None:
            return row
    return None


def poster_proxy_path(rating_key: str) -> str:
    from urllib.parse import quote

    return f"/api/theater/poster?rk={quote(str(rating_key), safe='')}"


def _session_progress(session: PlexActiveSession) -> float:
    duration = session.duration_ms or 0
    progress = session.progress_ms or 0
    if duration <= 0:
        return 0.0
    return max(0.0, min(1.0, float(progress) / float(duration)))


def filter_sessions(
    sessions: Sequence[PlexActiveSession],
    *,
    audience: str,
    household_keys: Optional[Set[str]] = None,
) -> List[PlexActiveSession]:
    kept: List[PlexActiveSession] = []
    for session in sessions:
        state = str(session.state or "").strip().lower()
        if state not in {"playing", "paused"}:
            continue
        if audience == "household":
            keys = household_keys or set()
            if session.source_user_key not in keys:
                continue
        kept.append(session)
    return kept


def resolve_header_label(theater: TheaterSettings, *, watching: bool) -> str:
    if theater.header_mode == "static":
        label = str(theater.static_label or "").strip()
        return label or "NOW PLAYING"
    return "NOW PLAYING" if watching else "NOW AVAILABLE"


def build_available_deck(db: Database, *, limit: int = 16) -> List[Dict[str, str]]:
    try:
        feed = feed_recently_added(db, limit=limit, days=365, media_type="movie")
    except Exception:  # noqa: BLE001
        logger.debug("theater recently-added deck failed", exc_info=True)
        return []
    deck: List[Dict[str, str]] = []
    for item in feed.get("items") or []:
        rating_key = str(item.get("rating_key") or "").strip()
        poster = str(item.get("poster_url") or "").strip()
        if not rating_key or not poster:
            continue
        deck.append({"id": rating_key, "poster_url": poster_proxy_path(rating_key)})
        if len(deck) >= limit:
            break
    return deck


def enrich_sessions(
    db: Database,
    sessions: Sequence[PlexActiveSession],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for session in sessions:
        row = _library_poster_row(
            db,
            rating_key=session.rating_key,
            parent_rating_key=session.parent_rating_key,
            media_type=session.media_type,
        )
        if row is None:
            continue
        art_key = str(row["rating_key"] if "rating_key" in row.keys() else session.rating_key)
        raw_poster = row["poster_url"] if "poster_url" in row.keys() else ""
        poster = str(raw_poster or "").strip()
        if not poster:
            continue
        state = str(session.state or "").strip().lower() or "playing"
        out.append(
            {
                "id": _opaque_session_id(session),
                "poster_url": poster_proxy_path(art_key),
                "progress": _session_progress(session),
                "duration_ms": int(session.duration_ms or 0),
                "progress_ms": int(session.progress_ms or 0),
                "state": state if state in {"playing", "paused"} else "playing",
            }
        )
    return out


def build_board_snapshot(
    db: Database,
    settings: Settings,
    *,
    sessions: Optional[Sequence[PlexActiveSession]] = None,
    fetch_sessions: bool = True,
) -> Dict[str, Any]:
    theater = normalize_theater_settings(getattr(settings, "theater", None))
    active: List[PlexActiveSession] = list(sessions or [])
    if fetch_sessions and sessions is None and theater.enabled:
        if settings.plex_url and settings.plex_token:
            try:
                client = PlexClient(settings.plex_url, settings.plex_token, timeout=10)
                active = client.active_sessions()
            except Exception:  # noqa: BLE001
                logger.debug("theater active_sessions failed", exc_info=True)
                active = []

    household_keys: Optional[Set[str]] = None
    if theater.audience == "household":
        household_keys = household_source_keys(db)
    filtered = filter_sessions(
        active,
        audience=theater.audience,
        household_keys=household_keys,
    )
    board_sessions = enrich_sessions(db, filtered)
    watching = bool(board_sessions)

    if watching:
        mode = "now_playing"
        available: List[Dict[str, str]] = []
    elif theater.idle_mode == "now_available":
        mode = "now_available"
        available = build_available_deck(db, limit=16)
    else:
        mode = "empty"
        available = []

    header_label = resolve_header_label(theater, watching=watching)
    return {
        "enabled": bool(theater.enabled),
        "header_mode": theater.header_mode,
        "header_label": header_label,
        "orientation": theater.orientation,
        "multi_mode": theater.multi_mode,
        "idle_mode": theater.idle_mode,
        "rotate_seconds": theater.rotate_seconds,
        "mode": mode,
        "watching": watching,
        "sessions": board_sessions,
        "available": available,
    }


def session_signature(sessions: Sequence[Mapping[str, Any]]) -> str:
    parts = []
    for item in sessions:
        parts.append(
            f"{item.get('id')}:{item.get('state')}:{round(float(item.get('progress') or 0), 3)}"
        )
    return "|".join(parts)
