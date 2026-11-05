"""Idle trickle + owner backfill: one household-language subtitle file per title.

Every movie and episode gets a cached text file (English titles included) at
``DATA_DIR/subtitles/{rating_key}/{language}.srt`` via
:func:`projectionist.library.subtitle_cache.ensure_household_subtitle`. Plex text
tracks are copied first; OpenSubtitles runs only with an API key.

Two ways this task runs:

* **Scheduled idle cycle** — a small batch, upcoming Live lineup titles first,
  a pause between OpenSubtitles calls, and the catch-up gap while a backlog
  drains. Chat activity stops it between titles like every idle task.
* **Owner backfill** — Admin → Scheduled Tasks → *Backfill subtitles* starts a
  manual run (``force=True``), so chat does not stop it. It keeps going until
  nothing is left, the owner presses Stop, the server shuts down, or
  OpenSubtitles reports its quota (the run pauses until the next scheduled
  window). Progress lives in ``subtitle_state``; a restart resumes unfinished
  rows.

Not part of the TMDB date/plot gap and does not need a TMDB key.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

from projectionist.config_store import Settings
from projectionist.library import subtitle_state
from projectionist.library.db import Database
from projectionist.library.episode_investigate.capabilities import opensubtitles_api_key
from projectionist.library.subtitle_cache import ensure_household_subtitle, household_language
from projectionist.scheduler.autotune import resolve_batch_size
from projectionist.scheduler.engine import IdleScheduler, TaskDefinition
from projectionist.scheduler.run_log import emit_task_event

logger = logging.getLogger(__name__)

TASK_NAME = "subtitle_enrichment"
INTERVAL_SECONDS = 6 * 3600
CATCHUP_GAP_SECONDS = 300
DEFAULT_BATCH_SIZE = 10
#: Titles pulled per query while a backfill drains the whole library.
BACKFILL_CHUNK = 25
#: Pause between OpenSubtitles calls (free tier is a few requests per second).
REQUEST_PAUSE_SECONDS = 2.0
#: Without a reset time from OpenSubtitles, hold downloads this long after a quota hit.
QUOTA_PAUSE_SECONDS = 6 * 3600
LINEUP_HOURS = 12.0

BACKFILL_CONFIG_KEY = "subtitle_backfill"
OPENSUBTITLES_PAUSE_KEY = "subtitle_opensubtitles_paused_until"

STATE_RUNNING = "running"
STATE_STOPPING = "stopping"
STATE_STOPPED = "stopped"
STATE_PAUSED_QUOTA = "paused_quota"
STATE_DONE = "done"

# Test seam: the pause is patched to 0 so tests do not sleep.
_sleep = asyncio.sleep


def load_backfill(db: Database) -> Dict[str, Any]:
    raw = db.get_config(BACKFILL_CONFIG_KEY)
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_backfill(db: Database, data: Dict[str, Any]) -> Dict[str, Any]:
    payload = {**data, "updated_at": time.time()}
    db.set_config(BACKFILL_CONFIG_KEY, json.dumps(payload))
    return payload


def opensubtitles_paused_until(db: Database) -> float:
    try:
        return float(db.get_config(OPENSUBTITLES_PAUSE_KEY) or 0)
    except (TypeError, ValueError):
        return 0.0


def _pause_opensubtitles(db: Database, reset_at: Optional[float]) -> float:
    now = time.time()
    until = float(reset_at) if reset_at and float(reset_at) > now else now + QUOTA_PAUSE_SECONDS
    db.set_config(OPENSUBTITLES_PAUSE_KEY, str(until))
    return until


def upcoming_lineup_keys(settings: Any, db: Any = None) -> List[str]:
    """Plex keys for real airings in the next few hours (no flex/filler)."""
    if not getattr(getattr(settings, "features", None), "live_channels_enabled", False):
        return []
    try:
        from projectionist.live_channels.guide_cache import get_guide_snapshot

        snap = get_guide_snapshot(settings, hours=LINEUP_HOURS, cold_wait=0.0, db=db)
    except Exception as error:  # noqa: BLE001
        logger.debug("subtitle task: lineup read failed: %s", error)
        return []
    keys: List[str] = []
    for channel in snap.get("channels") or []:
        if not isinstance(channel, dict):
            continue
        programs = [channel.get("now")] + list(channel.get("programs") or [])
        for program in programs:
            if not isinstance(program, dict) or program.get("is_flex"):
                continue
            key = str(program.get("plex_rating_key") or "").strip()
            if key and key not in keys:
                keys.append(key)
    return keys


def backfill_status(db: Database, settings: Any, *, running: bool = False) -> Dict[str, Any]:
    language = household_language(settings)
    configured = bool(opensubtitles_api_key(settings))
    summary = subtitle_state.backlog_summary(db, language, opensubtitles_configured=configured)
    state = load_backfill(db)
    paused_until = opensubtitles_paused_until(db)
    return {
        "task": TASK_NAME,
        "state": str(state.get("state") or ""),
        "running": bool(running),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "processed": int(state.get("processed") or 0),
        "opensubtitles_configured": configured,
        "opensubtitles_paused_until": paused_until if paused_until > time.time() else None,
        **summary,
    }


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted", "processed": 0}

    backfill = load_backfill(db)
    now = time.time()
    paused_until = opensubtitles_paused_until(db)
    if backfill.get("state") == STATE_PAUSED_QUOTA and paused_until <= now:
        backfill = save_backfill(db, {**backfill, "state": STATE_RUNNING})
    backfill_active = backfill.get("state") == STATE_RUNNING

    configured = bool(opensubtitles_api_key(settings))
    if configured and paused_until > now:
        return {
            "status": "skipped",
            "reason": "opensubtitles_quota",
            "processed": 0,
            "paused_until": paused_until,
        }

    language = household_language(settings)
    batch_size = resolve_batch_size(db, TASK_NAME, DEFAULT_BATCH_SIZE)
    limit: Optional[int] = None if backfill_active else batch_size
    prefer = upcoming_lineup_keys(settings, db)

    processed = cached = none_found = failed = 0
    seen: set[str] = set()
    interrupted = stopped = quota = False
    os_called_last = False
    mode = "backfill" if backfill_active else "idle"
    emit_task_event(f"Saving subtitles ({mode})", mode=mode)

    while not (interrupted or stopped or quota):
        chunk = BACKFILL_CHUNK if limit is None else max(0, limit - processed)
        if chunk <= 0:
            break
        keys = subtitle_state.pending_keys(
            db,
            language,
            limit=chunk,
            opensubtitles_configured=configured,
            prefer=prefer,
            exclude=seen,
        )
        if not keys:
            break
        for key in keys:
            if should_stop():
                interrupted = True
                break
            if backfill_active and load_backfill(db).get("state") == STATE_STOPPING:
                stopped = True
                break
            if os_called_last:
                await _sleep(REQUEST_PAUSE_SECONDS)
                if should_stop():
                    interrupted = True
                    break
            seen.add(key)
            result = ensure_household_subtitle(settings, key, db=db)
            os_called_last = bool(result.get("opensubtitles_called"))
            processed += 1
            if result.get("track") is not None:
                cached += 1
            elif result.get("reason") in {"none_found", "no_opensubtitles_key"}:
                none_found += 1
            elif result.get("reason") != "quota":
                failed += 1
            if result.get("quota"):
                until = _pause_opensubtitles(db, result.get("quota_reset_at"))
                emit_task_event(
                    "OpenSubtitles download limit reached; pausing until it resets",
                    paused_until=until,
                )
                quota = True
                break
            if processed == 1 or processed % 10 == 0:
                emit_task_event(
                    f"Subtitles: {processed} checked, {cached} saved",
                    processed=processed,
                    cached=cached,
                )

    remaining = subtitle_state.count_pending(db, language, opensubtitles_configured=configured)
    if backfill_active:
        if stopped:
            next_state = STATE_STOPPED
        elif quota:
            next_state = STATE_PAUSED_QUOTA
        elif interrupted:
            next_state = STATE_RUNNING
        else:
            next_state = STATE_DONE if remaining == 0 else STATE_RUNNING
        record = {
            **load_backfill(db),
            "state": next_state,
            "processed": int(backfill.get("processed") or 0) + processed,
        }
        if next_state in {STATE_DONE, STATE_STOPPED}:
            record["finished_at"] = time.time()
        save_backfill(db, record)

    logger.info(
        "Subtitle enrichment (%s): processed=%s cached=%s none=%s failed=%s remaining=%s",
        mode,
        processed,
        cached,
        none_found,
        failed,
        remaining,
    )
    status = "interrupted" if interrupted else "completed"
    return {
        "status": status,
        "mode": mode,
        "processed": processed,
        "cached": cached,
        "none_found": none_found,
        "failed": failed,
        "quota_paused": quota,
        "stopped": stopped,
        "batch_size": batch_size,
        "has_more": remaining > 0,
        "remaining": remaining,
    }


# -- Owner backfill control ------------------------------------------------

_waiters: set[asyncio.Task[Any]] = set()


def _queued() -> bool:
    return any(not task.done() for task in _waiters)


async def _trigger_when_free(scheduler: IdleScheduler) -> None:
    while not scheduler._shutdown:
        busy = scheduler._busy_task_name()
        if busy is None:
            scheduler.trigger_task_background(TASK_NAME)
            return
        await asyncio.sleep(1.0)


def _schedule_trigger(scheduler: IdleScheduler) -> None:
    if _queued():
        return
    loop = asyncio.get_running_loop()
    task = loop.create_task(_trigger_when_free(scheduler), name="subtitle-backfill-wait")
    _waiters.add(task)
    task.add_done_callback(_waiters.discard)


def backfill_running(scheduler: IdleScheduler) -> bool:
    return scheduler._running_task == TASK_NAME or scheduler._pending_trigger == TASK_NAME or _queued()


def start_backfill(scheduler: IdleScheduler, *, requested_by: Any = None) -> Dict[str, Any]:
    """Start (or show) the one backfill. Call from the event loop."""
    db = scheduler._db
    settings = _settings_for(scheduler)
    current = load_backfill(db)
    if current.get("state") == STATE_RUNNING and backfill_running(scheduler):
        return {"status": "already_running", **backfill_status(db, settings, running=True)}
    save_backfill(
        db,
        {
            "state": STATE_RUNNING,
            "started_at": time.time(),
            "requested_by": requested_by,
            "processed": 0,
        },
    )
    if scheduler._busy_task_name() is None:
        scheduler.trigger_task_background(TASK_NAME)
    else:
        _schedule_trigger(scheduler)
    return {"status": "started", **backfill_status(db, settings, running=True)}


def stop_backfill(scheduler: IdleScheduler) -> Dict[str, Any]:
    db = scheduler._db
    settings = _settings_for(scheduler)
    current = load_backfill(db)
    for task in list(_waiters):
        task.cancel()
    running = scheduler._running_task == TASK_NAME
    if current.get("state") in {STATE_RUNNING, STATE_PAUSED_QUOTA}:
        save_backfill(
            db,
            {
                **current,
                "state": STATE_STOPPING if running else STATE_STOPPED,
                **({} if running else {"finished_at": time.time()}),
            },
        )
    return {"status": "stopping" if running else "stopped", **backfill_status(db, settings, running=running)}


def resume_backfill_if_active(scheduler: IdleScheduler) -> bool:
    """After a restart, pick an unfinished backfill back up from its DB rows."""
    state = load_backfill(scheduler._db).get("state")
    if state == STATE_STOPPING:
        save_backfill(scheduler._db, {**load_backfill(scheduler._db), "state": STATE_STOPPED})
        return False
    if state != STATE_RUNNING or backfill_running(scheduler):
        return False
    _schedule_trigger(scheduler)
    return True


def _settings_for(scheduler: IdleScheduler) -> Settings:
    from projectionist.config_store import load_merged_settings

    return load_merged_settings(scheduler._data_dir)


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name=TASK_NAME,
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            off_loop=True,
            description=(
                "Saves one household-language text subtitle file for every movie and "
                "episode, English titles included, so Play and Live captions start "
                "without a download. Copies a Plex text track when one exists; otherwise "
                "asks OpenSubtitles (only when an API key is set). About "
                f"{DEFAULT_BATCH_SIZE} titles per idle run, upcoming Live lineup first. "
                "Backfill subtitles runs the whole library on the server."
            ),
            items_per_cycle=DEFAULT_BATCH_SIZE,
            catchup_gap_seconds=CATCHUP_GAP_SECONDS,
            progress_scope="subtitle_backlog",
        )
    )
