"""Background keepalive so Tunarr HLS sessions do not go cold between Plex tunes.

When idle, Tunarr SIGKILLs transcoder/concat processes. The next Plex HDHR tune
then races ffmpeg writing ``playlist.m3u8`` and fails with "Stream not ready yet"
→ Plex "This live TV session has ended."

Important: do **not** keep every station hot with full MPEG-TS pulls. Warming all
six channels every few minutes drove Tunarr to 2000%+ CPU, SIGKILL storms, and
mid-watch drops to the offline Tunarr icon. Background ticks now:

- skip channels that already have an active session (never remount under viewers)
- warm at most one cold channel per tick
- playlist-only keepalive (no ``.ts`` pull) unless an admin prepare asks otherwise
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from projectionist.config_store import load_merged_settings
from projectionist.circuit_breaker import (
    CircuitOpenError,
    circuit_backoff_seconds,
    is_host_circuit_open,
)

logger = logging.getLogger(__name__)

# First tick after HTTP is up; then periodically while Live Channels is on.
WARM_INITIAL_DELAY_SECONDS = 60
WARM_POLL_SECONDS = 300
# Cap concurrent background ffmpeg pipelines.
WARM_MAX_CHANNELS_PER_TICK = 1

_scheduler: Optional["StreamWarmScheduler"] = None
_lock = threading.Lock()


class StreamWarmScheduler:
    """Daemon thread: gently keep one cold Tunarr channel ready for Plex."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_result: Dict[str, Any] = {}
        self._last_run_at: float = 0.0
        self._warm_cursor: int = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="live-channels-stream-warm"
        )
        self._thread.start()
        logger.info("Live Channels stream-warm scheduler started")

    def stop(self) -> None:
        self._stop.set()

    def last_status(self) -> Dict[str, Any]:
        return {
            "last_run_at": self._last_run_at or None,
            "last_result": dict(self._last_result) if self._last_result else {},
        }

    def _loop(self) -> None:
        self._stop.wait(timeout=WARM_INITIAL_DELAY_SECONDS)
        while not self._stop.is_set():
            delay = float(WARM_POLL_SECONDS)
            try:
                delay = float(self._tick())
            except Exception as error:  # noqa: BLE001
                logger.exception("Live Channels stream-warm tick failed: %s", error)
            self._stop.wait(timeout=max(float(WARM_POLL_SECONDS), delay))

    def _tick(self) -> float:
        settings = load_merged_settings(self.data_dir)
        features = getattr(settings, "features", None)
        if not bool(getattr(features, "live_channels_enabled", False)):
            return float(WARM_POLL_SECONDS)
        tunarr = getattr(settings, "tunarr", None)
        url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
        if not url:
            return float(WARM_POLL_SECONDS)
        if is_host_circuit_open(url):
            delay = circuit_backoff_seconds(url, floor=WARM_POLL_SECONDS)
            self._last_run_at = time.time()
            self._last_result = {
                "ok": False,
                "skipped": True,
                "reason": "circuit_open",
                "circuit_remaining_seconds": delay,
                "message": "Tunarr circuit open; skipping stream-warm tick.",
            }
            logger.warning(
                "Live Channels stream-warm skipped: circuit open (%ss remaining)",
                delay,
            )
            return float(delay)
        from projectionist.connectors.tunarr import TunarrClient
        from projectionist.live_channels.publish import (
            prepare_channels_for_playback,
            tunarr_client_from_settings,
        )

        try:
            client = tunarr_client_from_settings(settings)
        except Exception:
            client = TunarrClient(url, timeout=20)

        # Rotate which cold channel we touch so every station gets a light warm
        # over time without starting six ffmpeg pipelines at once.
        channel_ids: list[str] = []
        try:
            listed = [
                str(ch.get("id") or ch.get("uuid") or "").strip()
                for ch in client.list_channels()
                if isinstance(ch, dict)
            ]
            listed = [cid for cid in listed if cid]
            if listed:
                start = self._warm_cursor % len(listed)
                channel_ids = listed[start:] + listed[:start]
                self._warm_cursor = (start + WARM_MAX_CHANNELS_PER_TICK) % len(listed)
        except CircuitOpenError:
            delay = circuit_backoff_seconds(url, floor=WARM_POLL_SECONDS)
            self._last_run_at = time.time()
            self._last_result = {
                "ok": False,
                "skipped": True,
                "reason": "circuit_open",
                "circuit_remaining_seconds": delay,
                "message": "Tunarr circuit open; skipping stream-warm tick.",
            }
            logger.warning(
                "Live Channels stream-warm skipped: circuit open (%ss remaining)",
                delay,
            )
            return float(delay)
        except Exception as error:  # noqa: BLE001
            # Do not fall through to prepare_channels_for_playback — an empty
            # channel_ids list becomes None (warm all) and hammers Tunarr again.
            self._last_run_at = time.time()
            self._last_result = {
                "ok": False,
                "skipped": True,
                "reason": "tunarr_unreachable",
                "message": str(error)[:200],
            }
            logger.warning("Live Channels stream-warm skipped: Tunarr unreachable: %s", error)
            return float(
                circuit_backoff_seconds(url, floor=WARM_POLL_SECONDS)
                if is_host_circuit_open(url)
                else WARM_POLL_SECONDS
            )

        result = prepare_channels_for_playback(
            client,
            settings=settings,
            channel_ids=channel_ids or None,
            # Never start-over from background warm — that drifted schedules into
            # flex/Continuity after viewers left a mid-episode station.
            align_playhead=False,
            warm_streams=True,
            skip_active_sessions=True,
            max_warm_channels=WARM_MAX_CHANNELS_PER_TICK,
            pull_ts=False,
        )
        self._last_run_at = time.time()
        self._last_result = {
            "ok": bool(result.get("ok")),
            "count_channels": result.get("count_channels"),
            "count_aligned": result.get("count_aligned"),
            "count_warmed_ok": result.get("count_warmed_ok"),
            "count_warmed_skipped": result.get("count_warmed_skipped"),
            "message": result.get("message") or "",
        }
        logger.info(
            "Live Channels stream-warm: channels=%s aligned=%s warmed=%s skipped=%s",
            result.get("count_channels"),
            result.get("count_aligned"),
            result.get("count_warmed_ok"),
            result.get("count_warmed_skipped"),
        )
        return float(WARM_POLL_SECONDS)


def get_stream_warm_scheduler() -> StreamWarmScheduler:
    global _scheduler
    with _lock:
        if _scheduler is None:
            data_dir = Path(os.environ.get("DATA_DIR", "/config"))
            _scheduler = StreamWarmScheduler(data_dir)
        return _scheduler


def reset_stream_warm_scheduler_for_tests() -> None:
    """Clear the singleton (unit tests only)."""
    global _scheduler
    with _lock:
        if _scheduler is not None:
            _scheduler.stop()
        _scheduler = None
