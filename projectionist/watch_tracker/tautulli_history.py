"""Optional Tautulli history → WatchEventInput. Never required for Year in Review."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from projectionist.config_store import Settings
from projectionist.watch_tracker.models import WatchEventInput

logger = logging.getLogger(__name__)

PAGE_SIZE = 100
MAX_PAGES = 200


def tautulli_configured(settings: Settings) -> bool:
    return bool(
        str(getattr(settings, "tautulli_url", "") or "").strip()
        and str(getattr(settings, "tautulli_api_key", "") or "").strip()
    )


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def _ms_from_unix(raw: Optional[int]) -> Optional[int]:
    if raw is None or raw <= 0:
        return None
    return int(raw) * 1000 if raw < 10_000_000_000 else int(raw)


def normalize_tautulli_history_row(
    row: Mapping[str, Any],
    *,
    server_machine_id: str,
) -> Optional[WatchEventInput]:
    """Map one Tautulli history row. Kind is the reserved ``tautulli_history``."""
    media_type = str(row.get("media_type") or "").strip().lower()
    if media_type not in {"movie", "episode"}:
        return None
    rating_key = str(row.get("rating_key") or "").strip()
    if not rating_key or rating_key == "0":
        return None
    account_id = str(row.get("user_id") or "").strip()
    if not account_id or account_id == "0":
        return None
    occurred_at_ms = _ms_from_unix(
        _optional_int(row.get("stopped")) or _optional_int(row.get("date"))
    )
    if occurred_at_ms is None:
        return None
    duration_raw = _optional_int(row.get("duration"))
    duration_ms: Optional[int] = None
    if duration_raw is not None and duration_raw > 0:
        duration_ms = duration_raw if duration_raw >= 10_000 else duration_raw * 1000
    progress_ms: Optional[int] = None
    pct_raw = row.get("percent_complete")
    try:
        pct = float(pct_raw) if pct_raw is not None and pct_raw != "" else None
    except (TypeError, ValueError):
        pct = None
    if pct is not None and duration_ms:
        progress_ms = int(duration_ms * min(100.0, max(0.0, pct)) / 100.0)
    parent = str(
        row.get("grandparent_rating_key") or row.get("parent_rating_key") or ""
    ).strip()
    if not parent or parent == "0":
        parent = None
    row_id = row.get("row_id")
    source_event_id = f"tautulli:{row_id}" if row_id is not None and str(row_id).strip() else None
    return WatchEventInput(
        source="tautulli_history",
        source_event_id=source_event_id,
        source_event_kind="tautulli_history",
        server_machine_id=server_machine_id,
        source_user_key=account_id,
        rating_key=rating_key,
        parent_rating_key=parent,
        media_type=media_type,  # type: ignore[arg-type]
        occurred_at_ms=occurred_at_ms,
        progress_ms=progress_ms,
        duration_ms=duration_ms,
        terminal=True,
        manual=False,
    )


def _client(settings: Settings):
    if not tautulli_configured(settings):
        return None
    from projectionist.connectors.tautulli import TautulliClient

    return TautulliClient(
        str(settings.tautulli_url).strip(),
        str(settings.tautulli_api_key).strip(),
    )


def fetch_tautulli_history_events(
    settings: Settings,
    *,
    server_machine_id: str,
    account_ids: Sequence[str],
    since_ms: int,
    until_ms: Optional[int] = None,
    should_stop: Optional[Callable[[], bool]] = None,
) -> tuple[List[WatchEventInput], Dict[str, Any]]:
    """Page Tautulli ``get_history`` for mapped Plex account ids. Skip if unconfigured."""
    if not tautulli_configured(settings):
        return [], {"status": "skipped", "reason": "tautulli_not_configured", "fetched": 0}
    client = _client(settings)
    if client is None:
        return [], {"status": "skipped", "reason": "tautulli_not_configured", "fetched": 0}

    allowed = {str(key).strip() for key in account_ids if str(key).strip()}
    if not allowed:
        return [], {"status": "skipped", "reason": "unmapped", "fetched": 0}

    after = datetime.fromtimestamp(max(0, int(since_ms)) / 1000, tz=timezone.utc).strftime(
        "%Y-%m-%d"
    )
    # Do not pass Tautulli's `before` as today — that can drop the current day's plays.
    # Year-end (and "now") bounds are applied client-side below.

    events: List[WatchEventInput] = []
    fetched = 0
    skipped = 0
    try:
        for account_id in sorted(allowed):
            start = 0
            for _ in range(MAX_PAGES):
                if should_stop and should_stop():
                    return events, {
                        "status": "interrupted",
                        "fetched": fetched,
                        "normalized": len(events),
                    }
                page = client.get_history(
                    start=start,
                    length=PAGE_SIZE,
                    user_id=account_id,
                    after=after,
                )
                rows = page.get("data") if isinstance(page, dict) else None
                if not isinstance(rows, list) or not rows:
                    break
                fetched += len(rows)
                for row in rows:
                    if not isinstance(row, Mapping):
                        skipped += 1
                        continue
                    event = normalize_tautulli_history_row(
                        row, server_machine_id=server_machine_id
                    )
                    if event is None:
                        skipped += 1
                        continue
                    if event.source_user_key not in allowed:
                        skipped += 1
                        continue
                    if event.occurred_at_ms < int(since_ms):
                        continue
                    if until_ms is not None and event.occurred_at_ms >= int(until_ms):
                        continue
                    events.append(event)
                if len(rows) < PAGE_SIZE:
                    break
                start += len(rows)
                filtered = page.get("recordsFiltered") if isinstance(page, dict) else None
                if filtered is not None and start >= int(filtered):
                    break
        return events, {
            "status": "ok",
            "fetched": fetched,
            "normalized": len(events),
            "skipped": skipped,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Tautulli history fetch failed")
        return events, {
            "status": "degraded",
            "reason": "tautulli_history_failed",
            "error": f"{type(exc).__name__}",
            "fetched": fetched,
            "normalized": len(events),
            "skipped": skipped,
        }
