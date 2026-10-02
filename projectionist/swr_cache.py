"""Shared stale-while-revalidate cache for first-paint aggregates.

Explore hub (1.37.24) proved the product rule: **recompute must never sit on the
request path** once we have anything to show. This helper generalizes it for Live,
Journey, Admin status, and library dashboards:

* fresh (age < soft TTL)  — serve the cached payload.
* stale (soft ≤ age < hard, or invalidated) — serve the cached payload *now* and
  refresh in a single-flight background thread.
* durable (optional) — payloads persist in ``sync_state`` so a restart / deploy
  paints from the last good snapshot instead of hanging on a cold recompute.
* cold (nothing cached) — kick a background build, wait at most ``cold_wait``
  seconds (default 0) and otherwise return a *warming* skeleton immediately.

Payloads are treated as immutable by the cache (callers get a shallow copy of the
top-level dict, so adding ``cached`` / ``stale`` flags is safe).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

Payload = Dict[str, Any]

# Minimum gap between background retries after a failed / rejected rebuild so a
# flapping upstream (Tunarr, Plex) is not hammered by every page poll.
RETRY_BACKOFF_SECONDS = 8.0


@dataclass
class _Entry:
    payload: Payload
    built_at: float  # wall clock
    epoch: int
    soft_ttl: float


@dataclass(frozen=True)
class SwrResult:
    """What ``SwrCache.get`` returned and why."""

    payload: Payload
    state: str  # "fresh" | "stale" | "warming"
    built_at: Optional[float]

    @property
    def cached(self) -> bool:
        return self.state in {"fresh", "stale"}

    @property
    def stale(self) -> bool:
        return self.state == "stale"

    @property
    def warming(self) -> bool:
        return self.state == "warming"

    def annotated(self) -> Payload:
        """Payload copy with ``cached`` / ``stale`` / ``warming`` flags set."""
        out = dict(self.payload)
        out["cached"] = self.cached
        out["stale"] = self.stale
        out["warming"] = self.warming
        return out


class SwrCache:
    """Process-local SWR cache with optional durable ``sync_state`` backing."""

    def __init__(
        self,
        name: str,
        *,
        soft_ttl: float,
        hard_ttl: float,
        durable: bool = False,
        max_entries: int = 128,
    ) -> None:
        self.name = name
        self.soft_ttl = max(0.0, float(soft_ttl))
        self.hard_ttl = max(self.soft_ttl, float(hard_ttl))
        self.durable = bool(durable)
        self.max_entries = max(1, int(max_entries))
        self._lock = threading.Lock()
        self._entries: Dict[str, _Entry] = {}
        self._epoch = 0
        self._inflight: Dict[str, threading.Event] = {}
        self._last_failure: Dict[str, float] = {}

    # ------------------------------------------------------------------ keys
    def _disk_key(self, key: str) -> str:
        return f"swr:{self.name}:{key}"

    # ------------------------------------------------------------- inspection
    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "name": self.name,
                "entries": len(self._entries),
                "inflight": len(self._inflight),
                "soft_ttl_seconds": self.soft_ttl,
                "hard_ttl_seconds": self.hard_ttl,
                "durable": self.durable,
                "epoch": self._epoch,
            }

    def clear(self) -> None:
        """Test helper — drop memory state (does not touch disk)."""
        with self._lock:
            self._entries.clear()
            self._inflight.clear()
            self._last_failure.clear()
            self._epoch = 0

    def invalidate(self) -> None:
        """Mark every entry soft-stale. Payloads stay so the next read paints."""
        with self._lock:
            self._epoch += 1

    def wait_idle(self, timeout: float = 5.0) -> bool:
        """Test helper — wait for in-flight background builds."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            with self._lock:
                events = list(self._inflight.values())
            if not events:
                return True
            for event in events:
                event.wait(max(0.0, deadline - time.monotonic()))
        return False

    # ----------------------------------------------------------------- disk
    def _disk_load(self, db: Any, key: str) -> Optional[tuple[Payload, float]]:
        if not self.durable or db is None:
            return None
        try:
            raw = db.get_sync_state(self._disk_key(key))
            if not raw:
                return None
            parsed = json.loads(raw)
            payload = parsed.get("payload")
            built_at = float(parsed.get("built_at") or 0)
            if not isinstance(payload, dict) or built_at <= 0:
                return None
            if time.time() - built_at > self.hard_ttl:
                return None
            return payload, built_at
        except Exception:  # noqa: BLE001 — durable cache must never break a page
            logger.debug("swr disk load failed name=%s key=%s", self.name, key, exc_info=True)
            return None

    def _disk_store(self, db: Any, key: str, payload: Payload, built_at: float) -> None:
        if not self.durable or db is None:
            return
        try:
            db.set_sync_state(
                self._disk_key(key),
                json.dumps({"built_at": built_at, "payload": payload}, default=str),
            )
        except Exception:  # noqa: BLE001
            logger.debug("swr disk store failed name=%s key=%s", self.name, key, exc_info=True)

    # --------------------------------------------------------------- storing
    def _store(
        self,
        key: str,
        payload: Payload,
        *,
        built_at: Optional[float] = None,
        soft_ttl: Optional[float] = None,
        epoch: Optional[int] = None,
    ) -> _Entry:
        with self._lock:
            entry = _Entry(
                payload=payload,
                built_at=time.time() if built_at is None else built_at,
                epoch=self._epoch if epoch is None else epoch,
                soft_ttl=self.soft_ttl if soft_ttl is None else soft_ttl,
            )
            self._entries[key] = entry
            if len(self._entries) > self.max_entries:
                oldest = min(self._entries.items(), key=lambda kv: kv[1].built_at)[0]
                if oldest != key:
                    self._entries.pop(oldest, None)
            return entry

    def put(self, key: str, payload: Payload, *, db: Any = None) -> None:
        """Seed / replace an entry (also persists when durable)."""
        entry = self._store(key, payload)
        self._disk_store(db, key, payload, entry.built_at)

    # ---------------------------------------------------------------- reading
    def _lookup(self, key: str) -> Optional[tuple[_Entry, bool]]:
        now = time.time()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            age = now - entry.built_at
            if age >= self.hard_ttl:
                self._entries.pop(key, None)
                return None
            fresh = age < entry.soft_ttl and entry.epoch == self._epoch
            return entry, fresh

    def _schedule(
        self,
        key: str,
        builder: Callable[[], Payload],
        *,
        db: Any,
        accept: Optional[Callable[[Payload], bool]],
        had_entry: bool,
        cold_soft_ttl: float,
    ) -> Optional[threading.Event]:
        """Single-flight background build.

        Returns the completion event **only for the caller that started the build**
        (so just that first request may wait ``cold_wait``). Returns ``None`` when a
        build is already in flight or a retry is being backed off.
        """
        with self._lock:
            if key in self._inflight:
                return None
            last_fail = self._last_failure.get(key)
            if last_fail is not None and time.monotonic() - last_fail < RETRY_BACKOFF_SECONDS:
                return None
            done = threading.Event()
            self._inflight[key] = done
            epoch_at_start = self._epoch

        def _run() -> None:
            try:
                payload = builder()
                if not isinstance(payload, dict):
                    raise TypeError("swr builder must return a dict")
                ok = True if accept is None else bool(accept(payload))
                if ok:
                    entry = self._store(key, payload, epoch=epoch_at_start)
                    self._disk_store(db, key, payload, entry.built_at)
                    with self._lock:
                        self._last_failure.pop(key, None)
                elif had_entry or self._lookup(key) is not None:
                    # Upstream is degraded — keep the last good payload (stale) and
                    # back off instead of replacing it with an error skeleton.
                    with self._lock:
                        self._last_failure[key] = time.monotonic()
                else:
                    # Cold + degraded: show the honest reason briefly, retry soon.
                    self._store(key, payload, soft_ttl=cold_soft_ttl, epoch=epoch_at_start)
                    with self._lock:
                        self._last_failure[key] = time.monotonic()
            except Exception:  # noqa: BLE001 — never crash the worker
                logger.exception("swr background refresh failed name=%s key=%s", self.name, key)
                with self._lock:
                    self._last_failure[key] = time.monotonic()
            finally:
                with self._lock:
                    self._inflight.pop(key, None)
                done.set()

        threading.Thread(
            target=_run,
            name=f"swr:{self.name}:{key[:40]}",
            daemon=True,
        ).start()
        return done

    def get(
        self,
        key: str,
        builder: Callable[[], Payload],
        *,
        db: Any = None,
        warming: Optional[Callable[[], Payload]] = None,
        accept: Optional[Callable[[Payload], bool]] = None,
        cold_wait: float = 0.0,
        cold_soft_ttl: float = 5.0,
        rebase: Optional[Callable[[Payload], Payload]] = None,
    ) -> SwrResult:
        """Return the best available payload without blocking on recompute.

        ``rebase`` (optional) cheaply adjusts a cached payload at serve time (e.g.
        recomputing "now playing" from cached programs) so stale never lies.
        """

        def _serve(payload: Payload, state: str, built_at: Optional[float]) -> SwrResult:
            if rebase is not None:
                try:
                    payload = rebase(payload)
                except Exception:  # noqa: BLE001
                    logger.debug("swr rebase failed name=%s", self.name, exc_info=True)
            return SwrResult(payload=payload, state=state, built_at=built_at)

        hit = self._lookup(key)
        if hit is not None:
            entry, fresh = hit
            if fresh:
                return _serve(entry.payload, "fresh", entry.built_at)
            self._schedule(
                key, builder, db=db, accept=accept, had_entry=True, cold_soft_ttl=cold_soft_ttl
            )
            return _serve(entry.payload, "stale", entry.built_at)

        disk = self._disk_load(db, key)
        if disk is not None:
            payload, built_at = disk
            # Epoch -1 → always soft-stale, so we refresh behind this paint.
            self._store(key, payload, built_at=built_at, epoch=-1)
            self._schedule(
                key, builder, db=db, accept=accept, had_entry=True, cold_soft_ttl=cold_soft_ttl
            )
            return _serve(payload, "stale", built_at)

        done = self._schedule(
            key, builder, db=db, accept=accept, had_entry=False, cold_soft_ttl=cold_soft_ttl
        )
        if done is not None and cold_wait > 0:
            done.wait(cold_wait)
            hit = self._lookup(key)
            if hit is not None:
                return _serve(hit[0].payload, "fresh", hit[0].built_at)
        skeleton = warming() if warming is not None else {}
        return SwrResult(payload=skeleton, state="warming", built_at=None)

    def refresh_now(
        self,
        key: str,
        builder: Callable[[], Payload],
        *,
        db: Any = None,
    ) -> Payload:
        """Synchronous rebuild (explicit ``fresh=1`` / tests / prewarm threads)."""
        payload = builder()
        entry = self._store(key, payload)
        self._disk_store(db, key, payload, entry.built_at)
        return payload
