"""Normalize Plex webhook payloads into WatchEventInput rows."""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional

from projectionist.watch_tracker.models import WatchEventInput

_EVENT_KIND = {
    "media.pause": "session_pause",
    "media.stop": "session_stop",
    "media.scrobble": "plex_scrobble",
}


def webhook_to_watch_event(
    payload: Mapping[str, Any],
    *,
    server_machine_id: str,
) -> Optional[WatchEventInput]:
    """Return a normalized event for supported webhook playback signals."""
    event = str(payload.get("event") or "").strip().lower()
    kind = _EVENT_KIND.get(event)
    if not kind:
        return None
    metadata = payload.get("Metadata")
    if not isinstance(metadata, Mapping):
        return None
    plex_type = str(metadata.get("type") or "").strip().lower()
    if plex_type not in {"movie", "episode"}:
        return None
    rating_key = str(metadata.get("ratingKey") or "").strip()
    if not rating_key:
        return None
    account = payload.get("Account") if isinstance(payload.get("Account"), Mapping) else {}
    account_id = str(account.get("id") or "").strip()
    if not account_id:
        return None
    progress_ms = _optional_int(metadata.get("viewOffset"))
    duration_ms = _optional_int(metadata.get("duration"))
    parent = (
        str(metadata.get("grandparentRatingKey") or metadata.get("parentRatingKey") or "").strip()
        or None
    )
    client = payload.get("Player") if isinstance(payload.get("Player"), Mapping) else {}
    client_key = str(client.get("uuid") or client.get("machineIdentifier") or "").strip() or None
    session_key = str(payload.get("Session", {}).get("id") or "").strip() if isinstance(
        payload.get("Session"), Mapping
    ) else None
    occurred_at_ms = int(time.time() * 1000)
    source_event_id = f"webhook:{event}:{account_id}:{rating_key}:{occurred_at_ms // 1000}"
    terminal = event in {"media.stop", "media.scrobble"}
    return WatchEventInput(
        source="plex_webhook",
        source_event_id=source_event_id,
        source_event_kind=kind,
        server_machine_id=server_machine_id or "unknown",
        source_user_key=account_id,
        rating_key=rating_key,
        parent_rating_key=parent,
        media_type=plex_type,  # type: ignore[arg-type]
        occurred_at_ms=occurred_at_ms,
        client_key=client_key,
        session_key=session_key or None,
        progress_ms=progress_ms,
        duration_ms=duration_ms,
        terminal=terminal,
        manual=False,
    )


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
