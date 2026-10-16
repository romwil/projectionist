"""Background tick for Live. Playback is library Play, so this does not warm a stream."""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from projectionist.config_store import load_merged_settings

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
        self._last_run_at = time.time()
        self._last_result = {
            "ok": True,
            "skipped": True,
            "reason": "native_playback",
            "message": "Live playback uses library Play.",
        }
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
