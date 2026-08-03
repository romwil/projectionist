"""Mark library titles watched/unwatched in CuratorX and optionally on Plex."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

from projectionist.config_store import Settings
from projectionist.connectors.plex import PlexClient, cached_machine_identifier
from projectionist.library.db import Database
from projectionist.watch_tracker.models import WatchEventInput
from projectionist.watch_tracker.store import ingest_watch_events
from projectionist.watchlist.plex_sync import resolve_account_token

logger = logging.getLogger(__name__)


def set_library_item_watched(
    db: Database,
    rating_key: str,
    *,
    watched: bool,
) -> Dict[str, Any]:
    """Update local ``view_count`` / ``last_viewed_at`` for a library item."""
    key = str(rating_key or "").strip()
    if not key:
        raise ValueError("rating_key is required")
    row = db.library_item_by_rating_key(key)
    if row is None:
        raise ValueError("Library item not found")

    # Match the library DB conventions: last_viewed_at is INTEGER epoch seconds
    # (like added_at), updated_at is a REAL epoch timestamp (like _library_item_params).
    now = time.time()
    last_viewed_at = int(now)
    with db.connect() as conn:
        if watched:
            conn.execute(
                """
                UPDATE library_items
                SET view_count = CASE
                        WHEN COALESCE(view_count, 0) < 1 THEN 1
                        ELSE view_count
                    END,
                    last_viewed_at = ?,
                    updated_at = ?
                WHERE rating_key = ?
                """,
                (last_viewed_at, now, key),
            )
        else:
            conn.execute(
                """
                UPDATE library_items
                SET view_count = 0,
                    last_viewed_at = NULL,
                    updated_at = ?
                WHERE rating_key = ?
                """,
                (now, key),
            )

    updated = db.library_item_by_rating_key(key)
    if updated is None:
        raise ValueError("Library item not found")
    return {
        "rating_key": key,
        "media_type": str(updated["media_type"] or ""),
        "title": str(updated["title"] or ""),
        "watched": bool(watched),
        "view_count": int(updated["view_count"] or 0),
        "last_viewed_at": (
            int(updated["last_viewed_at"])
            if updated["last_viewed_at"] is not None
            else None
        ),
    }


def resolve_plex_watch_token(
    db: Database,
    settings: Settings,
    *,
    user_id: Optional[str],
) -> Dict[str, Any]:
    """Prefer Sign-in-with-Plex account token; else server ``plex_token``.

    Server-token writes apply to the Plex admin/account that owns the server
    token (household-wide), not a specific household member.
    """
    resolved = resolve_account_token(db, settings, user_id=user_id)
    token = str(resolved.get("token") or "").strip()
    source = resolved.get("source")
    if not token:
        fallback = str(settings.plex_token or "").strip()
        if fallback:
            token = fallback
            source = "server_plex_token"
    return {
        "token": token or None,
        "source": source,
        "has_account_token": source == "plex_token_enc",
        "user_id": resolved.get("user_id"),
    }


def record_manual_watch_observation(
    db: Database,
    rating_key: str,
    *,
    watched: bool,
    user_id: Optional[str],
    token_source: Optional[str],
    server_machine_id: str,
    occurred_at_ms: Optional[int] = None,
) -> bool:
    """Append a mapped manual scrobble correction without retaining credentials."""
    key = str(rating_key or "").strip()
    actor_id = str(user_id or "").strip()
    if not key or not actor_id:
        return False
    user = db.get_user(actor_id)
    if user is None:
        return False
    source_user_key = str(user["plex_user_id"] or "").strip()
    if not source_user_key:
        # Local/OIDC identities must not be guessed into a Plex account.
        return False
    item = db.library_item_by_rating_key(key)
    if item is None:
        return False
    media_type = str(item["media_type"] or "").strip().lower()
    if media_type not in {"movie", "episode"}:
        return False

    stamp = int(occurred_at_ms if occurred_at_ms is not None else time.time() * 1000)
    kind = "manual_scrobble" if watched else "manual_unscrobble"
    source = (
        "plex_manual_account"
        if token_source == "plex_token_enc"
        else "plex_manual_server"
    )
    event = WatchEventInput(
        source=source,
        source_event_id=f"{kind}:{source_user_key}:{key}:{stamp}",
        source_event_kind=kind,
        server_machine_id=str(server_machine_id or "").strip() or "unknown",
        source_user_key=source_user_key,
        rating_key=key,
        media_type=media_type,  # type: ignore[arg-type]
        occurred_at_ms=stamp,
        terminal=True,
        manual=True,
    )
    return ingest_watch_events(db, [event]).inserted == 1


def sync_watched_to_plex(
    db: Database,
    settings: Settings,
    rating_key: str,
    *,
    watched: bool,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Push watched state to Plex. Never raises — returns sync status flags."""
    key = str(rating_key or "").strip()
    if not key:
        return {"plex_synced": False, "plex_reason": "missing_rating_key"}

    if not settings.plex_url:
        return {"plex_synced": False, "plex_reason": "plex_not_configured"}

    resolved = resolve_plex_watch_token(db, settings, user_id=user_id)
    token = resolved.get("token")
    if not token:
        return {"plex_synced": False, "plex_reason": "plex_not_configured"}

    try:
        client = PlexClient(
            settings.plex_url,
            str(token),
            movie_section=settings.plex_movie_section or None,
            tv_section=settings.plex_tv_section or None,
            timeout=10,
        )
        if watched:
            client.scrobble(key)
        else:
            client.unscrobble(key)
        machine_id = cached_machine_identifier(
            settings.plex_url,
            str(token),
            timeout=5,
        )
        observation_recorded = record_manual_watch_observation(
            db,
            key,
            watched=watched,
            user_id=(
                str(resolved.get("user_id"))
                if resolved.get("user_id") is not None
                else user_id
            ),
            token_source=(
                str(resolved.get("source"))
                if resolved.get("source") is not None
                else None
            ),
            server_machine_id=machine_id or "unknown",
        )
    except Exception:
        logger.exception(
            "Failed to sync Plex watched state rating_key=%s watched=%s",
            key,
            watched,
        )
        return {
            "plex_synced": False,
            "plex_reason": "plex_error",
            "plex_token_source": resolved.get("source"),
        }

    return {
        "plex_synced": True,
        "plex_reason": None,
        "plex_token_source": resolved.get("source"),
        "watch_observation_recorded": observation_recorded,
    }
