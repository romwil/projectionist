"""Re-derive Sonarr gaps from series episode records, then EpisodeSearch.

Owner-triggered “Find all missing” — not Sonarr’s Wanted list, and not a
``MissingEpisodeSearch`` command. Scan is a background job; Confirm queues
``EpisodeSearch`` in chunks.
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
) -> Dict[str, Any]:
    """Fire EpisodeSearch commands in chunks. Never MissingEpisodeSearch."""
    ids = [int(value) for value in episode_ids if int(value) > 0]
    size = max(1, int(chunk_size or EPISODE_SEARCH_CHUNK))
    chunks = [ids[index : index + size] for index in range(0, len(ids), size)] if ids else []
    queued = 0
    for index, chunk in enumerate(chunks, start=1):
        client.search_episodes(chunk)
        queued += 1
        if on_progress:
            on_progress(
                "searching",
                searches_queued=queued,
                searches_total=len(chunks),
                missing_found=len(ids),
                message=f"Queued EpisodeSearch {index} of {len(chunks)}…",
            )
    return {
        "searches_queued": queued,
        "command": "EpisodeSearch",
        "episode_count": len(ids),
        "chunk_size": size,
    }


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
            return out

    def begin(self, *, kind: str, include_specials: bool = False) -> Optional[str]:
        with self._lock:
            if self._state.get("busy"):
                return None
            job_id = uuid.uuid4().hex[:12]
            keep_result = self._state.get("result") if kind == "search" else None
            self._state.update(
                {
                    "job_id": job_id,
                    "phase": "queued",
                    "percent": 5,
                    "message": (
                        "Queued EpisodeSearch…" if kind == "search" else "Queued library scan…"
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
            if percent is not None:
                self._state["percent"] = max(0, min(int(percent), 99 if phase not in {"done", "searched", "error"} else 100))
            elif phase == "scanning":
                total = max(int(self._state.get("series_total") or 0), 1)
                done = int(self._state.get("series_done") or 0)
                self._state["percent"] = min(85, 10 + int(75 * done / total))
            elif phase == "comparing":
                self._state["percent"] = 90
            elif phase == "searching":
                total = max(int(self._state.get("searches_total") or 0), 1)
                done = int(self._state.get("searches_queued") or 0)
                self._state["percent"] = min(99, 20 + int(70 * done / total))
            if message:
                self._state["message"] = str(message)
            self._state["busy"] = phase not in {"idle", "done", "searched", "error"}
            self._state["ok"] = phase != "error"
            self._state["updated_at"] = time.time()

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
            self._state["message"] = str(message or ("Search queued" if phase == "searched" else "Scan finished"))
            self._state["busy"] = False
            self._state["ok"] = True
            self._state["error"] = ""
            if isinstance(result, Mapping):
                self._state["result"] = dict(result)
            self._state["updated_at"] = time.time()


_STORE = SonarrMissingJobStore()
_WORKER_LOCK = threading.Lock()
_WORKER: Optional[threading.Thread] = None


def progress_store() -> SonarrMissingJobStore:
    return _STORE


def reset_sonarr_missing_for_tests() -> None:
    global _WORKER
    with _WORKER_LOCK:
        _WORKER = None
    _STORE.reset()


def _persist_last_scan(data_dir: Path, result: Mapping[str, Any]) -> None:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        path = data_dir / LAST_SCAN_FILENAME
        tmp = path.with_suffix(".tmp")
        payload = {
            "saved_at": time.time(),
            "result": dict(result),
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


def build_status(*, data_dir: Optional[Path] = None) -> Dict[str, Any]:
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
    return {
        "job_id": str(snap.get("job_id") or ""),
        "phase": str(snap.get("phase") or "idle"),
        "percent": int(snap.get("percent") or 0),
        "message": str(snap.get("message") or ""),
        "busy": bool(snap.get("busy")),
        "ok": bool(snap.get("ok", True)),
        "error": str(snap.get("error") or ""),
        "include_specials": bool(snap.get("include_specials")),
        "series_done": int(snap.get("series_done") or 0),
        "series_total": int(snap.get("series_total") or 0),
        "missing_found": int(snap.get("missing_found") or 0),
        "searches_queued": int(snap.get("searches_queued") or 0),
        "result": snap.get("result"),
    }


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
    job_id = store.begin(kind="search", include_specials=include_specials)
    if not job_id:
        snap = build_status(data_dir=data_dir)
        snap["accepted"] = False
        snap["message"] = snap.get("message") or "A Sonarr missing job is already running."
        return snap

    on_progress = _make_progress(store)

    def _run() -> None:
        try:
            queued = queue_episode_searches(client, ids, on_progress=on_progress)
            current = store.snapshot().get("result")
            merged = dict(current) if isinstance(current, dict) else {}
            merged["search"] = queued
            store.set_done(
                f"Queued {queued['searches_queued']} EpisodeSearch command(s).",
                result=merged,
                phase="searched",
            )
            store.update(
                "searched",
                f"Queued {queued['searches_queued']} EpisodeSearch command(s).",
                percent=100,
                searches_queued=int(queued.get("searches_queued") or 0),
                missing_found=len(ids),
            )
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
