"""Adaptive, privacy-minimized Plex active-session observation polling."""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from projectionist.config_store import Settings
from projectionist.connectors.plex import PlexActiveSession, PlexClient
from projectionist.library.db import Database
from projectionist.watch_tracker.models import WatchEventInput
from projectionist.watch_tracker.store import ingest_watch_events

logger = logging.getLogger(__name__)

LIVE_POLL_SECONDS = 60
IDLE_POLL_SECONDS = 5 * 60


def normalize_active_session(
    session: PlexActiveSession,
    *,
    server_machine_id: str,
    occurred_at_ms: Optional[int] = None,
) -> WatchEventInput:
    """Normalize one active session without retaining device or network metadata."""
    stamp = int(occurred_at_ms if occurred_at_ms is not None else time.time() * 1000)
    client_key = None
    if session.client_identifier:
        client_key = hashlib.sha256(
            f"{server_machine_id}:{session.client_identifier}".encode("utf-8")
        ).hexdigest()
    source_event_id = ":".join(
        (
            "active",
            session.source_user_key,
            session.session_key or "no-session",
            session.rating_key,
            str(stamp),
        )
    )
    return WatchEventInput(
        source="plex_sessions",
        source_event_id=source_event_id,
        source_event_kind="session_progress",
        server_machine_id=server_machine_id,
        source_user_key=session.source_user_key,
        rating_key=session.rating_key,
        parent_rating_key=session.parent_rating_key,
        media_type=session.media_type,  # type: ignore[arg-type]
        occurred_at_ms=stamp,
        client_key=client_key,
        session_key=session.session_key,
        progress_ms=session.progress_ms,
        duration_ms=session.duration_ms,
        terminal=False,
        manual=False,
    )


def poll_active_sessions(
    db: Database,
    client: PlexClient,
    *,
    server_machine_id: str,
    occurred_at_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Fetch and persist one active-session snapshot."""
    sessions = client.active_sessions()
    events = [
        normalize_active_session(
            session,
            server_machine_id=server_machine_id,
            occurred_at_ms=occurred_at_ms,
        )
        for session in sessions
    ]
    result = ingest_watch_events(db, events)
    return {
        "status": "ok",
        "source": "plex_sessions",
        "active_sessions": len(sessions),
        **result.as_dict(),
    }


def poll_interval_seconds(result: Dict[str, Any]) -> int:
    """Use a one-minute cadence only while Plex reports active sessions."""
    if result.get("status") == "ok" and int(result.get("active_sessions") or 0) > 0:
        return LIVE_POLL_SECONDS
    return IDLE_POLL_SECONDS


class LiveSessionPoller:
    """Small stoppable loop for polling faster than the idle task scheduler."""

    def __init__(
        self,
        *,
        db_factory: Callable[[], Database],
        settings_factory: Callable[[], Settings],
        poll_fn: Optional[Callable[[Database, Settings], Dict[str, Any]]] = None,
        initial_delay_seconds: float = 5.0,
    ) -> None:
        self._db_factory = db_factory
        self._settings_factory = settings_factory
        self._poll_fn = poll_fn or self.poll_once
        self._initial_delay_seconds = max(0.0, float(initial_delay_seconds))
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="watch-live-session-poller",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5)

    def _loop(self) -> None:
        if self._stop.wait(self._initial_delay_seconds):
            return
        while not self._stop.is_set():
            try:
                result = self._poll_fn(
                    self._db_factory(),
                    self._settings_factory(),
                )
            except Exception:  # noqa: BLE001
                logger.exception("Unexpected live-session poll failure")
                result = {
                    "status": "degraded",
                    "source": "plex_sessions",
                    "active_sessions": 0,
                    "reason": "internal_error",
                }
            if self._stop.wait(poll_interval_seconds(result)):
                return

    @staticmethod
    def poll_once(db: Database, settings: Settings) -> Dict[str, Any]:
        """Poll once, returning sanitized degraded/skipped outcomes."""
        if not str(settings.plex_url or "").strip() or not str(
            settings.plex_token or ""
        ).strip():
            return {
                "status": "skipped",
                "source": "plex_sessions",
                "active_sessions": 0,
                "reason": "plex_not_configured",
            }
        try:
            client = PlexClient(
                settings.plex_url,
                settings.plex_token,
                movie_section=settings.plex_movie_section or None,
                tv_section=settings.plex_tv_section or None,
                timeout=10,
            )
            server_machine_id = client.machine_identifier()
            return poll_active_sessions(
                db,
                client,
                server_machine_id=server_machine_id,
            )
        except Exception as error:  # noqa: BLE001
            logger.warning(
                "Plex live-session polling unavailable (%s)",
                type(error).__name__,
            )
            return {
                "status": "degraded",
                "source": "plex_sessions",
                "active_sessions": 0,
                "reason": type(error).__name__,
            }
