"""Dedicated SQLite write serializer.

One background thread owns mutating work submitted via ``Database.run_write``.
Readers keep using short-lived WAL connections on caller threads so concurrent
reads do not regress. Callers keep the existing sync ``Database`` API; ambient
writers (telemetry, scheduler batch upserts, webhook enqueue, chat persist)
route through ``run_write`` internally.

Backpressure: a bounded queue blocks submitters when full. Shutdown drains the
queue, then stops the worker. Errors raised inside submitted callables are
re-raised on the waiting caller thread.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional, TypeVar

logger = logging.getLogger("projectionist.library.db")

T = TypeVar("T")

# Homelab default: absorb a burst of telemetry/webhook/scheduler writes without
# unbounded memory growth. Blocked put() is the backpressure signal.
DEFAULT_WRITE_QUEUE_MAXSIZE = 128


@dataclass
class _WriteJob:
    fn: Callable[[], object]
    label: str
    enqueued_at: float
    event: threading.Event
    result: list  # [value] or empty
    error: list  # [BaseException] or empty


class WriteSerializer:
    """Single-thread owner for SQLite mutating callables."""

    _STOP = object()

    def __init__(self, *, maxsize: int = DEFAULT_WRITE_QUEUE_MAXSIZE) -> None:
        self._queue: queue.Queue = queue.Queue(maxsize=max(1, int(maxsize)))
        self._thread = threading.Thread(
            target=self._loop,
            name="curatorx-db-writer",
            daemon=True,
        )
        self._thread_ident: Optional[int] = None
        self._closed = False
        self._close_lock = threading.Lock()
        self._jobs_done = 0
        self._total_wait_s = 0.0
        self._last_wait_s = 0.0
        self._max_wait_s = 0.0
        self._stats_lock = threading.Lock()
        self._thread.start()

    def in_writer_thread(self) -> bool:
        return self._thread_ident is not None and threading.get_ident() == self._thread_ident

    def run(self, fn: Callable[[], T], *, label: str = "write") -> T:
        """Enqueue ``fn``, wait for completion, propagate errors to the caller."""
        if self.in_writer_thread():
            # Re-entrant: nested run_write from inside a submitted job.
            return fn()

        with self._close_lock:
            if self._closed:
                raise RuntimeError("Database write serializer is shut down")

        job = _WriteJob(
            fn=fn,
            label=label or "write",
            enqueued_at=time.monotonic(),
            event=threading.Event(),
            result=[],
            error=[],
        )
        try:
            self._queue.put(job, block=True)
        except Exception:
            raise
        job.event.wait()
        if job.error:
            raise job.error[0]
        return job.result[0]  # type: ignore[return-value]

    def stats(self) -> dict:
        with self._stats_lock:
            return {
                "queue_depth": self._queue.qsize(),
                "jobs_done": self._jobs_done,
                "last_wait_s": self._last_wait_s,
                "max_wait_s": self._max_wait_s,
                "avg_wait_s": (self._total_wait_s / self._jobs_done) if self._jobs_done else 0.0,
                "closed": self._closed,
            }

    def shutdown(self, *, timeout: float = 30.0) -> None:
        """Drain pending jobs, then stop the writer thread."""
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        self._queue.put(self._STOP)
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            logger.warning("Write serializer did not stop within %.1fs", timeout)

    def _loop(self) -> None:
        self._thread_ident = threading.get_ident()
        logger.info("SQLite write serializer started (maxsize=%s)", self._queue.maxsize)
        while True:
            item = self._queue.get()
            if item is self._STOP:
                self._queue.task_done()
                break
            assert isinstance(item, _WriteJob)
            wait_s = time.monotonic() - item.enqueued_at
            with self._stats_lock:
                self._last_wait_s = wait_s
                self._max_wait_s = max(self._max_wait_s, wait_s)
                self._total_wait_s += wait_s
                depth = self._queue.qsize()
            if wait_s >= 0.25 or depth >= 8:
                logger.info(
                    "SQLite write serializer label=%s wait=%.3fs queue_depth=%s",
                    item.label,
                    wait_s,
                    depth,
                )
            try:
                item.result.append(item.fn())
            except BaseException as exc:  # noqa: BLE001 — propagate to caller
                item.error.append(exc)
            finally:
                with self._stats_lock:
                    self._jobs_done += 1
                item.event.set()
                self._queue.task_done()
        logger.info("SQLite write serializer stopped (jobs_done=%s)", self._jobs_done)
