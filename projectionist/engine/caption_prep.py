"""Extract embedded text captions to WebVTT before anyone presses Play.

A playback request used to run ffmpeg with a 20-second limit. A text track
inside a large file can take longer than that to read, and the session then
fell back to Plex even though the captions are text. This work runs on the
jobs engine instead: a new arrival, Continue Watching, For you,
the title page, or a play that finds the track not ready yet. A library scan
does not enqueue the whole library.

Ready WebVTT is cached next to the household subtitle file. Picture captions
are recorded and left alone (ENG-005). The play request never waits on ffmpeg.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

from projectionist.engine.probe import IMAGE_SUBTITLE_CODECS, TEXT_SUBTITLE_CODECS, subtitle_kind
from projectionist.engine.source import MediaAsset
from projectionist.library.playback import PlaybackError, validate_rating_key
from projectionist.library.subtitle_cache import (
    cache_path,
    is_usable_subtitle_text,
    iso2,
)

logger = logging.getLogger(__name__)

# Off the play request. A text track at the end of a large MKV can mean reading
# most of the file; the old play-time limit was 20 seconds.
PREP_TIMEOUT_S = 15 * 60
TASK_NAME = "caption_prep"
QUEUE_NAME = "caption_prep_queue.json"
MANIFEST_NAME = "prepared.json"
_MAX_TRACKS = 8
_QUEUE_LIMIT = 200
# A title someone opened or pressed Play on is extracted before arrivals.
_PRIORITY_REASONS = frozenset({"play", "title"})
_ARRIVAL_LOOKBACK_S = 14 * 24 * 3600
_ARRIVAL_SCAN = 200
_RETRY_S = 10 * 60
_LANG_RE = re.compile(r"^[a-z]{2,3}$")

Extractor = Callable[[Path, int, Path], None]
LocateFn = Callable[[str], MediaAsset]
StopFn = Callable[[], bool]
Kicker = Callable[[], None]

_LOCK = threading.Lock()
_kicker: Optional[Kicker] = None


@dataclass(frozen=True)
class PreparedCaption:
    """One text track already written beside the household subtitle cache."""

    index: int
    language: str
    webvtt: str


# No language tag. Several of these in one file are different tracks, not one language.
_UNTAGGED = frozenset({"und", "undetermined", "unknown", "un", "zxx", "mul"})


def caption_language(raw: str) -> str:
    code = iso2(raw)
    if code in _UNTAGGED or not _LANG_RE.fullmatch(code):
        return ""
    return code


def text_streams(asset: MediaAsset) -> list[Any]:
    probe = asset.probe
    if probe is None:
        return []
    found = []
    for stream in probe.streams:
        if stream.codec_type != "subtitle":
            continue
        kind = stream.subtitle_kind or subtitle_kind(stream.codec)
        if kind == "image" or stream.codec in IMAGE_SUBTITLE_CODECS:
            continue
        if kind == "text" or stream.codec in TEXT_SUBTITLE_CODECS:
            found.append(stream)
    return found


def picture_streams(asset: MediaAsset) -> list[Any]:
    probe = asset.probe
    if probe is None:
        return []
    found = []
    for stream in probe.streams:
        if stream.codec_type != "subtitle":
            continue
        kind = stream.subtitle_kind or subtitle_kind(stream.codec)
        if kind == "image" or stream.codec in IMAGE_SUBTITLE_CODECS or "pgs" in str(stream.codec):
            found.append(stream)
    return found


def install_caption_prep_kicker(scheduler: Any, loop: Any) -> None:
    """Start a jobs-engine run from a request thread when the queue gains work."""

    def kick() -> None:
        if loop is None or not getattr(loop, "is_running", lambda: False)():
            return

        def _start() -> None:
            try:
                scheduler.trigger_task_background(TASK_NAME)
            except Exception:  # noqa: BLE001 — a missed kick leaves the queue for the next poll
                logger.debug("caption prep kick failed", exc_info=True)

        try:
            loop.call_soon_threadsafe(_start)
        except RuntimeError:
            logger.debug("caption prep kick missed the scheduler loop", exc_info=True)

    global _kicker
    _kicker = kick


def kick_caption_prep() -> None:
    """Ask the jobs engine to drain the queue. Tests leave the queue on disk."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    kicker = _kicker
    if kicker is None:
        return
    try:
        kicker()
    except Exception:  # noqa: BLE001 — playback must not fail because the job did not start
        logger.debug("caption prep kick failed", exc_info=True)


def note_caption_titles(
    rating_keys: Sequence[str],
    *,
    data_dir: Optional[Path] = None,
    reason: str,
    force: bool = False,
) -> None:
    """Remember titles whose text captions should be WebVTT before the next play.

    Never raises. A title page, a rail, or Play can call this on the request path.
    """
    try:
        root = _data_dir(data_dir)
        added = enqueue_caption_prep(rating_keys, data_dir=root, reason=reason, force=force)
        if added:
            kick_caption_prep()
    except Exception:  # noqa: BLE001 — caption prep is not part of answering the request
        logger.debug("caption prep note failed", exc_info=True)


def enqueue_caption_prep(
    rating_keys: Sequence[str],
    *,
    data_dir: Path,
    reason: str,
    force: bool = False,
) -> list[str]:
    """Queue rating keys that are not already WebVTT. ``force`` retries a stale file.

    Play and the title page go to the front. A full queue drops an arrival
    from the back so the title someone is watching is not last.
    """
    added: list[str] = []
    priority = reason in _PRIORITY_REASONS or force
    with _LOCK:
        items = _read_queue(data_dir)
        known = {str(item.get("rating_key") or "") for item in items}
        for raw in rating_keys:
            key = _safe_key(raw)
            if not key:
                continue
            if key in known:
                if priority:
                    items = [item for item in items if str(item.get("rating_key") or "") != key]
                    items.insert(0, {"rating_key": key, "reason": reason, "not_before": 0})
                    added.append(key)
                continue
            if not force and _settled(data_dir, key):
                continue
            if len(items) >= _QUEUE_LIMIT:
                if not priority:
                    break
                _drop_backlog(items)
            entry = {"rating_key": key, "reason": reason, "not_before": 0}
            if priority:
                items.insert(0, entry)
            else:
                items.append(entry)
            known.add(key)
            added.append(key)
        _write_queue(data_dir, items)
    return added


def _drop_backlog(items: list[dict[str, Any]]) -> None:
    """Remove one non-priority row from the back. The front is who is watching."""
    for index in range(len(items) - 1, -1, -1):
        if str(items[index].get("reason") or "") not in _PRIORITY_REASONS:
            items.pop(index)
            return
    if items:
        items.pop()


def enqueue_recent_arrivals(db: Any, *, data_dir: Path, limit: int = 40) -> list[str]:
    """Queue movies and episodes added in the last two weeks (library scan / new arrival)."""
    if db is None or not hasattr(db, "connect"):
        return []
    cutoff = int(time.time()) - _ARRIVAL_LOOKBACK_S
    keys: list[str] = []
    try:
        with db.connect() as conn:
            movie_rows = conn.execute(
                """
                SELECT rating_key FROM library_items
                WHERE media_type = 'movie'
                  AND rating_key IS NOT NULL AND rating_key != ''
                  AND added_at IS NOT NULL AND added_at >= ?
                ORDER BY added_at DESC
                LIMIT ?
                """,
                (cutoff, _ARRIVAL_SCAN),
            ).fetchall()
            episode_rows = conn.execute(
                """
                SELECT rating_key FROM library_episodes
                WHERE rating_key IS NOT NULL AND rating_key != ''
                  AND added_at IS NOT NULL AND added_at >= ?
                ORDER BY added_at DESC
                LIMIT ?
                """,
                (cutoff, _ARRIVAL_SCAN),
            ).fetchall()
    except Exception:  # noqa: BLE001 — a scan without these columns just does not queue
        logger.debug("caption prep could not read recent arrivals", exc_info=True)
        return []
    for row in list(movie_rows) + list(episode_rows):
        try:
            raw = row["rating_key"]
        except (KeyError, IndexError, TypeError):
            raw = row[0] if row else ""
        key = _safe_key(raw)
        if key and key not in keys:
            keys.append(key)
    added: list[str] = []
    room = max(0, int(limit))
    for key in keys:
        if len(added) >= room:
            break
        added.extend(enqueue_caption_prep([key], data_dir=data_dir, reason="arrival"))
    return added


def prepared_tracks(asset: MediaAsset, *, data_dir: Path) -> list[PreparedCaption]:
    """WebVTT written ahead of play, when it still matches this file. Otherwise nothing."""
    manifest = _read_manifest(data_dir, asset.rating_key)
    if not manifest or str(manifest.get("status") or "") != "ready":
        return []
    if not _fingerprint_matches(asset, manifest):
        return []
    folder = _prepared_dir(data_dir, asset.rating_key)
    if folder is None:
        return []
    tracks: list[PreparedCaption] = []
    for raw in manifest.get("tracks") or []:
        if not isinstance(raw, dict):
            continue
        value = raw.get("index")
        if value is None:
            continue
        try:
            index = int(value)
        except (TypeError, ValueError):
            continue
        if index < 0:
            continue
        path = folder / f"s{index}.vtt"
        webvtt = _usable_webvtt(path)
        if not webvtt:
            continue
        tracks.append(
            PreparedCaption(index=index, language=caption_language(str(raw.get("language") or "")), webvtt=webvtt)
        )
    return tracks


def has_unprepared_text(asset: MediaAsset, *, data_dir: Path) -> bool:
    """True when this file has a text track that is not WebVTT for this exact file yet."""
    streams = text_streams(asset)
    if not streams or not asset.local_path:
        return False
    manifest = _read_manifest(data_dir, asset.rating_key)
    if manifest is None or not _fingerprint_matches(asset, manifest):
        return True
    if str(manifest.get("status") or "") != "ready":
        return True
    covered = {str(item) for item in (manifest.get("covered_languages") or [])}
    have: set[int] = set()
    for raw in manifest.get("tracks") or []:
        if not isinstance(raw, dict):
            continue
        language = caption_language(str(raw.get("language") or ""))
        if language:
            covered.add(language)
        value = raw.get("index")
        if value is None:
            continue
        try:
            have.add(int(value))
        except (TypeError, ValueError):
            continue
    for stream in streams:
        language = caption_language(str(getattr(stream, "language", "") or ""))
        # One prepared track covers every stream of that language. Extract keeps
        # only the first. A stream with no language is covered only by its index.
        if language and language in covered:
            continue
        if int(getattr(stream, "index", -1)) in have:
            continue
        return True
    return False


def extract_text_captions(
    asset: MediaAsset,
    *,
    data_dir: Path,
    extractor: Optional[Extractor] = None,
) -> str:
    """Write text tracks to WebVTT. Picture-only titles are marked and not extracted.

    Returns ``ready``, ``picture``, ``none``, ``unreadable``, or ``failed``.
    """
    if asset.probe is None or not asset.readable or not asset.local_path:
        return "unreadable"
    source = Path(asset.local_path)
    try:
        if not source.is_file():
            return "unreadable"
    except OSError:
        return "unreadable"
    fingerprint = _fingerprint(source)
    if fingerprint is None:
        return "unreadable"
    texts = text_streams(asset)
    images = picture_streams(asset)
    if not texts and not images:
        _write_manifest(data_dir, asset.rating_key, status="none", tracks=[], covered=[], fingerprint=fingerprint)
        return "none"
    if not texts:
        _write_manifest(
            data_dir, asset.rating_key, status="picture", tracks=[], covered=[], fingerprint=fingerprint
        )
        return "picture"
    if not has_unprepared_text(asset, data_dir=data_dir):
        return "ready"
    covered = _cached_languages(asset, data_dir)
    todo = []
    seen: set[str] = set()
    for stream in texts:
        language = caption_language(str(getattr(stream, "language", "") or ""))
        if language and language in covered:
            continue
        if language and language in seen:
            continue
        todo.append(stream)
        if language:
            seen.add(language)
        if len(todo) >= _MAX_TRACKS:
            break
    extract = extractor or _ffmpeg_extract
    tracks: list[dict[str, Any]] = []
    written: set[str] = set()
    for stream in todo:
        index = int(getattr(stream, "index", -1))
        language = caption_language(str(getattr(stream, "language", "") or ""))
        webvtt = _capture(source, index, extract)
        if not webvtt:
            continue
        if not _write_vtt(data_dir, asset.rating_key, index, webvtt):
            continue
        tracks.append({"index": index, "language": language})
        if language:
            written.add(language)
    if todo and not tracks:
        return "failed"
    _write_manifest(
        data_dir,
        asset.rating_key,
        status="ready",
        tracks=tracks,
        covered=sorted(covered | written),
        fingerprint=fingerprint,
    )
    return "ready"


def drain_caption_queue(
    *,
    data_dir: Path,
    locate: LocateFn,
    should_stop: StopFn,
    limit: int = 1,
    extractor: Optional[Extractor] = None,
) -> dict[str, Any]:
    """Prepare up to ``limit`` queued titles. Failures stay queued and wait before retrying."""
    claimed = _claim_due(data_dir, max(1, int(limit)))
    processed = 0
    for key in claimed:
        if should_stop():
            _defer(data_dir, key, reason="interrupted", delay=0)
            break
        try:
            asset = locate(key)
        except Exception:  # noqa: BLE001 — one title must not stop the queue
            logger.debug("caption prep could not locate %s", key, exc_info=True)
            _defer(data_dir, key, reason="unreadable", delay=_RETRY_S)
            continue
        status = extract_text_captions(asset, data_dir=data_dir, extractor=extractor)
        if status in {"ready", "picture", "none"}:
            processed += 1
            continue
        _defer(data_dir, key, reason=status, delay=_RETRY_S)
    remaining = _due_count(data_dir)
    return {
        "status": "completed",
        "processed": processed,
        "has_more": remaining > 0,
        "batch_size": max(1, int(limit)),
    }


def _ffmpeg_extract(source: Path, index: int, dest: Path) -> None:
    from projectionist.engine.media_slot import run_media_tool
    from projectionist.library.episode_investigate.capabilities import resolve_ffmpeg

    binary = resolve_ffmpeg()
    if not binary:
        return
    try:
        completed = run_media_tool(
            [
                binary,
                "-y",
                "-i",
                str(source),
                "-map",
                f"0:{int(index)}",
                "-f",
                "webvtt",
                str(dest),
            ],
            subprocess.run,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=PREP_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.debug("text caption extract failed index=%s", index, exc_info=True)
        _discard_partial(dest)
        raise
    # ffmpeg often writes a finished WebVTT and still exits 1 because a later
    # packet failed to demux. That file is a track. A timeout, an empty file,
    # and a file with no cues are not.
    if getattr(completed, "returncode", 0) not in (0, None) and not _usable_webvtt(dest):
        _discard_partial(dest)


def _discard_partial(path: Path) -> None:
    """Drop a timed-out, empty, or unusable extract. A usable WebVTT stays."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.debug("could not discard a partial caption extract", exc_info=True)


def _capture(source: Path, index: int, extract: Extractor) -> str:
    if index < 0:
        return ""
    try:
        with tempfile.TemporaryDirectory(prefix="eng-caption-") as tmp:
            dest = Path(tmp) / "track.vtt"
            extract(source, int(index), dest)
            return _usable_webvtt(dest)
    except Exception:  # noqa: BLE001 — one bad track must not fail the title
        logger.debug("text caption extract failed index=%s", index, exc_info=True)
        return ""


def _usable_webvtt(path: Path) -> str:
    from projectionist.engine.captions import _as_webvtt, _read_limited

    if not path.is_file():
        return ""
    return _as_webvtt(_read_limited(path))


def _data_dir(data_dir: Optional[Path]) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    from projectionist.logging_config import resolve_data_dir

    return resolve_data_dir()


def _safe_key(raw: Any) -> str:
    try:
        return validate_rating_key(raw)
    except PlaybackError:
        return ""


def _queue_path(data_dir: Path) -> Path:
    return Path(data_dir) / QUEUE_NAME


def _read_queue(data_dir: Path) -> list[dict[str, Any]]:
    path = _queue_path(data_dir)
    try:
        if not path.is_file():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    items: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        key = _safe_key(raw.get("rating_key"))
        if not key:
            continue
        try:
            not_before = float(raw.get("not_before") or 0)
        except (TypeError, ValueError):
            not_before = 0
        items.append(
            {
                "rating_key": key,
                "reason": str(raw.get("reason") or ""),
                "not_before": not_before,
            }
        )
    return items


def _write_queue(data_dir: Path, items: Sequence[dict[str, Any]]) -> None:
    path = _queue_path(data_dir)
    payload = {"items": list(items)[:_QUEUE_LIMIT]}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        logger.debug("could not store the caption prep queue", exc_info=True)


def _claim_due(data_dir: Path, limit: int) -> list[str]:
    now = time.time()
    claimed: list[str] = []
    with _LOCK:
        items = _read_queue(data_dir)
        kept: list[dict[str, Any]] = []
        for item in items:
            if len(claimed) < limit and float(item.get("not_before") or 0) <= now:
                claimed.append(str(item["rating_key"]))
            else:
                kept.append(item)
        _write_queue(data_dir, kept)
    return claimed


def _defer(data_dir: Path, rating_key: str, *, reason: str, delay: float) -> None:
    with _LOCK:
        items = _read_queue(data_dir)
        items.append(
            {
                "rating_key": rating_key,
                "reason": reason,
                "not_before": time.time() + max(0.0, float(delay)),
            }
        )
        _write_queue(data_dir, items)


def _due_count(data_dir: Path) -> int:
    now = time.time()
    return sum(1 for item in _read_queue(data_dir) if float(item.get("not_before") or 0) <= now)


def _cache_root(data_dir: Path, rating_key: str) -> Optional[Path]:
    sample = cache_path(rating_key, "en", data_dir=data_dir)
    if sample is None:
        return None
    return sample.parent


def _prepared_dir(data_dir: Path, rating_key: str) -> Optional[Path]:
    root = _cache_root(data_dir, rating_key)
    if root is None:
        return None
    return root / "prepared"


def _manifest_path(data_dir: Path, rating_key: str) -> Optional[Path]:
    root = _cache_root(data_dir, rating_key)
    if root is None:
        return None
    return root / MANIFEST_NAME


def _fingerprint(path: Path) -> Optional[tuple[int, int]]:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (int(stat.st_size), int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))))


def _fingerprint_matches(asset: MediaAsset, manifest: dict[str, Any]) -> bool:
    if not asset.local_path:
        return False
    current = _fingerprint(Path(asset.local_path))
    if current is None:
        return False
    try:
        recorded = (int(manifest.get("size") or -1), int(manifest.get("mtime_ns") or -1))
    except (TypeError, ValueError):
        return False
    return recorded == current


def _read_manifest(data_dir: Path, rating_key: str) -> Optional[dict[str, Any]]:
    path = _manifest_path(data_dir, rating_key)
    if path is None or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_manifest(
    data_dir: Path,
    rating_key: str,
    *,
    status: str,
    tracks: Sequence[dict[str, Any]],
    covered: Sequence[str],
    fingerprint: tuple[int, int],
) -> None:
    path = _manifest_path(data_dir, rating_key)
    if path is None:
        return
    payload = {
        "status": status,
        "size": fingerprint[0],
        "mtime_ns": fingerprint[1],
        "tracks": list(tracks),
        "covered_languages": list(covered),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        logger.debug("could not store prepared captions for %s", rating_key, exc_info=True)


def _write_vtt(data_dir: Path, rating_key: str, index: int, webvtt: str) -> bool:
    folder = _prepared_dir(data_dir, rating_key)
    if folder is None or index < 0:
        return False
    path = folder / f"s{int(index)}.vtt"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".vtt.tmp")
        tmp.write_text(webvtt, encoding="utf-8")
        tmp.replace(path)
    except OSError:
        logger.debug("could not store prepared webvtt index=%s", index, exc_info=True)
        return False
    return True


def _settled(data_dir: Path, rating_key: str) -> bool:
    manifest = _read_manifest(data_dir, rating_key)
    if not manifest:
        return False
    return str(manifest.get("status") or "") in {"ready", "picture", "none"}


def _cached_languages(asset: MediaAsset, data_dir: Path) -> set[str]:
    root = _cache_root(data_dir, asset.rating_key)
    if root is None or not root.is_dir():
        return set()
    found: set[str] = set()
    try:
        paths = list(root.glob("*.srt"))
    except OSError:
        return set()
    for path in paths:
        language = caption_language(path.stem)
        if not language:
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if is_usable_subtitle_text(body):
            found.add(language)
    return found
