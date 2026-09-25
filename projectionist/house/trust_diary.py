"""Trust diary — rematch, Investigate, and job cards in one owner timeline."""

from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

from projectionist.library.db import Database

REMATCH_HREF = "/admin/libraries"
INVESTIGATE_HREF = "/admin/libraries"
JOBS_HREF = "/admin/tasks"
DIARY_LIMIT = 40

# Scheduler names that belong on the trust diary (identity / house care).
TRUST_TASK_NAMES = frozenset(
    {
        "purge_candidates",
        "health_metrics",
        "seasonal_rail",
        "enthusiast_nudge",
        "member_newsletter",
        "gift_queue",
        "watch_history_ingest",
    }
)


def _entry(
    *,
    kind: str,
    title: str,
    why: str,
    href: str,
    at: Optional[float] = None,
    status: Optional[str] = None,
    related_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "kind": kind,
        "title": title,
        "why": why,
        "href": href,
        "at": float(at) if at is not None else None,
        "status": status,
        "related_id": related_id,
    }


def _rematch_entries(db: Database) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    try:
        from projectionist.library.rematch import collect_repair_misses, load_skipped_ids
    except Exception:  # noqa: BLE001
        return entries

    skipped = load_skipped_ids(db)
    if skipped:
        entries.append(
            _entry(
                kind="rematch",
                title="Rematch studio is holding skips",
                why=(
                    f"{len(skipped)} title{'s' if len(skipped) != 1 else ''} "
                    "were set aside instead of forced. Open Rematch to review."
                ),
                href=REMATCH_HREF,
                related_id="rematch-skipped",
            )
        )

    register: Dict[str, Any] = {}
    sonarr: Dict[str, Any] = {}
    try:
        from projectionist.library.radarr_register import build_status as register_status

        snap = register_status()
        if isinstance(snap, dict):
            register = snap
    except Exception:  # noqa: BLE001
        register = {}
    try:
        from projectionist.library.sonarr_missing import build_status as sonarr_status

        snap = sonarr_status()
        if isinstance(snap, dict):
            sonarr = snap
    except Exception:  # noqa: BLE001
        sonarr = {}

    repairs = collect_repair_misses(
        register_items=register.get("items") if isinstance(register, dict) else None,
        sonarr_status=sonarr if sonarr else None,
    )
    for row in repairs[:8]:
        title = str(row.get("title") or "A title")
        message = str(row.get("message") or "Search or register missed.")
        entries.append(
            _entry(
                kind="rematch",
                title=f"Repair the miss — {title}",
                why=message,
                href=REMATCH_HREF,
                related_id=str(row.get("id") or title),
                status=str(row.get("kind") or "failed"),
            )
        )
    return entries


def _investigate_entries() -> List[Dict[str, Any]]:
    try:
        from projectionist.library.episode_investigate.job import build_apply_status, build_status
    except Exception:  # noqa: BLE001
        return []
    entries: List[Dict[str, Any]] = []
    for snap, label in (
        (build_status(), "Investigate"),
        (build_apply_status(), "Investigate apply"),
    ):
        if not isinstance(snap, dict):
            continue
        phase = str(snap.get("phase") or snap.get("status") or "").strip().lower()
        if not phase or phase in {"idle", "ready"}:
            continue
        message = str(snap.get("message") or snap.get("friendly") or "").strip()
        show = str(snap.get("show") or snap.get("title") or "").strip()
        title = f"{label} — {show}" if show else label
        why = message or "A job card is in flight. Open Libraries to read it."
        entries.append(
            _entry(
                kind="investigate",
                title=title,
                why=why,
                href=INVESTIGATE_HREF,
                status=phase,
                related_id=str(snap.get("id") or phase),
            )
        )
    return entries


def _job_card_entries(jobs: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for job in jobs or []:
        if not isinstance(job, Mapping):
            continue
        status = str(job.get("status") or "").strip().lower()
        name = str(job.get("name") or job.get("label") or job.get("kind") or "Job").strip()
        message = str(job.get("message") or job.get("friendly") or "").strip()
        if not name:
            continue
        entries.append(
            _entry(
                kind="job",
                title=name,
                why=message or "Open the job card for progress.",
                href=JOBS_HREF,
                at=job.get("updated_at") or job.get("started_at") or job.get("created_at"),
                status=status or None,
                related_id=str(job.get("id") or name),
            )
        )
    return entries


def _scheduler_entries(db: Database) -> List[Dict[str, Any]]:
    try:
        from projectionist.scheduler.run_history import list_all_task_runs
    except Exception:  # noqa: BLE001
        return []
    try:
        runs = list_all_task_runs(db, limit=24)
    except Exception:  # noqa: BLE001
        return []
    entries: List[Dict[str, Any]] = []
    for run in runs:
        name = str(run.get("name") or "").strip()
        if name not in TRUST_TASK_NAMES:
            continue
        status = str(run.get("status") or "").strip()
        finished = run.get("finished_at") or run.get("started_at")
        why = str(run.get("error") or run.get("message") or "").strip()
        if not why:
            why = f"{name.replace('_', ' ')} {status or 'ran'}."
        entries.append(
            _entry(
                kind="job",
                title=name.replace("_", " "),
                why=why,
                href=JOBS_HREF,
                at=finished,
                status=status or None,
                related_id=str(run.get("id") or name),
            )
        )
    return entries


def collect_trust_diary(
    db: Database,
    *,
    jobs: Optional[Iterable[Mapping[str, Any]]] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """One timeline that links rematch, Investigate, and job cards."""
    ts = time.time() if now is None else float(now)
    entries: List[Dict[str, Any]] = []
    entries.extend(_rematch_entries(db))
    entries.extend(_investigate_entries())
    if jobs is not None:
        entries.extend(_job_card_entries(list(jobs)))
    entries.extend(_scheduler_entries(db))
    entries.sort(key=lambda row: (row.get("at") is None, -(row.get("at") or 0)))
    trimmed = entries[:DIARY_LIMIT]
    return {
        "entries": trimmed,
        "total": len(trimmed),
        "empty_reason": None if trimmed else "No rematch, Investigate, or job cards yet.",
        "generated_at": ts,
    }
