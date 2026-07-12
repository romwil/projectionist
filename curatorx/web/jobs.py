"""Background job manager for library sync."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional

from curatorx.config_store import Settings, load_merged_settings
from curatorx.library.db import Database
from curatorx.library.query import refresh_library_overview_cache
from curatorx.library.sync import sync_library
from curatorx.logging_config import configure_logging
from curatorx.web.job_progress import format_job_progress, friendly_job_error
from curatorx.web.sync_schedule import should_run_scheduled_library_sync

logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "completed", "failed"]

INTERRUPTED_BY_RESTART = "Interrupted by server restart — start sync again"
RECENT_JOB_LIMIT = 50
JOBS_STATE_FILENAME = "jobs_state.json"
# Cap durable job state reads so a runaway/corrupt file cannot stall startup.
JOBS_STATE_MAX_BYTES = 5 * 1024 * 1024
# Give FastAPI time to finish binding HTTP before the first scheduled sync.
SCHEDULER_INITIAL_DELAY_SECONDS = 30
# How often the scheduler re-evaluates due syncs (hour-of-day windows need sub-day ticks).
SCHEDULER_POLL_SECONDS = 900

_manager: Optional["JobManager"] = None
_lock = threading.Lock()


@dataclass
class JobProgress:
    phase: str = "queued"
    current: int = 0
    total: int = 1
    message: str = ""

    def to_dict(self) -> Dict[str, object]:
        percent, message, label = format_job_progress(
            self.phase, self.current, self.total, self.message
        )
        return {
            "phase": self.phase,
            "label": label,
            "current": self.current,
            "total": self.total,
            "percent": percent,
            "message": message,
        }


@dataclass
class Job:
    id: str
    job_type: str
    status: JobStatus
    created_at: float
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    summary: Dict[str, object] = field(default_factory=dict)
    progress: JobProgress = field(default_factory=JobProgress)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["progress"] = self.progress.to_dict()
        return payload

    def to_persist_dict(self) -> Dict[str, object]:
        """Raw fields for durable storage (progress without recomputed percent)."""
        return {
            "id": self.id,
            "job_type": self.job_type,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "summary": self.summary,
            "progress": {
                "phase": self.progress.phase,
                "current": self.progress.current,
                "total": self.progress.total,
                "message": self.progress.message,
            },
            "error": self.error,
        }


def _job_from_persist_dict(raw: Dict[str, object]) -> Job:
    progress_raw = raw.get("progress") or {}
    if not isinstance(progress_raw, dict):
        progress_raw = {}
    status = str(raw.get("status") or "failed")
    if status not in ("queued", "running", "completed", "failed"):
        status = "failed"
    return Job(
        id=str(raw.get("id") or ""),
        job_type=str(raw.get("job_type") or "library_sync"),
        status=status,  # type: ignore[arg-type]
        created_at=float(raw.get("created_at") or 0),
        started_at=float(raw["started_at"]) if raw.get("started_at") is not None else None,
        finished_at=float(raw["finished_at"]) if raw.get("finished_at") is not None else None,
        summary=dict(raw["summary"]) if isinstance(raw.get("summary"), dict) else {},
        progress=JobProgress(
            phase=str(progress_raw.get("phase") or "queued"),
            current=int(progress_raw.get("current") or 0),
            total=max(int(progress_raw.get("total") or 1), 1),
            message=str(progress_raw.get("message") or ""),
        ),
        error=str(raw["error"]) if raw.get("error") is not None else None,
    )


def _resolve_db_path(data_dir: Path) -> Path:
    """Prefer curatorx.db; adopt legacy mediacurator.db once if present."""
    new_path = data_dir / "curatorx.db"
    legacy_path = data_dir / "mediacurator.db"
    if not new_path.exists() and legacy_path.exists():
        legacy_path.rename(new_path)
    return new_path


class JobManager:
    def __init__(self, data_dir: Path) -> None:
        configure_logging()
        self.data_dir = data_dir
        logger.info("JobManager: opening database…")
        self.db = Database(_resolve_db_path(data_dir))
        logger.info("JobManager: database ready")
        # Facet rebuild can take minutes on large libraries (per-row SQLite writes) —
        # never run it here; lifespan defers warm-up to a background thread.
        self._jobs_path = data_dir / JOBS_STATE_FILENAME
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()
        self._progress_log_at: Dict[str, float] = {}
        self._progress_log_phase: Dict[str, str] = {}
        logger.info("JobManager: loading durable jobs…")
        self._load_persisted_jobs()
        logger.info("JobManager initialized data_dir=%s jobs=%s", data_dir, len(self._jobs))

    def list_jobs(self) -> List[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def get_job(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def start_sync(self, settings: Settings) -> Job:
        job_id = uuid.uuid4().hex[:12]
        job = Job(id=job_id, job_type="library_sync", status="queued", created_at=time.time())
        with self._lock:
            self._jobs[job_id] = job
            self._persist_locked()
        logger.info("Library sync job queued job_id=%s", job_id)
        thread = threading.Thread(target=self._run_sync, args=(job_id, settings), daemon=True)
        thread.start()
        return job

    def _load_persisted_jobs(self) -> None:
        """Load recent jobs from disk; mark interrupted running/queued jobs as failed.

        Never raises — corrupt / oversized / unreadable state must not block startup.
        """
        try:
            raw_jobs = self._read_jobs_file()
            loaded: Dict[str, Job] = {}
            interrupted = 0
            for entry in raw_jobs:
                if not isinstance(entry, dict) or not entry.get("id"):
                    continue
                try:
                    job = _job_from_persist_dict(entry)
                except (TypeError, ValueError, KeyError) as error:
                    logger.warning("Skipping corrupt job entry: %s", error)
                    continue
                if not job.id:
                    continue
                if job.status in ("queued", "running"):
                    job.status = "failed"
                    job.finished_at = time.time()
                    job.error = INTERRUPTED_BY_RESTART
                    if job.progress.phase not in ("completed", "done"):
                        job.progress.message = INTERRUPTED_BY_RESTART
                    interrupted += 1
                loaded[job.id] = job

            # Keep newest N by created_at
            ordered = sorted(loaded.values(), key=lambda j: j.created_at, reverse=True)
            self._jobs = {job.id: job for job in ordered[:RECENT_JOB_LIMIT]}
            if interrupted:
                logger.warning(
                    "Marked %s interrupted job(s) as failed after restart",
                    interrupted,
                )
            if self._jobs or self._jobs_path.exists():
                self._persist_locked()
        except Exception as error:  # noqa: BLE001
            logger.exception("Durable jobs load failed; starting with empty job list: %s", error)
            self._jobs = {}

    def _read_jobs_file(self) -> List[object]:
        if not self._jobs_path.exists():
            return []
        try:
            size = self._jobs_path.stat().st_size
            if size > JOBS_STATE_MAX_BYTES:
                logger.warning(
                    "Skipping oversized jobs state %s (%s bytes > %s); starting empty",
                    self._jobs_path,
                    size,
                    JOBS_STATE_MAX_BYTES,
                )
                return []
            payload = json.loads(self._jobs_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("Could not load jobs state from %s: %s", self._jobs_path, error)
            return []
        if isinstance(payload, dict):
            jobs = payload.get("jobs")
            return list(jobs) if isinstance(jobs, list) else []
        if isinstance(payload, list):
            return payload
        return []

    def _persist_locked(self) -> None:
        """Write job state to DATA_DIR. Caller must hold self._lock (or init)."""
        ordered = sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)
        trimmed = ordered[:RECENT_JOB_LIMIT]
        self._jobs = {job.id: job for job in trimmed}
        payload = {
            "version": 1,
            "updated_at": time.time(),
            "jobs": [job.to_persist_dict() for job in trimmed],
        }
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = self._jobs_path.with_suffix(".tmp")
            tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            tmp_path.replace(self._jobs_path)
        except OSError as error:
            logger.warning("Could not persist jobs state to %s: %s", self._jobs_path, error)

    def _persist(self) -> None:
        with self._lock:
            self._persist_locked()

    def _update_progress(self, job_id: str, phase: str, current: int, total: int, message: str) -> None:
        percent, friendly, label = format_job_progress(phase, current, total, message)
        now = time.time()
        last_at = self._progress_log_at.get(job_id, 0.0)
        last_phase = self._progress_log_phase.get(job_id)
        phase_changed = phase != last_phase
        boundary = total > 0 and (current <= 0 or current >= total)
        due = (now - last_at) >= 3.0
        should_log = phase_changed or boundary or due

        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                # Persist the human-readable message so clients never see snake_case keys.
                job.progress = JobProgress(
                    phase=phase,
                    current=current,
                    total=total,
                    message=friendly,
                )
                # Throttle disk writes; always flush on phase changes / boundaries.
                if should_log:
                    self._persist_locked()

        if should_log:
            count_bit = f" — {current}/{total}" if total > 1 else ""
            logger.info(
                "Library sync: %s (%s%%)%s — %s",
                label.lower(),
                percent,
                count_bit,
                friendly,
            )
            self._progress_log_at[job_id] = now
            self._progress_log_phase[job_id] = phase

    def _run_sync(self, job_id: str, settings: Settings) -> None:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
            job.started_at = time.time()
            job.progress = JobProgress(phase="preparing", current=0, total=1, message="Connecting to Plex…")
            self._persist_locked()

        logger.info("Library sync started job_id=%s", job_id)

        def progress(phase: str, current: int, total: int, message: str) -> None:
            self._update_progress(job_id, phase, current, total, message)

        try:
            result = asyncio.run(sync_library(self.db, settings, progress=progress))
            refresh_library_overview_cache(self.db)
            elapsed = time.time() - (job.started_at or time.time())
            with self._lock:
                job.status = "completed"
                job.finished_at = time.time()
                job.summary = result
                job.progress = JobProgress(phase="completed", current=1, total=1, message="Done")
                self._persist_locked()
            self._progress_log_at.pop(job_id, None)
            self._progress_log_phase.pop(job_id, None)
            logger.info(
                "Library sync completed job_id=%s elapsed=%.1fs items=%s movies=%s shows=%s",
                job_id,
                elapsed,
                result.get("items_synced"),
                result.get("movies"),
                result.get("shows"),
            )
        except Exception as error:  # noqa: BLE001
            logger.exception("Library sync failed job_id=%s: %s", job_id, error)
            self._progress_log_at.pop(job_id, None)
            self._progress_log_phase.pop(job_id, None)
            with self._lock:
                job.status = "failed"
                job.finished_at = time.time()
                job.error = friendly_job_error(error)
                job.summary = {"traceback": traceback.format_exc()}
                self._persist_locked()


class SyncScheduler:
    """Background scheduler for periodic library re-sync."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="library-sync-scheduler")
        self._thread.start()
        logger.info("Library sync scheduler started")

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        # Defer first tick so HTTP can come up before any optional Plex sync.
        self._stop.wait(timeout=SCHEDULER_INITIAL_DELAY_SECONDS)
        while not self._stop.is_set():
            try:
                settings = load_merged_settings(self.data_dir)
                if settings.plex_url and settings.plex_token:
                    interval_hours = max(1, int(settings.library_sync_interval_hours))
                    preferred_hour = settings.library_sync_hour
                    last_ts: Optional[float] = None
                    last_raw = get_job_manager().db.get_sync_state("last_sync")
                    if last_raw:
                        try:
                            last_data = json.loads(last_raw)
                            last_ts = float(last_data.get("timestamp") or 0)
                        except (json.JSONDecodeError, TypeError, ValueError):
                            last_ts = None
                    should_run = should_run_scheduled_library_sync(
                        now=datetime.now().astimezone(),
                        last_sync_ts=last_ts,
                        interval_hours=interval_hours,
                        preferred_hour=preferred_hour,
                    )
                    running = any(j.status in ("queued", "running") for j in get_job_manager().list_jobs())
                    if should_run and not running:
                        logger.info(
                            "Scheduler triggering library sync interval_hours=%s preferred_hour=%s",
                            interval_hours,
                            preferred_hour,
                        )
                        get_job_manager().start_sync(settings)
            except Exception as error:  # noqa: BLE001
                logger.exception("Sync scheduler loop error: %s", error)
            self._stop.wait(timeout=SCHEDULER_POLL_SECONDS)


_scheduler: Optional[SyncScheduler] = None


def get_sync_scheduler() -> SyncScheduler:
    global _scheduler
    with _lock:
        if _scheduler is None:
            data_dir = Path(os.environ.get("DATA_DIR", "/config"))
            _scheduler = SyncScheduler(data_dir)
        return _scheduler


def get_job_manager() -> JobManager:
    global _manager
    with _lock:
        if _manager is None:
            data_dir = Path(os.environ.get("DATA_DIR", "/config"))
            _manager = JobManager(data_dir)
        return _manager


def reset_job_manager_for_tests() -> None:
    """Clear the singleton JobManager (unit tests only)."""
    global _manager
    with _lock:
        _manager = None
