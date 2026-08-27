"""SSE hub + Plex watcher for lobby theater (subscriber-aware, adaptive)."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Set

from projectionist.circuit_breaker import (
    circuit_backoff_seconds,
    is_host_circuit_open,
)
from projectionist.config_store import Settings, load_merged_settings
from projectionist.library.db import Database
from projectionist.theater import (
    AVAILABLE_REFRESH_SECONDS,
    SSE_PING_SECONDS,
    WATCHER_POLL_ACTIVE_SECONDS,
    WATCHER_POLL_DEGRADED_SECONDS,
    WATCHER_POLL_IDLE_SECONDS,
)
from projectionist.theater.normalize import normalize_theater_settings
from projectionist.theater.snapshot import build_board_snapshot, session_signature

logger = logging.getLogger(__name__)


@dataclass(eq=False)
class _Subscriber:
    queue: asyncio.Queue
    loop: asyncio.AbstractEventLoop

    def __hash__(self) -> int:
        return id(self)


@dataclass
class TheaterHub:
    """Process-wide theater fan-out. Shared by main + theater uvicorn apps."""

    data_dir: Path
    db_factory: Callable[[], Database]
    settings_factory: Optional[Callable[[], Settings]] = None
    _subscribers: Set[_Subscriber] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: Optional[threading.Thread] = None
    _last_signature: str = ""
    _last_mode: str = ""
    _last_settings_sig: str = ""
    _last_available_at: float = 0.0
    _last_snapshot: Optional[Dict[str, Any]] = None
    _plex_calls: int = 0
    _started: bool = False
    _degraded: bool = False
    _next_poll_seconds: float = float(WATCHER_POLL_IDLE_SECONDS)
    _prefetch_fn: Optional[Callable[[List[str], Path], None]] = None

    def settings(self) -> Settings:
        if self.settings_factory is not None:
            return self.settings_factory()
        return load_merged_settings(self.data_dir)

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    @property
    def plex_call_count(self) -> int:
        return int(self._plex_calls)

    @property
    def next_poll_seconds(self) -> float:
        return float(self._next_poll_seconds)

    @property
    def degraded(self) -> bool:
        return bool(self._degraded)

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            self._started = True
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop,
                daemon=True,
                name="theater-watcher",
            )
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=5)
        with self._lock:
            self._started = False
            self._thread = None

    def notify_settings_changed(self) -> None:
        """Force hydrate on next watcher tick (or immediately if subscribers)."""
        self._last_settings_sig = ""
        snapshot = self._safe_snapshot(fetch_sessions=self.subscriber_count > 0)
        if snapshot is not None:
            self._broadcast("hydrate", snapshot)
            self._remember(snapshot)
            self._maybe_prefetch(snapshot)

    def poll_interval_for_mode(self, mode: str, *, degraded: bool = False) -> float:
        """Expose adaptive cadence for tests and /api/health."""
        if degraded:
            settings = self.settings()
            plex_url = str(settings.plex_url or "").strip()
            if plex_url and is_host_circuit_open(plex_url):
                return float(
                    circuit_backoff_seconds(
                        plex_url, floor=WATCHER_POLL_DEGRADED_SECONDS
                    )
                )
            return float(WATCHER_POLL_DEGRADED_SECONDS)
        if mode == "now_playing":
            return float(WATCHER_POLL_ACTIVE_SECONDS)
        return float(WATCHER_POLL_IDLE_SECONDS)

    def _settings_sig(self, settings: Settings) -> str:
        theater = normalize_theater_settings(getattr(settings, "theater", None))
        return json.dumps(
            {
                "enabled": theater.enabled,
                "orientation": theater.orientation,
                "audience": theater.audience,
                "idle_mode": theater.idle_mode,
                "multi_mode": theater.multi_mode,
                "header_mode": theater.header_mode,
                "static_label": theater.static_label,
                "rotate_seconds": theater.rotate_seconds,
            },
            sort_keys=True,
        )

    def _plex_circuit_open(self, settings: Settings) -> bool:
        plex_url = str(settings.plex_url or "").strip()
        return bool(plex_url and is_host_circuit_open(plex_url))

    def _safe_snapshot(self, *, fetch_sessions: bool) -> Optional[Dict[str, Any]]:
        try:
            settings = self.settings()
            theater = normalize_theater_settings(getattr(settings, "theater", None))
            if not theater.enabled:
                self._degraded = False
                return {
                    "enabled": False,
                    "header_mode": theater.header_mode,
                    "header_label": theater.static_label or "LOBBY",
                    "orientation": theater.orientation,
                    "multi_mode": theater.multi_mode,
                    "idle_mode": theater.idle_mode,
                    "rotate_seconds": theater.rotate_seconds,
                    "mode": "empty",
                    "watching": False,
                    "sessions": [],
                    "available": [],
                }

            if fetch_sessions and self._plex_circuit_open(settings):
                self._degraded = True
                if self._last_snapshot is not None:
                    return dict(self._last_snapshot)
                # Idle board from library only — no Plex sessions call.
                return build_board_snapshot(
                    self.db_factory(),
                    settings,
                    sessions=[],
                    fetch_sessions=False,
                )

            if fetch_sessions:
                self._plex_calls += 1
            snapshot = build_board_snapshot(
                self.db_factory(),
                settings,
                fetch_sessions=fetch_sessions,
            )
            # build_board_snapshot swallows Plex errors into empty sessions;
            # treat circuit-open after the attempt as degraded for backoff.
            if fetch_sessions and self._plex_circuit_open(settings):
                self._degraded = True
            else:
                self._degraded = False
            return snapshot
        except Exception:  # noqa: BLE001
            logger.exception("theater snapshot failed")
            self._degraded = True
            if self._last_snapshot is not None:
                return dict(self._last_snapshot)
            return None

    def _remember(self, snapshot: Dict[str, Any]) -> None:
        self._last_mode = str(snapshot.get("mode") or "")
        self._last_signature = session_signature(snapshot.get("sessions") or [])
        self._last_snapshot = dict(snapshot)
        if snapshot.get("mode") == "now_available":
            self._last_available_at = time.monotonic()
        self._next_poll_seconds = self.poll_interval_for_mode(
            self._last_mode, degraded=self._degraded
        )

    def _visible_rating_keys(self, snapshot: Dict[str, Any]) -> List[str]:
        keys: List[str] = []
        seen: Set[str] = set()
        for item in list(snapshot.get("sessions") or []) + list(
            snapshot.get("available") or []
        ):
            url = str((item or {}).get("poster_url") or "")
            # /api/theater/poster?rk=KEY
            if "rk=" not in url:
                continue
            rk = url.split("rk=", 1)[1].split("&", 1)[0].strip()
            if not rk or rk in seen:
                continue
            seen.add(rk)
            keys.append(rk)
            if len(keys) >= 16:
                break
        return keys

    def _maybe_prefetch(self, snapshot: Dict[str, Any]) -> None:
        keys = self._visible_rating_keys(snapshot)
        if not keys:
            return
        prefetch = self._prefetch_fn
        if prefetch is None:
            try:
                from projectionist.theater.poster_cache import schedule_poster_prefetch

                prefetch = schedule_poster_prefetch
            except Exception:  # noqa: BLE001
                return
        try:
            prefetch(keys, self.data_dir, self.db_factory, self.settings)
        except Exception:  # noqa: BLE001
            logger.debug("theater poster prefetch schedule failed", exc_info=True)

    def _broadcast(self, event: str, data: Dict[str, Any]) -> None:
        payload = json.dumps(data, separators=(",", ":"))
        dead: List[_Subscriber] = []
        with self._lock:
            subscribers = list(self._subscribers)
        for sub in subscribers:
            try:
                asyncio.run_coroutine_threadsafe(
                    sub.queue.put((event, payload)),
                    sub.loop,
                )
            except Exception:  # noqa: BLE001
                dead.append(sub)
        if dead:
            with self._lock:
                for sub in dead:
                    self._subscribers.discard(sub)

    def _loop(self) -> None:
        while not self._stop.wait(max(1.0, float(self._next_poll_seconds))):
            try:
                self._tick()
            except Exception:  # noqa: BLE001
                logger.exception("theater watcher tick failed")
                self._degraded = True
                self._next_poll_seconds = float(WATCHER_POLL_DEGRADED_SECONDS)

    def _tick(self) -> None:
        settings = self.settings()
        theater = normalize_theater_settings(getattr(settings, "theater", None))
        settings_sig = self._settings_sig(settings)
        settings_changed = settings_sig != self._last_settings_sig
        self._last_settings_sig = settings_sig

        if not theater.enabled:
            self._degraded = False
            self._next_poll_seconds = float(WATCHER_POLL_IDLE_SECONDS)
            if settings_changed:
                snapshot = self._safe_snapshot(fetch_sessions=False)
                if snapshot is not None:
                    self._broadcast("hydrate", snapshot)
                    self._remember(snapshot)
            return

        if self.subscriber_count <= 0:
            # Zero subscribers ⇒ no Plex stampede.
            self._next_poll_seconds = float(WATCHER_POLL_IDLE_SECONDS)
            return

        need_available_refresh = (
            self._last_mode == "now_available"
            and (time.monotonic() - self._last_available_at) >= AVAILABLE_REFRESH_SECONDS
        )
        snapshot = self._safe_snapshot(fetch_sessions=True)
        if snapshot is None:
            self._next_poll_seconds = self.poll_interval_for_mode(
                self._last_mode or "empty", degraded=True
            )
            return

        if settings_changed or need_available_refresh:
            self._broadcast("hydrate", snapshot)
            self._remember(snapshot)
            self._maybe_prefetch(snapshot)
            return

        mode = str(snapshot.get("mode") or "")
        sig = session_signature(snapshot.get("sessions") or [])
        if mode != self._last_mode:
            if mode == "now_playing":
                self._broadcast("now_playing", snapshot)
            else:
                self._broadcast("idle", snapshot)
            self._remember(snapshot)
            self._maybe_prefetch(snapshot)
            return

        if mode == "now_playing" and sig != self._last_signature:
            # Session set / pause / seek change — push progress correction.
            prev_ids = {p.split(":")[0] for p in self._last_signature.split("|") if p}
            next_ids = {p.split(":")[0] for p in sig.split("|") if p}
            if prev_ids != next_ids:
                self._broadcast("now_playing", snapshot)
                self._maybe_prefetch(snapshot)
            else:
                self._broadcast("progress", snapshot)
            self._remember(snapshot)
            return

        self._remember(snapshot)

    async def subscribe(self) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=32)
        sub = _Subscriber(queue=queue, loop=loop)
        with self._lock:
            self._subscribers.add(sub)

        try:
            snapshot = self._safe_snapshot(fetch_sessions=True)
            if snapshot is None:
                snapshot = {
                    "enabled": False,
                    "mode": "empty",
                    "watching": False,
                    "sessions": [],
                    "available": [],
                    "header_label": "LOBBY",
                    "header_mode": "dynamic",
                    "orientation": "landscape",
                    "multi_mode": "rotator",
                    "idle_mode": "empty",
                    "rotate_seconds": 12,
                }
            yield _sse_event("hydrate", snapshot)
            self._remember(snapshot)
            self._maybe_prefetch(snapshot)

            while True:
                try:
                    event, payload = await asyncio.wait_for(
                        queue.get(),
                        timeout=float(SSE_PING_SECONDS),
                    )
                    yield f"event: {event}\ndata: {payload}\n\n"
                except asyncio.TimeoutError:
                    # Comment keeps quiet proxies/TCP alive; named event feeds the
                    # kiosk 45s silence watchdog (EventSource hides comments).
                    yield ": ping\n\n"
                    yield "event: ping\ndata: {}\n\n"
        finally:
            with self._lock:
                self._subscribers.discard(sub)


def _sse_event(event: str, data: Dict[str, Any]) -> str:
    payload = json.dumps(data, separators=(",", ":"))
    return f"event: {event}\ndata: {payload}\n\n"


_HUB: Optional[TheaterHub] = None
_HUB_LOCK = threading.Lock()


def get_theater_hub(
    *,
    data_dir: Optional[Path] = None,
    db_factory: Optional[Callable[[], Database]] = None,
    settings_factory: Optional[Callable[[], Settings]] = None,
) -> TheaterHub:
    global _HUB
    with _HUB_LOCK:
        if _HUB is not None:
            return _HUB
        if data_dir is None or db_factory is None:
            raise RuntimeError("Theater hub not initialized")
        _HUB = TheaterHub(
            data_dir=data_dir,
            db_factory=db_factory,
            settings_factory=settings_factory,
        )
        return _HUB


def init_theater_hub(
    *,
    data_dir: Path,
    db_factory: Callable[[], Database],
    settings_factory: Optional[Callable[[], Settings]] = None,
) -> TheaterHub:
    global _HUB
    with _HUB_LOCK:
        _HUB = TheaterHub(
            data_dir=data_dir,
            db_factory=db_factory,
            settings_factory=settings_factory,
        )
        return _HUB


def reset_theater_hub_for_tests() -> None:
    global _HUB
    with _HUB_LOCK:
        if _HUB is not None:
            try:
                _HUB.stop()
            except Exception:  # noqa: BLE001
                pass
        _HUB = None
