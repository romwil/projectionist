"""Year-scoped Plex (+ optional Tautulli) history backfill for one member."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.watch_tracker.identity import source_user_keys_for_user, sync_plex_watch_identities
from projectionist.watch_tracker.models import WatchEventInput
from projectionist.watch_tracker.plex_history import normalize_plex_history
from projectionist.watch_tracker.rollups import year_bounds_ms
from projectionist.watch_tracker.store import ingest_watch_events
from projectionist.watch_tracker.tautulli_history import fetch_tautulli_history_events, tautulli_configured

logger = logging.getLogger(__name__)

PAGE_SIZE = 250
# Regular ingest is 40 pages (10k). A year of one member's plays can exceed that.
YEAR_MAX_PAGES = 200


def _plex_client(settings: Settings):
    base = str(settings.plex_url or "").strip()
    token = str(settings.plex_token or "").strip()
    if not base or not token:
        return None
    from projectionist.connectors.plex import PlexClient

    return PlexClient(
        base_url=base,
        token=token,
        movie_section=settings.plex_movie_section or None,
        tv_section=settings.plex_tv_section or None,
    )


def _refresh_identities(db: Database, settings: Settings, server_machine_id: Optional[str]) -> None:
    try:
        sync_plex_watch_identities(
            db,
            plex_url=str(settings.plex_url or ""),
            plex_token=str(settings.plex_token or ""),
            server_machine_id=server_machine_id,
            repair=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("YIR identity alias refresh failed (continuing year backfill)")


def _fetch_plex_year_events(
    client: Any,
    *,
    machine_id: str,
    account_ids: Sequence[str],
    since_ms: int,
    until_ms: int,
    should_stop: Optional[Callable[[], bool]],
) -> tuple[List[WatchEventInput], Dict[str, Any]]:
    allowed = {str(key).strip() for key in account_ids if str(key).strip()}
    events: List[WatchEventInput] = []
    fetched = 0
    skipped = 0
    missing_identity = 0
    for account_id in sorted(allowed):
        start = 0
        for _ in range(YEAR_MAX_PAGES):
            if should_stop and should_stop():
                return events, {
                    "status": "interrupted",
                    "fetched": fetched,
                    "normalized": len(events),
                }
            page = client.history_page(
                start=start,
                size=PAGE_SIZE,
                since_ms=since_ms,
                until_ms=until_ms,
                account_id=account_id,
            )
            fetched += int(page.size or 0)
            skipped += int(page.skipped or 0)
            missing_identity += int(page.missing_identity or 0)
            if page.size <= 0:
                break
            for item in page.items:
                if str(item.account_id) not in allowed:
                    continue
                if int(item.viewed_at_ms) < since_ms or int(item.viewed_at_ms) >= until_ms:
                    continue
                events.append(normalize_plex_history(item, server_machine_id=machine_id))
            start += page.size
            if page.size < PAGE_SIZE:
                break
            if page.total_size is not None and start >= int(page.total_size):
                break
    return events, {
        "status": "ok",
        "fetched": fetched,
        "normalized": len(events),
        "skipped": skipped,
        "missing_identity": missing_identity,
    }


def backfill_member_year_history(
    db: Database,
    settings: Settings,
    *,
    user_id: str,
    year: int,
    should_stop: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """Pull this member's Plex plays for the calendar year, then optional Tautulli.

    Does not advance the household ``plex_history`` ingest cursor. Unmapped
    accounts stay empty (fail closed) — never household ``viewCount``.
    """
    uid = str(user_id or "").strip()
    if not uid:
        return {"status": "skipped", "reason": "missing_user"}
    if should_stop and should_stop():
        return {"status": "interrupted"}

    client = _plex_client(settings)
    machine_id = ""
    if client is not None:
        try:
            machine_id = str(client.machine_identifier() or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("YIR Plex identity failed: %s", type(exc).__name__)
            client = None

    _refresh_identities(db, settings, machine_id or None)
    account_ids = source_user_keys_for_user(db, uid)
    if not account_ids:
        return {
            "status": "skipped",
            "reason": "unmapped",
            "user_id": uid,
            "year": int(year),
        }

    since_ms, until_bound = year_bounds_ms(int(year))
    # Include the first second of the year (`viewedAt>` is exclusive).
    since_ms = max(0, since_ms - 1000)
    now_ms = int(time.time() * 1000)
    until_ms = min(until_bound, now_ms) if now_ms > 0 else until_bound

    plex_events: List[WatchEventInput] = []
    plex_meta: Dict[str, Any] = {"status": "skipped", "reason": "plex_not_configured"}
    if client is not None and machine_id:
        try:
            plex_events, plex_meta = _fetch_plex_year_events(
                client,
                machine_id=machine_id,
                account_ids=account_ids,
                since_ms=since_ms,
                until_ms=until_ms,
                should_stop=should_stop,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("YIR Plex year history failed")
            plex_meta = {
                "status": "degraded",
                "reason": "history_page_failed",
                "error": type(exc).__name__,
            }

    tautulli_events: List[WatchEventInput] = []
    tautulli_meta: Dict[str, Any] = {"status": "skipped", "reason": "tautulli_not_configured"}
    if tautulli_configured(settings):
        tautulli_events, tautulli_meta = fetch_tautulli_history_events(
            settings,
            server_machine_id=machine_id or "tautulli",
            account_ids=account_ids,
            since_ms=since_ms,
            until_ms=until_ms,
            should_stop=should_stop,
        )

    events = [*plex_events, *tautulli_events]
    ingest: Dict[str, Any] = {"inserted": 0, "deduped": 0, "mapped": 0, "unmapped": 0}
    if events:
        result = ingest_watch_events(db, events)
        ingest = result.as_dict()
        ingest["inserted"] = result.inserted
        ingest["deduped"] = result.deduped
        ingest["mapped"] = result.mapped
        ingest["unmapped"] = result.unmapped

    status = "ok"
    if plex_meta.get("status") == "interrupted" or tautulli_meta.get("status") == "interrupted":
        status = "interrupted"
    elif plex_meta.get("status") == "degraded" and tautulli_meta.get("status") in {
        "degraded",
        "skipped",
    }:
        status = "degraded"
    elif not events and plex_meta.get("status") == "skipped" and tautulli_meta.get("status") == "skipped":
        status = "skipped"

    return {
        "status": status,
        "user_id": uid,
        "year": int(year),
        "account_ids": list(account_ids),
        "plex": plex_meta,
        "tautulli": tautulli_meta,
        "ingest": ingest,
    }
