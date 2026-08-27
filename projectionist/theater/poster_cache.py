"""Shared theater poster cache — memory LRU + disk + negative + single-flight."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.theater import (
    POSTER_DISK_MAX_BYTES,
    POSTER_DISK_TTL_SECONDS,
    POSTER_MEMORY_MAX_BYTES,
    POSTER_MEMORY_MAX_ENTRIES,
    POSTER_NEGATIVE_TTL_SECONDS,
)

logger = logging.getLogger(__name__)

CACHE_DIR_NAME = "theater-poster-cache"


@dataclass(frozen=True)
class CachedPoster:
    body: bytes
    content_type: str
    etag: str
    source_fingerprint: str


def content_etag(body: bytes) -> str:
    return '"' + hashlib.sha256(body).hexdigest()[:32] + '"'


def source_fingerprint(url: str) -> str:
    return hashlib.sha256(str(url or "").encode("utf-8")).hexdigest()[:24]


def _ext_for_content_type(content_type: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct == "image/png":
        return ".png"
    if ct == "image/webp":
        return ".webp"
    if ct == "image/gif":
        return ".gif"
    return ".jpg"


class TheaterPosterCache:
    """Process-local poster cache backed by DATA_DIR for multi-kiosk fan-in."""

    def __init__(
        self,
        data_dir: Path,
        *,
        negative_ttl: float = POSTER_NEGATIVE_TTL_SECONDS,
        disk_ttl: float = POSTER_DISK_TTL_SECONDS,
        memory_max_entries: int = POSTER_MEMORY_MAX_ENTRIES,
        memory_max_bytes: int = POSTER_MEMORY_MAX_BYTES,
        disk_max_bytes: int = POSTER_DISK_MAX_BYTES,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.cache_dir = self.data_dir / CACHE_DIR_NAME
        self.negative_ttl = float(negative_ttl)
        self.disk_ttl = float(disk_ttl)
        self.memory_max_entries = int(memory_max_entries)
        self.memory_max_bytes = int(memory_max_bytes)
        self.disk_max_bytes = int(disk_max_bytes)
        self._lock = threading.RLock()
        self._memory: OrderedDict[str, CachedPoster] = OrderedDict()
        self._memory_bytes = 0
        self._negative: Dict[str, float] = {}
        self._hits = 0
        self._misses = 0
        self._negative_hits = 0
        self._inflight: Dict[str, asyncio.Future] = {}
        self._inflight_lock = asyncio.Lock()

    @property
    def hits(self) -> int:
        return int(self._hits)

    @property
    def misses(self) -> int:
        return int(self._misses)

    @property
    def negative_hits(self) -> int:
        return int(self._negative_hits)

    def is_negative(self, rating_key: str) -> bool:
        key = str(rating_key or "").strip()
        if not key:
            return False
        with self._lock:
            expires = self._negative.get(key)
            if expires is None:
                return False
            if time.monotonic() >= expires:
                self._negative.pop(key, None)
                return False
            self._negative_hits += 1
            return True

    def remember_miss(self, rating_key: str) -> None:
        key = str(rating_key or "").strip()
        if not key:
            return
        with self._lock:
            self._negative[key] = time.monotonic() + self.negative_ttl

    def clear_negative(self, rating_key: str) -> None:
        key = str(rating_key or "").strip()
        with self._lock:
            self._negative.pop(key, None)

    def get(self, rating_key: str) -> Optional[CachedPoster]:
        key = str(rating_key or "").strip()
        if not key:
            return None
        with self._lock:
            cached = self._memory.get(key)
            if cached is not None:
                self._memory.move_to_end(key)
                self._hits += 1
                return cached
        disk = self._read_disk(key)
        if disk is not None:
            with self._lock:
                self._put_memory_locked(key, disk)
                self._hits += 1
            return disk
        with self._lock:
            self._misses += 1
        return None

    def put(
        self,
        rating_key: str,
        body: bytes,
        content_type: str,
        *,
        source: str = "",
    ) -> CachedPoster:
        key = str(rating_key or "").strip()
        poster = CachedPoster(
            body=body,
            content_type=(content_type or "image/jpeg").split(";")[0].strip()
            or "image/jpeg",
            etag=content_etag(body),
            source_fingerprint=source_fingerprint(source),
        )
        if not key or not body:
            return poster
        with self._lock:
            self._negative.pop(key, None)
            self._put_memory_locked(key, poster)
        self._write_disk(key, poster)
        return poster

    def _put_memory_locked(self, key: str, poster: CachedPoster) -> None:
        existing = self._memory.pop(key, None)
        if existing is not None:
            self._memory_bytes -= len(existing.body)
        self._memory[key] = poster
        self._memory_bytes += len(poster.body)
        while (
            len(self._memory) > self.memory_max_entries
            or self._memory_bytes > self.memory_max_bytes
        ) and self._memory:
            old_key, old = self._memory.popitem(last=False)
            self._memory_bytes -= len(old.body)
            del old_key

    def _meta_path(self, key: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in key)[:80]
        return self.cache_dir / f"{safe}.meta.json"

    def _body_path(self, key: str, content_type: str) -> Path:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in key)[:80]
        return self.cache_dir / f"{safe}{_ext_for_content_type(content_type)}"

    def _read_disk(self, key: str) -> Optional[CachedPoster]:
        meta_path = self._meta_path(key)
        if not meta_path.is_file():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            stored_at = float(meta.get("stored_at") or 0)
            if stored_at and (time.time() - stored_at) > self.disk_ttl:
                self._unlink_quiet(meta_path)
                body_name = str(meta.get("body") or "")
                if body_name:
                    self._unlink_quiet(self.cache_dir / body_name)
                return None
            body_name = str(meta.get("body") or "")
            body_path = self.cache_dir / body_name if body_name else None
            if body_path is None or not body_path.is_file():
                return None
            body = body_path.read_bytes()
            content_type = str(meta.get("content_type") or "image/jpeg")
            etag = str(meta.get("etag") or content_etag(body))
            fingerprint = str(meta.get("source_fingerprint") or "")
            # Touch mtime for LRU eviction.
            now = time.time()
            os.utime(body_path, (now, now))
            os.utime(meta_path, (now, now))
            return CachedPoster(
                body=body,
                content_type=content_type,
                etag=etag,
                source_fingerprint=fingerprint,
            )
        except Exception:  # noqa: BLE001
            logger.debug("theater poster disk read failed for %s", key, exc_info=True)
            return None

    def _write_disk(self, key: str, poster: CachedPoster) -> None:
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            body_path = self._body_path(key, poster.content_type)
            meta_path = self._meta_path(key)
            tmp_body = body_path.with_suffix(body_path.suffix + ".tmp")
            tmp_meta = meta_path.with_suffix(".tmp")
            tmp_body.write_bytes(poster.body)
            tmp_body.replace(body_path)
            meta = {
                "rating_key": key,
                "content_type": poster.content_type,
                "etag": poster.etag,
                "source_fingerprint": poster.source_fingerprint,
                "stored_at": time.time(),
                "body": body_path.name,
                "bytes": len(poster.body),
            }
            tmp_meta.write_text(json.dumps(meta), encoding="utf-8")
            tmp_meta.replace(meta_path)
            self._enforce_disk_cap()
        except Exception:  # noqa: BLE001
            logger.debug("theater poster disk write failed for %s", key, exc_info=True)

    def _enforce_disk_cap(self) -> None:
        try:
            if not self.cache_dir.is_dir():
                return
            entries: List[Tuple[float, Path, int]] = []
            total = 0
            for path in self.cache_dir.iterdir():
                if not path.is_file():
                    continue
                if path.suffix == ".tmp" or path.name.endswith(".tmp"):
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                entries.append((stat.st_mtime, path, stat.st_size))
                total += stat.st_size
            if total <= self.disk_max_bytes:
                return
            entries.sort(key=lambda row: row[0])  # oldest first
            for _mtime, path, size in entries:
                if total <= self.disk_max_bytes:
                    break
                self._unlink_quiet(path)
                total -= size
        except Exception:  # noqa: BLE001
            logger.debug("theater poster disk eviction failed", exc_info=True)

    @staticmethod
    def _unlink_quiet(path: Path) -> None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    async def single_flight(self, rating_key: str, factory: Callable[[], Any]) -> Any:
        """Coalesce concurrent fetches for the same rating key.

        Waiters always observe a terminal future (result or exception),
        including when the leader is cancelled: ``CancelledError`` inherits
        from ``BaseException`` (not ``Exception``), so the shared Future must
        still be completed before the leader re-raises. The inflight slot is
        cleared in ``finally`` so a failed flight never leaves subsequent
        callers blocked on a dead Future — waiters can retry a new flight.
        """
        key = str(rating_key or "").strip()
        async with self._inflight_lock:
            existing = self._inflight.get(key)
            if existing is not None:
                wait = existing
            else:
                loop = asyncio.get_running_loop()
                fut: asyncio.Future = loop.create_future()
                self._inflight[key] = fut
                wait = None

        if wait is not None:
            return await asyncio.shield(wait)

        try:
            result = factory()
            if asyncio.iscoroutine(result):
                result = await result
            async with self._inflight_lock:
                fut = self._inflight.get(key)
                if fut is not None and not fut.done():
                    fut.set_result(result)
            return result
        except BaseException as exc:
            # Must cover CancelledError (BaseException in 3.9+) so waiters
            # holding asyncio.shield(wait) never hang on an incomplete Future.
            async with self._inflight_lock:
                fut = self._inflight.get(key)
                if fut is not None and not fut.done():
                    if isinstance(exc, asyncio.CancelledError):
                        fut.set_exception(asyncio.CancelledError())
                    else:
                        fut.set_exception(exc)
            raise
        finally:
            async with self._inflight_lock:
                self._inflight.pop(key, None)


_CACHES: Dict[str, TheaterPosterCache] = {}
_CACHES_LOCK = threading.Lock()


def get_poster_cache(data_dir: Path) -> TheaterPosterCache:
    resolved = str(Path(data_dir).expanduser().resolve())
    with _CACHES_LOCK:
        cache = _CACHES.get(resolved)
        if cache is None:
            cache = TheaterPosterCache(Path(resolved))
            _CACHES[resolved] = cache
        return cache


def reset_poster_caches_for_tests() -> None:
    with _CACHES_LOCK:
        _CACHES.clear()


_prefetch_lock = threading.Lock()
_prefetch_pending: set[str] = set()


def schedule_poster_prefetch(
    rating_keys: List[str],
    data_dir: Path,
    db_factory: Callable[[], Database],
    settings_factory: Callable[[], Settings],
) -> None:
    """Fire-and-forget warm of ≤16 visible posters (daemon thread)."""
    keys = [str(k).strip() for k in rating_keys if str(k).strip()][:16]
    if not keys:
        return
    with _prefetch_lock:
        todo = [k for k in keys if k not in _prefetch_pending]
        for k in todo:
            _prefetch_pending.add(k)
    if not todo:
        return

    def _run() -> None:
        try:
            from projectionist.theater.poster import fetch_poster_bytes_sync

            db = db_factory()
            settings = settings_factory()
            cache = get_poster_cache(data_dir)
            for rk in todo:
                try:
                    if cache.is_negative(rk) or cache.get(rk) is not None:
                        continue
                    fetch_poster_bytes_sync(db, settings, data_dir=data_dir, rating_key=rk)
                except Exception:  # noqa: BLE001
                    logger.debug("theater poster prefetch failed rk=%s", rk, exc_info=True)
        finally:
            with _prefetch_lock:
                for k in todo:
                    _prefetch_pending.discard(k)

    thread = threading.Thread(target=_run, daemon=True, name="theater-poster-prefetch")
    thread.start()
