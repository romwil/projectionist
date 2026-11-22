"""Copies made ahead of time (ENG-014).

The owner picks a folder outside every Plex library. The job takes the
playability ranking — titles above 1080p first, then the most-watched — and
makes one compatible file at a time until the disk budget. It runs only from
01:00 to 06:00 household time. A partial file is not a ready copy. This module
does not start an encode on import.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from projectionist.engine.media_slot import media_command
from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.engine.source import MediaAsset

DEFAULT_BUDGET_BYTES = 200 * 1024 * 1024 * 1024
_PART = ".part"
_READY = ".mp4"

Runner = Callable[[list[str], Path], str]
SourceFn = Callable[[str], Path]


def in_copy_window(moment: datetime) -> bool:
    """True from 01:00 inclusive until 06:00 exclusive, in that clock's zone."""
    local = moment.astimezone(moment.tzinfo) if moment.tzinfo is not None else moment
    return 1 <= local.hour < 6


def copy_folder_problem(output: Path, library_paths: Sequence[Path]) -> str:
    """Empty when ``output`` may hold copies. Otherwise one sentence.

    A symlink, a trailing slash, and a parent of a library are the same folder
    as the library they point at. A name that only shares a prefix is not.
    """
    try:
        folder = Path(output).expanduser().resolve()
    except OSError:
        return "That folder is not writable."
    libraries: list[Path] = []
    for raw in library_paths:
        try:
            libraries.append(Path(raw).expanduser().resolve())
        except OSError:
            continue
    for library in libraries:
        if folder == library or _is_inside(folder, library):
            return "That folder is inside a Plex library."
        if _is_inside(library, folder):
            return "That folder contains a Plex library."
    if not _can_write(folder):
        return "That folder is not writable."
    return ""


def titles_within_budget(
    titles: Sequence[Mapping[str, Any]],
    *,
    budget_bytes: int,
    used_bytes: int = 0,
) -> list[Mapping[str, Any]]:
    """Titles that still fit, above 1080p first, then most-watched.

    The walk stops at the first title that would pass the budget. A later
    smaller title does not skip ahead.
    """
    used = max(0, int(used_bytes or 0))
    budget = max(0, int(budget_bytes or 0))
    chosen: list[Mapping[str, Any]] = []
    for row in sorted(titles, key=_sort_key):
        if not isinstance(row, Mapping):
            continue
        size = _size(row.get("file_size"))
        if used + size > budget:
            break
        chosen.append(row)
        used += size
    return chosen


def run_copy_pass(
    titles: Sequence[Mapping[str, Any]],
    output_dir: Path,
    *,
    budget_bytes: int,
    now: datetime,
    runner: Runner,
    source_for: SourceFn,
) -> dict[str, Any]:
    """Encode at most one title. Outside the window, do not call ``runner``."""
    output = Path(output_dir)
    if not in_copy_window(now):
        return {"status": "asleep", "ready": False, "rating_key": "", "resumed": False}
    output.mkdir(parents=True, exist_ok=True)
    used = _bytes_on_disk(output, titles)
    for row in sorted(titles, key=_sort_key):
        if not isinstance(row, Mapping):
            continue
        key = str(row.get("rating_key") or "").strip()
        if not key or "/" in key or key in {".", ".."}:
            continue
        final = output / f"{key}{_READY}"
        part = output / f"{key}{_PART}"
        if _is_ready_file(final):
            continue
        resumed = part.is_file()
        size = _size(row.get("file_size"))
        if not resumed and used + size > max(0, int(budget_bytes or 0)):
            return {"status": "budget", "ready": False, "rating_key": "", "resumed": False}
        source = Path(source_for(key))
        command = media_command(_ffmpeg_args(source, part))
        outcome = runner(command, part)
        ready = outcome == "complete" and part.is_file() and part.stat().st_size > 0
        if ready:
            part.replace(final)
            _write_note(output / f"{key}.json", key)
        return {
            "status": "ready" if ready else "partial",
            "ready": ready,
            "rating_key": key,
            "resumed": resumed,
        }
    return {"status": "idle", "ready": False, "rating_key": "", "resumed": False}


def describe_copies(
    titles: Sequence[Mapping[str, Any]],
    output_dir: Optional[Path],
    *,
    budget_bytes: int,
) -> dict[str, Any]:
    """Queue, used bytes, and which files can be removed. No source paths."""
    output = Path(output_dir) if output_dir is not None else None
    used = 0
    queue: list[dict[str, Any]] = []
    remaining = max(0, int(budget_bytes or 0))
    for row in sorted(titles, key=_sort_key):
        if not isinstance(row, Mapping):
            continue
        key = str(row.get("rating_key") or "").strip()
        if not key:
            continue
        final = output / f"{key}{_READY}" if output is not None else None
        part = output / f"{key}{_PART}" if output is not None else None
        size = _size(row.get("file_size"))
        if final is not None and _is_ready_file(final):
            actual = final.stat().st_size
            used += actual
            remaining -= actual
            queue.append(_row(row, key, "ready", actual))
            continue
        if part is not None and part.is_file():
            actual = part.stat().st_size
            used += actual
            queue.append(_row(row, key, "partial", size or actual))
            continue
        if size > max(0, remaining):
            break
        remaining -= size
        queue.append(_row(row, key, "queued", size))
    return {"used_bytes": max(0, used), "budget_bytes": int(budget_bytes or 0), "queue": queue}


def remove_copy(output_dir: Path, rating_key: str) -> None:
    """Delete one ready copy and any partial beside it."""
    key = str(rating_key or "").strip()
    if not key or "/" in key or key in {".", ".."}:
        raise ValueError("rating_key is required")
    output = Path(output_dir)
    for name in (f"{key}{_READY}", f"{key}{_PART}", f"{key}.json"):
        path = output / name
        if path.is_file():
            path.unlink()


def ready_copy_asset(output_dir: Path, rating_key: str) -> Optional[MediaAsset]:
    """A finished copy, as a file the planner can direct-play or remux.

    A partial file has no note and is not returned.
    """
    key = str(rating_key or "").strip()
    output = Path(output_dir)
    final = output / f"{key}{_READY}"
    note = output / f"{key}.json"
    if not key or not _is_ready_file(final) or not note.is_file():
        return None
    try:
        meta = json.loads(note.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict) or str(meta.get("rating_key") or "") != key:
        return None
    return MediaAsset(
        rating_key=key,
        local_path=str(final),
        readable=True,
        probe=ProbeResult(
            container="mp4",
            format_name="mp4",
            duration_s=0,
            bitrate=0,
            size=final.stat().st_size,
            streams=[
                MediaStream(
                    index=0,
                    codec_type="video",
                    codec="h264",
                    level="4.1",
                    width=1920,
                    height=1080,
                ),
                MediaStream(
                    index=1,
                    codec_type="audio",
                    codec="aac",
                    language="eng",
                    channels=2,
                ),
            ],
        ),
    )


def _ffmpeg_args(source: Path, destination: Path) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(source),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-c:a",
        "aac",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(destination),
    ]


def _write_note(path: Path, rating_key: str) -> None:
    path.write_text(
        json.dumps({"rating_key": rating_key, "container": "mp4", "video": "h264", "audio": "aac"}),
        encoding="utf-8",
    )


def _row(row: Mapping[str, Any], key: str, status: str, size: int) -> dict[str, Any]:
    return {
        "rating_key": key,
        "title": str(row.get("title") or ""),
        "status": status,
        "file_size": int(size),
        "above_1080p": bool(row.get("above_1080p")),
        "watch_count": _size(row.get("watch_count")),
    }


def _bytes_on_disk(output: Path, titles: Sequence[Mapping[str, Any]]) -> int:
    total = 0
    for row in titles:
        if not isinstance(row, Mapping):
            continue
        key = str(row.get("rating_key") or "")
        final = output / f"{key}{_READY}"
        part = output / f"{key}{_PART}"
        if _is_ready_file(final):
            total += final.stat().st_size
        elif part.is_file():
            total += part.stat().st_size
    return total


def _is_ready_file(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0 and path.suffix != _PART


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        return path.is_relative_to(parent) and path != parent
    except (OSError, ValueError):
        return False


def _can_write(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".projectionist-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


def _size(value: Any) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0


def _sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        0 if row.get("above_1080p") else 1,
        -_size(row.get("watch_count")),
        str(row.get("title") or ""),
        str(row.get("rating_key") or ""),
    )
