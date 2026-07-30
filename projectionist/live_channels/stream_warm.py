"""Background keepalive so Tunarr HLS sessions do not go cold between Plex tunes.

When idle, Tunarr SIGKILLs transcoder/concat processes. The next Plex HDHR tune
then races ffmpeg writing ``playlist.m3u8`` and fails with "Stream not ready yet"
→ Plex "This live TV session has ended." Periodic warm (+ start-over when a
playhead is past EOF / deep into a cold channel) keeps MPEG-TS ready.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from projectionist.config_store import load_merged_settings

logger = logging.getLogger(__name__)

# First tick after HTTP is up; then every few minutes while Live Channels is on.
WARM_INITIAL_DELAY_SECONDS = 45
WARM_POLL_SECONDS = 180

_scheduler: Optional["StreamWarmScheduler"] = None
_lock = threading.Lock()


class StreamWarmScheduler:
    """Daemon thread: prepare Tunarr channels for Plex while the feature is on."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_result: Dict[str, Any] = {}
        self._last_run_at: float = 0.0

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
            try:
                self._tick()
            except Exception as error:  # noqa: BLE001
                logger.exception("Live Channels stream-warm tick failed: %s", error)
            self._stop.wait(timeout=WARM_POLL_SECONDS)

    def _tick(self) -> None:
        settings = load_merged_settings(self.data_dir)
        features = getattr(settings, "features", None)
        if not bool(getattr(features, "live_channels_enabled", False)):
            return
        tunarr = getattr(settings, "tunarr", None)
        url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
        if not url:
            return
        from projectionist.connectors.tunarr import TunarrClient
        from projectionist.live_channels.publish import (
            prepare_channels_for_playback,
            tunarr_client_from_settings,
        )

        try:
            client = tunarr_client_from_settings(settings)
        except Exception:
            client = TunarrClient(url, timeout=20)
        result = prepare_channels_for_playback(
            client,
            settings=settings,
            align_playhead=True,
            warm_streams=True,
        )
        self._last_run_at = time.time()
        self._last_result = {
            "ok": bool(result.get("ok")),
            "count_channels": result.get("count_channels"),
            "count_aligned": result.get("count_aligned"),
            "count_warmed_ok": result.get("count_warmed_ok"),
            "message": result.get("message") or "",
        }
        logger.info(
            "Live Channels stream-warm: channels=%s aligned=%s warmed=%s",
            result.get("count_channels"),
            result.get("count_aligned"),
            result.get("count_warmed_ok"),
        )


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
