"""Re-derive Sonarr gaps from series episode records, then EpisodeSearch.

Owner-triggered “Find all missing” — not Sonarr’s Wanted list, and not a
``MissingEpisodeSearch`` command. Scan is a background job; Search these
submits ``EpisodeSearch`` in chunks, then status polls Sonarr’s command
queue until those commands finish or the owner cancels remaining queued
ones.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

EPISODE_SEARCH_CHUNK = 50
LAST_SCAN_FILENAME = "sonarr_missing_last.json"
WANTED_PAGE_SIZE = 100
THROTTLE_NOTE = (
    "Sonarr runs a few EpisodeSearch commands at a time; the rest wait in its "
    "command queue. Projectionist already submitted them — this is not a hang. "
    "Failed here means the Sonarr command failed, not a download-client abort."
)
TERMINAL_STATUSES = frozenset({"completed", "failed", "aborted", "cancelled"})
RUNNING_STATUSES = frozenset({"started", "running", "cancelling", "canceling"})
QUEUED_STATUSES = frozenset({"queued", "pending"})
FAILED_STATUSES = frozenset({"failed", "aborted"})

PhaseCallback = Callable[..., None]


def _parse_air_date(value: Any) -> Optional[datetime]:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _season_is_monitored(
    seasons: Optional[Sequence[Mapping[str, Any]]],
    season_number: int,
    *,
    series_monitored: bool,
) -> bool:
    if not seasons:
        return bool(series_monitored)
    for season in seasons:
        if not isinstance(season, Mapping):
            continue
        try:
            number = int(season.get("seasonNumber"))
        except (TypeError, ValueError):
            continue
        if number == int(season_number):
            return bool(season.get("monitored"))
    return bool(series_monitored)


def is_aired_missing_episode(
    episode: Mapping[str, Any],
    *,
    now: datetime,
    include_specials: bool,
    series_monitored: bool,
    season_monitored: Optional[bool],
) -> bool:
    """True when an episode is aired, monitored, and has no file."""
    if not series_monitored:
        return False
    if not bool(episode.get("monitored")):
        return False
    if bool(episode.get("hasFile")):
        return False
    try:
        season_number = int(episode.get("seasonNumber") or 0)
    except (TypeError, ValueError):
        season_number = 0
    if season_number == 0 and not include_specials:
        return False
    if season_monitored is False:
        return False
    if season_monitored is None and not series_monitored:
        return False
    aired = _parse_air_date(episode.get("airDateUtc") or episode.get("airDate"))
    if aired is None or aired > now:
        return False
    return True


def filter_aired_missing_episodes(
    episodes: Sequence[Mapping[str, Any]],
    *,
    series_id: int,
    series_title: str,
    series_monitored: bool,
    seasons: Optional[Sequence[Mapping[str, Any]]],
    include_specials: bool,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Keep aired+monitored+no-file episodes for one series."""
    clock = now or datetime.now(timezone.utc)
    rows: List[Dict[str, Any]] = []
    if not series_monitored:
        return rows
    for episode in episodes:
        if not isinstance(episode, Mapping):
            continue
        try:
            season_number = int(episode.get("seasonNumber") or 0)
        except (TypeError, ValueError):
            season_number = 0
        season_monitored = _season_is_monitored(
            seasons, season_number, series_monitored=series_monitored
        )
        if include_specials and season_number == 0 and series_monitored:
            season_monitored = True
        if not is_aired_missing_episode(
            episode,
            now=clock,
            include_specials=include_specials,
            series_monitored=series_monitored,
            season_monitored=season_monitored,
        ):
            continue
        try:
            episode_id = int(episode.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if episode_id <= 0:
            continue
        try:
            episode_number = int(episode.get("episodeNumber") or 0)
        except (TypeError, ValueError):
            episode_number = 0
        rows.append(
            {
                "seriesId": int(series_id),
                "seriesTitle": str(series_title or ""),
                "episodeId": episode_id,
                "season": season_number,
                "episode": episode_number,
                "airDate": str(episode.get("airDateUtc") or episode.get("airDate") or ""),
                "title": str(episode.get("title") or ""),
            }
        )
    return rows


def compare_to_wanted(scan_ids: Iterable[int], wanted_ids: Iterable[int]) -> Dict[str, Any]:
    scan = [int(value) for value in scan_ids]
    wanted = [int(value) for value in wanted_ids]
    scan_set = set(scan)
    wanted_set = set(wanted)
    only_in_scan = sorted(scan_set - wanted_set)
    only_in_wanted = sorted(wanted_set - scan_set)
    return {
        "scan_count": len(scan_set),
        "wanted_count": len(wanted_set),
        "only_in_scan": only_in_scan,
        "only_in_wanted": only_in_wanted,
        "summary": (
            f"Library scan found {len(scan_set)}; Sonarr Wanted lists {len(wanted_set)}"
        ),
    }


def group_missing_by_series(episodes: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[int, Dict[str, Any]] = {}
    order: List[int] = []
    for row in episodes:
        try:
            series_id = int(row.get("seriesId") or 0)
        except (TypeError, ValueError):
            continue
        if series_id not in grouped:
            grouped[series_id] = {
                "seriesId": series_id,
                "seriesTitle": str(row.get("seriesTitle") or ""),
                "count": 0,
                "episodes": [],
            }
            order.append(series_id)
        grouped[series_id]["episodes"].append(dict(row))
        grouped[series_id]["count"] += 1
    groups = [grouped[key] for key in order]
    groups.sort(key=lambda item: str(item.get("seriesTitle") or "").lower())
    return groups


def collect_wanted_ids(client: Any) -> List[int]:
    """Page through GET /api/v3/wanted/missing for compare-only counts."""
    ids: List[int] = []
    page = 1
    while page <= 1000:
        payload = client.wanted_missing(page=page, page_size=WANTED_PAGE_SIZE)
        if not isinstance(payload, Mapping):
            break
        records = payload.get("records") or []
        if not isinstance(records, list) or not records:
            break
        for record in records:
            if not isinstance(record, Mapping):
                continue
            try:
                episode_id = int(record.get("id") or 0)
            except (TypeError, ValueError):
                continue
            if episode_id > 0:
                ids.append(episode_id)
        total = int(payload.get("totalRecords") or 0)
        if total and len(ids) >= total:
            break
        if len(records) < WANTED_PAGE_SIZE:
            break
        page += 1
    return ids


def scan_monitored_series(
    client: Any,
    *,
    include_specials: bool = False,
    now: Optional[datetime] = None,
    on_progress: Optional[PhaseCallback] = None,
) -> Dict[str, Any]:
    """Scan every monitored series’ episodes and compare to Wanted."""
    clock = now or datetime.now(timezone.utc)
    raw_items: List[Mapping[str, Any]] = []
    if hasattr(client, "series_items"):
        payload = client.series_items() or []
        if isinstance(payload, list):
            raw_items = [item for item in payload if isinstance(item, Mapping)]
    if not raw_items and hasattr(client, "series_list"):
        for series in client.series_list() or []:
            raw_items.append(
                {
                    "id": int(getattr(series, "id", 0) or 0),
                    "title": str(getattr(series, "title", "") or ""),
                    "monitored": bool(getattr(series, "monitored", False)),
                    "seasons": list(getattr(series, "seasons", None) or []),
                }
            )

    monitored = [item for item in raw_items if bool(item.get("monitored"))]
    total = len(monitored)
    episodes: List[Dict[str, Any]] = []
    if on_progress:
        on_progress(
            "scanning",
            series_done=0,
            series_total=total,
            missing_found=0,
            message="Scanning monitored series…",
        )
    for index, series in enumerate(monitored, start=1):
        series_id = int(series.get("id") or 0)
        title = str(series.get("title") or "")
        if series_id <= 0:
            continue
        series_episodes = client.episodes(series_id) or []
        rows = filter_aired_missing_episodes(
            series_episodes if isinstance(series_episodes, list) else [],
            series_id=series_id,
            series_title=title,
            series_monitored=True,
            seasons=series.get("seasons") if isinstance(series.get("seasons"), list) else None,
            include_specials=include_specials,
            now=clock,
        )
        episodes.extend(rows)
        if on_progress:
            on_progress(
                "scanning",
                series_done=index,
                series_total=total,
                missing_found=len(episodes),
                message=f"Scanning {title}…" if title else f"Scanning series {index} of {total}…",
            )

    if on_progress:
        on_progress(
            "comparing",
            series_done=total,
            series_total=total,
            missing_found=len(episodes),
            message="Comparing to Sonarr Wanted…",
        )
    wanted_ids = collect_wanted_ids(client)
    scan_ids = [int(row["episodeId"]) for row in episodes]
    comparison = compare_to_wanted(scan_ids, wanted_ids)
    result = {
        "episodes": episodes,
        "episode_ids": scan_ids,
        "by_series": group_missing_by_series(episodes),
        "include_specials": bool(include_specials),
        **comparison,
    }
    return result


def queue_episode_searches(
    client: Any,
    episode_ids: Sequence[int],
    *,
    chunk_size: int = EPISODE_SEARCH_CHUNK,
    on_progress: Optional[PhaseCallback] = None,
    should_continue: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    """Fire EpisodeSearch commands in chunks. Never MissingEpisodeSearch."""
    ids = [int(value) for value in episode_ids if int(value) > 0]
    size = max(1, int(chunk_size or EPISODE_SEARCH_CHUNK))
    chunks = [ids[index : index + size] for index in range(0, len(ids), size)] if ids else []
    queued = 0
    commands: List[Dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        if should_continue is not None and not should_continue():
            pending = len(chunks) - queued
            if on_progress:
                on_progress(
                    "searching",
                    searches_queued=queued,
                    searches_total=len(chunks),
                    pending_submit=pending,
                    missing_found=len(ids),
                    message="Stopped sending more EpisodeSearch commands.",
                )
            return {
                "searches_queued": queued,
                "command": "EpisodeSearch",
                "episode_count": len(ids),
                "chunk_size": size,
                "commands": commands,
                "stopped_early": True,
                "pending_submit": pending,
            }
        payload = client.search_episodes(chunk) or {}
        record = command_record_from_payload(
            payload if isinstance(payload, Mapping) else {},
            episode_ids=chunk,
        )
        commands.append(record)
        queued += 1
        if on_progress:
            on_progress(
                "searching",
                searches_queued=queued,
                searches_total=len(chunks),
                pending_submit=len(chunks) - queued,
                missing_found=len(ids),
                message=f"Submitted EpisodeSearch {index} of {len(chunks)} to Sonarr…",
            )
    return {
        "searches_queued": queued,
        "command": "EpisodeSearch",
        "episode_count": len(ids),
        "chunk_size": size,
        "commands": commands,
        "stopped_early": False,
        "pending_submit": 0,
    }


def normalize_command_status(value: Any) -> str:
    raw = str(value or "").strip().lower()
    aliases = {
        "queued": "queued",
        "pending": "queued",
        "started": "started",
        "running": "started",
        "completed": "completed",
        "failed": "failed",
        "aborted": "aborted",
        "cancelled": "cancelled",
        "canceled": "cancelled",
        "cancelling": "started",
        "canceling": "started",
    }
    return aliases.get(raw, raw or "queued")


def _is_episode_search(item: Mapping[str, Any]) -> bool:
    name = str(item.get("name") or item.get("commandName") or "").replace(" ", "")
    return name.lower() == "episodesearch"


def _episode_ids_from_command(item: Mapping[str, Any]) -> List[int]:
    raw = item.get("episode_ids") or item.get("episodeIds")
    if not raw:
        body = item.get("body")
        if isinstance(body, Mapping):
            raw = body.get("episodeIds")
    ids: List[int] = []
    if isinstance(raw, list):
        for value in raw:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                ids.append(number)
    return ids


def command_record_from_payload(
    payload: Mapping[str, Any],
    *,
    episode_ids: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    ids = [int(value) for value in (episode_ids or []) if int(value) > 0]
    if not ids:
        ids = _episode_ids_from_command(payload)
    try:
        command_id = int(payload.get("id") or 0)
    except (TypeError, ValueError):
        command_id = 0
    ended = payload.get("ended_at") or payload.get("ended")
    return {
        "id": command_id,
        "name": str(payload.get("name") or payload.get("commandName") or "EpisodeSearch"),
        "status": normalize_command_status(payload.get("status") or "queued"),
        "message": str(payload.get("message") or "")[:240],
        "exception": str(payload.get("exception") or "")[:400],
        "queued_at": str(payload.get("queued_at") or payload.get("queued") or ""),
        "started_at": str(payload.get("started_at") or payload.get("started") or ""),
        "ended_at": str(ended or ""),
        "episode_ids": ids,
        "episode_count": len(ids),
    }


def _merge_command_records(
    tracked: Sequence[Mapping[str, Any]],
    live: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    by_id: Dict[int, Dict[str, Any]] = {}
    tracked_ids: set[int] = set()
    for item in tracked:
        if not isinstance(item, Mapping):
            continue
        record = command_record_from_payload(item, episode_ids=item.get("episode_ids"))
        cid = int(record.get("id") or 0)
        if cid <= 0:
            continue
        tracked_ids.add(cid)
        by_id[cid] = record
    for item in live:
        if not isinstance(item, Mapping):
            continue
        record = command_record_from_payload(item)
        cid = int(record.get("id") or 0)
        if cid <= 0:
            continue
        if cid in tracked_ids or _is_episode_search(record):
            existing = by_id.get(cid)
            if existing:
                if not record.get("episode_ids"):
                    record["episode_ids"] = existing.get("episode_ids") or []
                    record["episode_count"] = existing.get("episode_count") or len(record["episode_ids"])
                by_id[cid] = record
            else:
                by_id[cid] = record
    live_ids = {
        int(command_record_from_payload(item).get("id") or 0)
        for item in live
        if isinstance(item, Mapping)
    }
    live_ids.discard(0)
    if live_ids:
        for cid, existing in by_id.items():
            if cid in live_ids:
                continue
            if normalize_command_status(existing.get("status")) in TERMINAL_STATUSES:
                continue
            existing["status"] = "completed"
            if not existing.get("message"):
                existing["message"] = "Finished — no longer in Sonarr’s command list"
    return list(by_id.values())


def _ended_timestamp(value: Any) -> float:
    parsed = _parse_air_date(value)
    if parsed is None:
        return 0.0
    return parsed.timestamp()


def summarize_episode_search_commands(
    tracked: Sequence[Mapping[str, Any]],
    live: Optional[Sequence[Mapping[str, Any]]] = None,
    *,
    pending_submit: int = 0,
) -> Dict[str, Any]:
    """Aggregate Sonarr EpisodeSearch command status. Not download-client history."""
    rows = _merge_command_records(list(tracked or []), list(live or []))
    queued = running = completed = failed = cancelled = 0
    current: Optional[Dict[str, Any]] = None
    last_error = ""
    last_completed_at = ""
    last_completed_ts = 0.0
    now = time.time()
    for row in rows:
        status = normalize_command_status(row.get("status"))
        if status in QUEUED_STATUSES:
            queued += 1
        elif status in RUNNING_STATUSES or status == "started":
            running += 1
            if current is None:
                current = {
                    "id": row.get("id"),
                    "status": status,
                    "name": row.get("name") or "EpisodeSearch",
                    "message": str(row.get("message") or row.get("name") or "EpisodeSearch"),
                }
        elif status == "completed":
            completed += 1
        elif status in FAILED_STATUSES:
            failed += 1
            err = str(row.get("exception") or row.get("message") or "").strip()
            if err:
                last_error = err[:400]
        elif status == "cancelled":
            cancelled += 1
        ended = str(row.get("ended_at") or "")
        if ended and status in TERMINAL_STATUSES:
            stamp = _ended_timestamp(ended)
            if stamp >= last_completed_ts:
                last_completed_ts = stamp
                last_completed_at = ended
    pending = max(0, int(pending_submit or 0))
    total = len(rows) + pending
    finished = completed + failed + cancelled
    if total <= 0:
        percent = 0
    elif finished >= total and pending == 0 and queued == 0 and running == 0:
        percent = 100
    else:
        percent = min(99, int(100 * finished / max(total, 1)))
    seconds_since: Optional[int] = None
    if last_completed_ts:
        seconds_since = max(0, int(now - last_completed_ts))
    return {
        "queued": queued,
        "running": running,
        "completed": completed,
        "failed": failed,
        "cancelled": cancelled,
        "pending_submit": pending,
        "total": total,
        "finished": finished,
        "percent": percent,
        "current": current,
        "last_error": last_error,
        "last_completed_at": last_completed_at,
        "seconds_since_last_completion": seconds_since,
        "throttle_note": THROTTLE_NOTE,
        "kind": "command",
        "commands": rows,
    }


def _execution_message(summary: Mapping[str, Any], *, submitting: bool = False) -> str:
    queued = int(summary.get("queued") or 0)
    running = int(summary.get("running") or 0)
    completed = int(summary.get("completed") or 0)
    failed = int(summary.get("failed") or 0)
    cancelled = int(summary.get("cancelled") or 0)
    pending = int(summary.get("pending_submit") or 0)
    current = summary.get("current") if isinstance(summary.get("current"), Mapping) else None
    bits = []
    if submitting and pending:
        bits.append(f"Submitting {pending} more to Sonarr")
    bits.extend(
        [
            f"{queued} queued",
            f"{running} running",
            f"{completed} completed",
            f"{failed} failed",
        ]
    )
    if cancelled:
        bits.append(f"{cancelled} cancelled")
    if current and current.get("message"):
        bits.append(str(current.get("message")))
    return " · ".join(bits)


def _finished_message(summary: Mapping[str, Any]) -> str:
    completed = int(summary.get("completed") or 0)
    failed = int(summary.get("failed") or 0)
    cancelled = int(summary.get("cancelled") or 0)
    total = int(summary.get("total") or 0)
    if cancelled and completed == 0 and failed == 0:
        return f"Cancelled remaining EpisodeSearch commands ({cancelled} cancelled)."
    if failed:
        return (
            f"Sonarr finished {total} EpisodeSearch command(s): "
            f"{completed} completed · {failed} failed"
            + (f" · {cancelled} cancelled" if cancelled else "")
            + "."
        )
    if cancelled:
        return f"Sonarr finished {completed} EpisodeSearch command(s); {cancelled} cancelled."
    return f"Sonarr finished {completed} EpisodeSearch command(s)."


class SonarrMissingJobStore:
    """Process-local progress; last scan also lands in DATA_DIR for Confirm."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = self._idle_state()

    @staticmethod
    def _idle_state() -> Dict[str, Any]:
        return {
            "job_id": "",
            "phase": "idle",
            "percent": 0,
            "message": "Ready when you are",
            "busy": False,
            "ok": True,
            "error": "",
            "include_specials": False,
            "series_done": 0,
            "series_total": 0,
            "missing_found": 0,
            "searches_queued": 0,
            "searches_total": 0,
            "pending_submit": 0,
            "commands": [],
            "cancel_requested": False,
            "result": None,
            "updated_at": 0.0,
        }

    def reset(self) -> None:
        with self._lock:
            self._state = self._idle_state()
            self._state["updated_at"] = time.time()

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            out = dict(self._state)
            if isinstance(out.get("result"), dict):
                out["result"] = dict(out["result"])
            if isinstance(out.get("commands"), list):
                out["commands"] = [
                    dict(item) if isinstance(item, dict) else item for item in out["commands"]
                ]
            return out

    def begin(self, *, kind: str, include_specials: bool = False) -> Optional[str]:
        with self._lock:
            if self._state.get("busy"):
                return None
            job_id = uuid.uuid4().hex[:12]
            keep_result = self._state.get("result") if kind == "search" else None
            keep_commands = [] if kind == "search" else list(self._state.get("commands") or [])
            self._state.update(
                {
                    "job_id": job_id,
                    "phase": "queued",
                    "percent": 5,
                    "message": (
                        "Submitting EpisodeSearch to Sonarr…"
                        if kind == "search"
                        else "Queued library scan…"
                    ),
                    "busy": True,
                    "ok": True,
                    "error": "",
                    "include_specials": bool(include_specials)
                    if kind == "scan"
                    else bool(self._state.get("include_specials")),
                    "series_done": 0 if kind == "scan" else int(self._state.get("series_done") or 0),
                    "series_total": 0 if kind == "scan" else int(self._state.get("series_total") or 0),
                    "missing_found": 0
                    if kind == "scan"
                    else int(self._state.get("missing_found") or 0),
                    "searches_queued": 0,
                    "searches_total": 0,
                    "pending_submit": 0,
                    "commands": keep_commands,
                    "cancel_requested": False,
                    "result": dict(keep_result) if isinstance(keep_result, dict) else keep_result,
                    "updated_at": time.time(),
                }
            )
            return job_id

    def update(
        self,
        phase: str,
        message: str = "",
        *,
        percent: Optional[int] = None,
        series_done: Optional[int] = None,
        series_total: Optional[int] = None,
        missing_found: Optional[int] = None,
        searches_queued: Optional[int] = None,
        searches_total: Optional[int] = None,
        pending_submit: Optional[int] = None,
    ) -> None:
        with self._lock:
            self._state["phase"] = phase
            if series_done is not None:
                self._state["series_done"] = int(series_done)
            if series_total is not None:
                self._state["series_total"] = int(series_total)
            if missing_found is not None:
                self._state["missing_found"] = int(missing_found)
            if searches_queued is not None:
                self._state["searches_queued"] = int(searches_queued)
            if searches_total is not None:
                self._state["searches_total"] = int(searches_total)
            if pending_submit is not None:
                self._state["pending_submit"] = int(pending_submit)
            terminal = phase in {"idle", "done", "searched", "error", "cancelled"}
            if percent is not None:
                cap = 100 if terminal else 99
                self._state["percent"] = max(0, min(int(percent), cap))
            elif phase == "scanning":
                total = max(int(self._state.get("series_total") or 0), 1)
                done = int(self._state.get("series_done") or 0)
                self._state["percent"] = min(85, 10 + int(75 * done / total))
            elif phase == "comparing":
                self._state["percent"] = 90
            elif phase == "searching":
                total = max(int(self._state.get("searches_total") or 0), 1)
                done = int(self._state.get("searches_queued") or 0)
                self._state["percent"] = min(40, int(40 * done / total)) if total else 5
            if message:
                self._state["message"] = str(message)
            self._state["busy"] = phase not in {"idle", "done", "searched", "error", "cancelled"}
            self._state["ok"] = phase != "error"
            self._state["updated_at"] = time.time()

    def set_commands(
        self,
        commands: Sequence[Mapping[str, Any]],
        *,
        searches_queued: Optional[int] = None,
        searches_total: Optional[int] = None,
        pending_submit: Optional[int] = None,
    ) -> None:
        with self._lock:
            self._state["commands"] = [
                dict(item) for item in commands if isinstance(item, Mapping)
            ]
            if searches_queued is not None:
                self._state["searches_queued"] = int(searches_queued)
            if searches_total is not None:
                self._state["searches_total"] = int(searches_total)
            if pending_submit is not None:
                self._state["pending_submit"] = int(pending_submit)
            self._state["updated_at"] = time.time()

    def set_result(self, result: Mapping[str, Any]) -> None:
        with self._lock:
            self._state["result"] = dict(result)
            self._state["updated_at"] = time.time()

    def request_cancel(self) -> None:
        with self._lock:
            self._state["cancel_requested"] = True
            self._state["updated_at"] = time.time()
            if not self._state.get("message"):
                self._state["message"] = "Cancel requested…"

    def set_error(self, message: str) -> None:
        with self._lock:
            self._state["phase"] = "error"
            self._state["percent"] = 100
            self._state["message"] = str(message or "Sonarr missing job failed")
            self._state["busy"] = False
            self._state["ok"] = False
            self._state["error"] = str(message or "Sonarr missing job failed")
            self._state["updated_at"] = time.time()

    def set_done(self, message: str = "", *, result: Optional[Mapping[str, Any]] = None, phase: str = "done") -> None:
        with self._lock:
            self._state["phase"] = phase
            self._state["percent"] = 100
            self._state["message"] = str(
                message
                or (
                    "Searches finished"
                    if phase == "searched"
                    else "Cancelled"
                    if phase == "cancelled"
                    else "Scan finished"
                )
            )
            self._state["busy"] = False
            self._state["ok"] = True
            self._state["error"] = ""
            if isinstance(result, Mapping):
                self._state["result"] = dict(result)
            self._state["updated_at"] = time.time()


_STORE = SonarrMissingJobStore()
_WORKER_LOCK = threading.Lock()
_WORKER: Optional[threading.Thread] = None
_CANCEL = threading.Event()


def progress_store() -> SonarrMissingJobStore:
    return _STORE


def reset_sonarr_missing_for_tests() -> None:
    global _WORKER
    with _WORKER_LOCK:
        _WORKER = None
    _CANCEL.clear()
    _STORE.reset()


def _search_should_continue() -> bool:
    return not _CANCEL.is_set()


def _worker_alive() -> bool:
    with _WORKER_LOCK:
        return _WORKER is not None and _WORKER.is_alive()


def _persist_last_scan(
    data_dir: Path,
    result: Mapping[str, Any],
    *,
    commands: Optional[Sequence[Mapping[str, Any]]] = None,
) -> None:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / LAST_SCAN_FILENAME
        tmp = path.with_suffix(".tmp")
        existing_commands: List[Any] = []
        if commands is None and path.is_file():
            try:
                previous = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                previous = {}
            if isinstance(previous, dict) and isinstance(previous.get("commands"), list):
                existing_commands = previous["commands"]
        payload = {
            "saved_at": time.time(),
            "result": dict(result),
            "commands": list(commands) if commands is not None else existing_commands,
        }
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)
    except OSError as error:
        logger.warning("Could not persist Sonarr missing scan: %s", error)


def load_last_scan(data_dir: Path) -> Optional[Dict[str, Any]]:
    path = data_dir / LAST_SCAN_FILENAME
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        return dict(payload["result"])
    return None


def load_last_commands(data_dir: Path) -> List[Dict[str, Any]]:
    path = data_dir / LAST_SCAN_FILENAME
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get("commands") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [dict(item) for item in rows if isinstance(item, Mapping)]


def _status_payload(snap: Mapping[str, Any]) -> Dict[str, Any]:
    pending = int(snap.get("pending_submit") or 0)
    execution = summarize_episode_search_commands(
        snap.get("commands") or [],
        live=[],
        pending_submit=pending,
    )
    execution_out = {key: value for key, value in execution.items() if key != "commands"}
    phase = str(snap.get("phase") or "idle")
    can_cancel = bool(
        phase in {"searching", "executing"}
        or execution["queued"] > 0
        or execution["pending_submit"] > 0
    )
    percent = int(snap.get("percent") or 0)
    if phase == "executing":
        percent = max(1, min(99, int(execution.get("percent") or 0) or 1))
    elif phase == "searching":
        percent = min(percent, 40)
    return {
        "job_id": str(snap.get("job_id") or ""),
        "phase": phase,
        "percent": percent,
        "message": str(snap.get("message") or ""),
        "busy": bool(snap.get("busy")),
        "ok": bool(snap.get("ok", True)),
        "error": str(snap.get("error") or ""),
        "include_specials": bool(snap.get("include_specials")),
        "series_done": int(snap.get("series_done") or 0),
        "series_total": int(snap.get("series_total") or 0),
        "missing_found": int(snap.get("missing_found") or 0),
        "searches_queued": int(snap.get("searches_queued") or 0),
        "searches_total": int(snap.get("searches_total") or 0),
        "result": snap.get("result"),
        "execution": execution_out,
        "can_cancel": can_cancel,
        "cancel_requested": bool(snap.get("cancel_requested")),
        "current": execution.get("current"),
    }


def refresh_execution(
    client: Any,
    store: Optional[SonarrMissingJobStore] = None,
    *,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Poll Sonarr command queue/history and update the local job snapshot."""
    store = store or progress_store()
    snap = store.snapshot()
    phase = str(snap.get("phase") or "idle")
    if phase in {"scanning", "comparing"} and snap.get("busy"):
        return _status_payload(snap)

    live: List[Mapping[str, Any]] = []
    if client is not None and hasattr(client, "list_commands"):
        try:
            payload = client.list_commands() or []
            if isinstance(payload, list):
                live = [item for item in payload if isinstance(item, Mapping)]
        except Exception as error:  # noqa: BLE001 — keep last known status
            logger.warning("Could not list Sonarr commands: %s", error)

    tracked = list(snap.get("commands") or [])
    if not tracked and data_dir is not None:
        tracked = load_last_commands(data_dir)
    pending = int(snap.get("pending_submit") or 0)
    if phase == "searching" and _worker_alive():
        pending = max(
            pending,
            int(snap.get("searches_total") or 0) - int(snap.get("searches_queued") or 0),
        )
    summary = summarize_episode_search_commands(tracked, live, pending_submit=pending)
    store.set_commands(
        summary.get("commands") or [],
        searches_queued=int(snap.get("searches_queued") or 0),
        searches_total=int(snap.get("searches_total") or summary.get("total") or 0),
        pending_submit=pending if phase == "searching" and _worker_alive() else int(summary.get("pending_submit") or 0),
    )
    if data_dir is not None and isinstance(snap.get("result"), dict):
        _persist_last_scan(data_dir, snap["result"], commands=summary.get("commands") or [])

    still_submitting = phase == "searching" and _worker_alive()
    remaining = (
        int(summary.get("queued") or 0)
        + int(summary.get("running") or 0)
        + (int(summary.get("pending_submit") or 0) if still_submitting else 0)
    )
    if still_submitting:
        store.update(
            "searching",
            _execution_message(summary, submitting=True),
            searches_queued=int(snap.get("searches_queued") or 0),
            searches_total=int(snap.get("searches_total") or 0),
            pending_submit=pending,
        )
    elif int(summary.get("total") or 0) > 0 and remaining > 0:
        exec_percent = max(1, min(99, int(summary.get("percent") or 0) or 1))
        store.update(
            "executing",
            _execution_message(summary),
            percent=exec_percent,
            searches_queued=int(snap.get("searches_queued") or 0),
            searches_total=int(snap.get("searches_total") or summary.get("total") or 0),
            pending_submit=0,
        )
    elif int(summary.get("total") or 0) > 0:
        finished_phase = "cancelled"
        if int(summary.get("completed") or 0) or int(summary.get("failed") or 0):
            finished_phase = "searched"
        elif not snap.get("cancel_requested") and int(summary.get("cancelled") or 0) == 0:
            finished_phase = "searched"
        message = _finished_message(summary)
        store.set_done(message, phase=finished_phase)
        store.update(
            finished_phase,
            message,
            percent=100,
            searches_queued=int(snap.get("searches_queued") or 0),
            searches_total=int(snap.get("searches_total") or summary.get("total") or 0),
            pending_submit=0,
        )
    return _status_payload(store.snapshot())


def build_status(*, data_dir: Optional[Path] = None, client: Any = None) -> Dict[str, Any]:
    if client is not None:
        try:
            return refresh_execution(client, data_dir=data_dir)
        except Exception as error:  # noqa: BLE001 — fall back to last snapshot
            logger.warning("Sonarr command refresh failed: %s", error)
    snap = progress_store().snapshot()
    result = snap.get("result")
    if not isinstance(result, dict) and data_dir is not None:
        result = load_last_scan(data_dir)
        if result:
            snap["result"] = result
            snap["missing_found"] = int(result.get("scan_count") or snap.get("missing_found") or 0)
            if snap.get("phase") == "idle":
                snap["phase"] = "done"
                snap["percent"] = 100
                snap["message"] = str(result.get("summary") or "Last scan ready")
    if not snap.get("commands") and data_dir is not None:
        loaded = load_last_commands(data_dir)
        if loaded:
            snap["commands"] = loaded
    return _status_payload(snap)


def cancel_remaining_searches(client: Any, *, data_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Stop submitting more batches and DELETE queued (not started) EpisodeSearch commands."""
    _CANCEL.set()
    store = progress_store()
    store.request_cancel()
    live: List[Mapping[str, Any]] = []
    if client is not None and hasattr(client, "list_commands"):
        try:
            payload = client.list_commands() or []
            if isinstance(payload, list):
                live = [item for item in payload if isinstance(item, Mapping)]
        except Exception as error:  # noqa: BLE001 — still mark cancel requested
            logger.warning("Could not list Sonarr commands to cancel: %s", error)
    snap = store.snapshot()
    merged = _merge_command_records(snap.get("commands") or [], live)
    if client is not None and hasattr(client, "cancel_command"):
        for row in merged:
            status = normalize_command_status(row.get("status"))
            try:
                command_id = int(row.get("id") or 0)
            except (TypeError, ValueError):
                command_id = 0
            if command_id <= 0 or status != "queued":
                continue
            if not _is_episode_search(row):
                continue
            try:
                client.cancel_command(command_id)
            except Exception as error:  # noqa: BLE001 — continue remaining ids
                logger.warning("Could not cancel Sonarr command %s: %s", command_id, error)
    return refresh_execution(client, store, data_dir=data_dir)


def _make_progress(store: SonarrMissingJobStore) -> PhaseCallback:
    def _on_progress(phase: str, message: str = "", **kwargs: Any) -> None:
        store.update(phase, message, **kwargs)

    return _on_progress


def start_scan_job(
    client: Any,
    *,
    include_specials: bool = False,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    store = progress_store()
    job_id = store.begin(kind="scan", include_specials=include_specials)
    if not job_id:
        snap = build_status(data_dir=data_dir)
        snap["accepted"] = False
        snap["message"] = snap.get("message") or "A Sonarr missing job is already running."
        return snap

    on_progress = _make_progress(store)

    def _run() -> None:
        try:
            result = scan_monitored_series(
                client,
                include_specials=include_specials,
                on_progress=on_progress,
            )
            if data_dir is not None:
                _persist_last_scan(data_dir, result)
            store.set_done(
                str(result.get("summary") or "Scan finished"),
                result=result,
                phase="done",
            )
            store.update(
                "done",
                str(result.get("summary") or "Scan finished"),
                percent=100,
                missing_found=int(result.get("scan_count") or 0),
                series_done=int(store.snapshot().get("series_done") or 0),
                series_total=int(store.snapshot().get("series_total") or 0),
            )
        except Exception as error:  # noqa: BLE001 — surface on progress store
            logger.exception("sonarr missing scan failed: %s", error)
            store.set_error(str(error)[:400] or "Sonarr missing scan failed.")
        finally:
            global _WORKER
            with _WORKER_LOCK:
                _WORKER = None

    thread = threading.Thread(target=_run, name="sonarr-missing-scan", daemon=True)
    with _WORKER_LOCK:
        global _WORKER
        _WORKER = thread
    thread.start()
    snap = build_status(data_dir=data_dir)
    snap["accepted"] = True
    snap["job_id"] = job_id
    return snap


def start_search_job(
    client: Any,
    *,
    episode_ids: Optional[Sequence[int]] = None,
    search_all: bool = False,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    store = progress_store()
    ids = [int(value) for value in (episode_ids or []) if int(value) > 0]
    if search_all or not ids:
        result = store.snapshot().get("result")
        if not isinstance(result, dict) and data_dir is not None:
            result = load_last_scan(data_dir)
        if isinstance(result, dict):
            ids = [int(value) for value in (result.get("episode_ids") or []) if int(value) > 0]
    if not ids:
        snap = build_status(data_dir=data_dir)
        snap["accepted"] = False
        snap["message"] = "No missing episodes to search. Run Find all missing first."
        return snap

    include_specials = bool(store.snapshot().get("include_specials"))
    _CANCEL.clear()
    job_id = store.begin(kind="search", include_specials=include_specials)
    if not job_id:
        snap = build_status(data_dir=data_dir)
        snap["accepted"] = False
        snap["message"] = snap.get("message") or "A Sonarr missing job is already running."
        return snap

    on_progress = _make_progress(store)

    def _run() -> None:
        try:
            queued = queue_episode_searches(
                client,
                ids,
                on_progress=on_progress,
                should_continue=_search_should_continue,
            )
            current = store.snapshot().get("result")
            merged = dict(current) if isinstance(current, dict) else {}
            merged["search"] = {key: value for key, value in queued.items() if key != "commands"}
            store.set_commands(
                queued.get("commands") or [],
                searches_queued=int(queued.get("searches_queued") or 0),
                searches_total=int(queued.get("searches_queued") or 0)
                + int(queued.get("pending_submit") or 0),
                pending_submit=int(queued.get("pending_submit") or 0),
            )
            store.set_result(merged)
            if data_dir is not None:
                _persist_last_scan(data_dir, merged, commands=queued.get("commands") or [])
            if queued.get("stopped_early"):
                store.update(
                    "executing",
                    "Stopped submitting; waiting on Sonarr for commands already sent…",
                    searches_queued=int(queued.get("searches_queued") or 0),
                    pending_submit=0,
                )
            else:
                store.update(
                    "executing",
                    "Waiting on Sonarr to run EpisodeSearch…",
                    searches_queued=int(queued.get("searches_queued") or 0),
                    searches_total=int(queued.get("searches_queued") or 0),
                    pending_submit=0,
                )
            refresh_execution(client, store, data_dir=data_dir)
        except Exception as error:  # noqa: BLE001 — surface on progress store
            logger.exception("sonarr missing search failed: %s", error)
            store.set_error(str(error)[:400] or "Sonarr missing search failed.")
        finally:
            global _WORKER
            with _WORKER_LOCK:
                _WORKER = None

    thread = threading.Thread(target=_run, name="sonarr-missing-search", daemon=True)
    with _WORKER_LOCK:
        global _WORKER
        _WORKER = thread
    thread.start()
    snap = build_status(data_dir=data_dir)
    snap["accepted"] = True
    snap["job_id"] = job_id
    return snap
