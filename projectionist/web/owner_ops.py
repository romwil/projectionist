"""Owner operations on Admin: stewardship checklist, Monday pass, secrets card, needs attention.

Everything is computed from data already on the box (settings.json, SQLite,
cached library stats, scheduler state). No network probes, no phone-home.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from projectionist.envcompat import resolve_env
from projectionist.secrets_crypto import (
    NESTED_SECRET_PATHS,
    SETTINGS_SECRET_FIELDS,
    decrypt_secret,
    is_encrypted_secret,
)

logger = logging.getLogger(__name__)

SCOPE_SETUP = "setup"
SCOPE_MONDAY = "monday"
MONDAY_COMPLETE_ITEM = "complete"
MONDAY_REOPENED_ITEM = "reopened"
MONDAY_STEP_IDS = ("kinship", "issues", "purge", "catchup")
KINSHIP_TARGET_PCT = 50

WARM_EXPLORE_TASKS = (
    "metadata_enrichment",
    "summary_motifs",
    "plot_neighbors",
    "title_relations_refresh",
    "semantic_embeddings",
)

SERVICE_LABELS = {
    "llm": "Curator (LLM)",
    "plex": "Plex",
    "radarr": "Radarr",
    "sonarr": "Sonarr",
    "tmdb": "TMDB",
    "fanart": "Fanart",
    "tautulli": "Tautulli",
    "seerr": "Seerr",
}

_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
_warm_explore_jobs: set = set()


def current_period(now: Optional[float] = None) -> str:
    """ISO week on the server clock, e.g. ``2026-W44``."""
    stamp = time.localtime(time.time() if now is None else now)
    year, week, _ = time.strftime("%G %V %u", stamp).split()
    return f"{year}-W{week}"


# --- Secrets & connections (OPS-031) -------------------------------------------------


def unreadable_secret_fields(data_dir: Optional[Path]) -> List[str]:
    """Saved secrets in settings.json that are ciphertext the current key can't open."""
    if data_dir is None:
        return []
    path = Path(data_dir) / "settings.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(raw, Mapping):
        return []

    def _bad(value: Any) -> bool:
        return (
            isinstance(value, str)
            and is_encrypted_secret(value)
            and not decrypt_secret(value, data_dir=Path(data_dir)).strip()
        )

    names = [field for field in SETTINGS_SECRET_FIELDS if _bad(raw.get(field))]
    for parent, child in NESTED_SECRET_PATHS:
        section = raw.get(parent)
        if isinstance(section, Mapping) and _bad(section.get(child)):
            names.append(f"{parent}.{child}")
    return names


def _service_key_set(settings: Any, service: str) -> bool:
    if service == "seerr":
        return bool(str(getattr(settings.seerr, "api_key", "") or "").strip())
    if service == "plex":
        return bool(str(settings.plex_token or "").strip())
    if service == "llm":
        if str(settings.llm_api_key or "").strip():
            return True
        provider = str(getattr(settings, "llm_provider", "") or "").strip().lower()
        return provider == "ollama" and bool(str(getattr(settings, "llm_base_url", "") or "").strip())
    return bool(str(getattr(settings, f"{service}_api_key", "") or "").strip())


def _service_field(service: str) -> str:
    if service == "seerr":
        return "seerr.api_key"
    if service == "plex":
        return "plex_token"
    return f"{service}_api_key"


def build_secrets_health(db: Any, settings: Any, data_dir: Optional[Path]) -> Dict[str, Any]:
    from projectionist.web.setup import CERTIFIED_SERVICES, build_certifications_status

    unreadable = unreadable_secret_fields(data_dir)
    certs = build_certifications_status(db, data_dir).get("services", {})
    services = []
    for service in CERTIFIED_SERVICES:
        cert = certs.get(service) or {}
        certified = bool(cert.get("certified"))
        key_unreadable = _service_field(service) in unreadable
        key_set = _service_key_set(settings, service) and not key_unreadable
        if key_unreadable:
            state = "needs_key"
        elif certified and key_set:
            state = "connected"
        elif certified:
            state = "stale"
        elif key_set:
            state = "untested"
        else:
            state = "off"
        services.append(
            {
                "id": service,
                "label": SERVICE_LABELS.get(service, service.title()),
                "state": state,
                "certified": certified,
                "key_set": key_set,
                "key_unreadable": key_unreadable,
                "last_tested_at": cert.get("last_tested_at"),
            }
        )
    dedicated = bool((resolve_env("PROJECTIONIST_SECRETS_KEY") or "").strip())
    disagree = [s["id"] for s in services if s["state"] in ("stale", "untested")]
    if unreadable:
        status = "fail"
    elif disagree:
        status = "warn"
    else:
        status = "ok"
    return {
        "status": status,
        "key_source": "dedicated" if dedicated else "derived",
        "unreadable_fields": unreadable,
        "disagreements": disagree,
        "services": services,
    }


# --- Stewardship checklist (UX-036) -------------------------------------------------


def _backup_downloaded(db: Any) -> bool:
    from projectionist.web.backup import household_backup_log

    return bool(household_backup_log(db))


def _household_invited(db: Any) -> bool:
    try:
        if len(db.list_users(limit=2)) > 1:
            return True
        return bool(db.list_invites(limit=1))
    except Exception:  # noqa: BLE001
        return False


def _setup_definitions(db: Any, settings: Any, secrets: Mapping[str, Any]) -> List[Dict[str, Any]]:
    by_id = {s["id"]: s for s in secrets.get("services", [])}
    multi_user = bool(settings.features.multi_user_enabled)
    libraries_mapped = bool(
        str(settings.plex_movie_section or "").strip() or str(settings.plex_tv_section or "").strip()
    )
    synced = bool(db.get_sync_state("last_sync"))
    items = [
        {
            "id": "plex",
            "label": "Connect Plex",
            "detail": "Projectionist reads your library and plays titles through Plex.",
            "to": "/admin/connections",
            "optional": False,
            "verified": by_id.get("plex", {}).get("state") == "connected",
        },
        {
            "id": "libraries",
            "label": "Map and sync your libraries",
            "detail": "Pick the movie and TV libraries, then run the first sync.",
            "to": "/admin/libraries",
            "optional": False,
            "verified": libraries_mapped and synced,
        },
        {
            "id": "curator",
            "label": "Connect the curator",
            "detail": "Chat and written picks need an LLM. Browse and Play work without one.",
            "to": "/admin/connections",
            "optional": True,
            "verified": by_id.get("llm", {}).get("state") == "connected",
        },
        {
            "id": "secrets_key",
            "label": "Pin a dedicated secrets key",
            "detail": (
                "Set PROJECTIONIST_SECRETS_KEY so saved keys survive a restore. "
                "Keep it with your backups."
            ),
            "to": "/admin/overview#secrets-connections",
            "optional": False,
            "verified": secrets.get("key_source") == "dedicated"
            and not secrets.get("unreadable_fields"),
        },
        {
            "id": "invite",
            "label": "Invite someone in your household" if multi_user else "Turn on household accounts",
            "detail": (
                "Send a join link so they get their own picks and history."
                if multi_user
                else "Each person gets their own sign-in, picks, and history."
            ),
            "to": "/admin/access" if multi_user else "/admin/household",
            "optional": True,
            "verified": multi_user and _household_invited(db),
        },
        {
            "id": "backup",
            "label": "Download a household backup",
            "detail": "One zip with settings and the library database. Store it like a password vault.",
            "to": "/admin/overview#admin-backup-snapshot",
            "optional": False,
            "verified": _backup_downloaded(db),
        },
        {
            "id": "mail",
            "label": "Turn on mail",
            "detail": "Lets the weekly letter and invites reach people by email.",
            "to": "/admin/mail",
            "optional": True,
            "verified": bool(getattr(settings.mail, "enabled", False)),
        },
    ]
    return items


def build_setup_checklist(db: Any, settings: Any, secrets: Mapping[str, Any]) -> Dict[str, Any]:
    marks = db.list_checklist_marks(SCOPE_SETUP)
    items = []
    for item in _setup_definitions(db, settings, secrets):
        mark = marks.get(item["id"])
        if item["verified"]:
            status = "done"
        elif mark and mark["status"] == "skipped":
            status = "skipped"
        else:
            status = "pending"
        items.append(
            {
                **item,
                "status": status,
                "skipped_at": mark["updated_at"] if mark and mark["status"] == "skipped" else None,
            }
        )
    done = sum(1 for i in items if i["status"] == "done")
    return {"items": items, "done": done, "total": len(items)}


# --- Monday pass (OPS-030) ----------------------------------------------------------


def _kinship_pct(coverage: Mapping[str, Any]) -> Optional[int]:
    def _pct(value: Any) -> Optional[int]:
        try:
            num = float(value)
        except (TypeError, ValueError):
            return None
        return max(0, min(100, round(num)))

    opened_count = int(coverage.get("opened_title_count") or 0)
    opened = _pct(coverage.get("with_explainable_neighbors_opened_pct"))
    if opened_count > 0 and opened is not None:
        return opened
    explainable = _pct(coverage.get("with_explainable_neighbors_pct"))
    if explainable is not None:
        return explainable
    return _pct(coverage.get("with_overview_pct"))


def _monday_metrics(db: Any) -> Dict[str, Optional[int]]:
    from projectionist.library.derived_caches import get_knowledge_coverage
    from projectionist.scheduler.tasks.purge_candidates import read_cached_purge_candidates

    kinship: Optional[int] = None
    issues: Optional[int] = None
    purge: Optional[int] = None
    try:
        coverage = get_knowledge_coverage(db, cold_wait=0.0)
        if isinstance(coverage, Mapping):
            kinship = _kinship_pct(coverage)
    except Exception:  # noqa: BLE001
        logger.debug("Monday pass: coverage unavailable", exc_info=True)
    try:
        issues = len(db.list_media_issues(status="open", limit=500))
    except Exception:  # noqa: BLE001
        logger.debug("Monday pass: media issues unavailable", exc_info=True)
    try:
        cached = read_cached_purge_candidates(db)
        if isinstance(cached, Mapping):
            count = cached.get("count")
            purge = int(count) if isinstance(count, (int, float)) else len(cached.get("items") or [])
    except Exception:  # noqa: BLE001
        logger.debug("Monday pass: purge cache unavailable", exc_info=True)
    return {"kinship": kinship, "issues": issues, "purge": purge}


def build_monday_pass(db: Any, *, now: Optional[float] = None) -> Dict[str, Any]:
    period = current_period(now)
    marks = db.list_checklist_marks(SCOPE_MONDAY, period=period)
    metrics = _monday_metrics(db)
    kinship, issues, purge = metrics["kinship"], metrics["issues"], metrics["purge"]
    steps = [
        {
            "id": "kinship",
            "label": "Named kinship",
            "metric": None if kinship is None else f"{kinship}%",
            "detail": (
                "Share of opened titles whose More Like This names a real link."
                f" Done at {KINSHIP_TARGET_PCT}% or when you mark it reviewed."
            ),
            "to": "/admin/tasks",
            "auto_done": kinship is not None and kinship >= KINSHIP_TARGET_PCT,
        },
        {
            "id": "issues",
            "label": "Open issues",
            "metric": None if issues is None else str(issues),
            "detail": "Media problems members reported. Done when none are open.",
            "to": "/admin/health?tab=issues",
            "auto_done": issues == 0,
        },
        {
            "id": "purge",
            "label": "Purge pressure",
            "metric": None if purge is None else str(purge),
            "detail": "Titles nobody is watching that hold disk. Done when the buffer is clear.",
            "to": "/admin/health?tab=sync#storage-intelligence",
            "auto_done": purge == 0,
        },
        {
            "id": "catchup",
            "label": "Tasks catch-up",
            "metric": None,
            "detail": "Run catch-up to queue Warm Explore, or review the Tasks shortlist.",
            "to": "/admin/tasks",
            "auto_done": False,
        },
    ]
    for step in steps:
        mark = marks.get(step["id"])
        if step["auto_done"]:
            step["status"] = "done"
        elif mark and mark["status"] in ("done", "reviewed"):
            step["status"] = mark["status"]
        else:
            step["status"] = "pending"
        step["marked_at"] = mark["updated_at"] if mark else None
    complete = marks.get(MONDAY_COMPLETE_ITEM)
    reopened = marks.get(MONDAY_REOPENED_ITEM)
    if complete and reopened and reopened["updated_at"] >= complete["updated_at"]:
        complete = None
    last = db.last_checklist_mark(SCOPE_MONDAY, MONDAY_COMPLETE_ITEM)
    return {
        "period": period,
        "steps": steps,
        "ready": all(step["status"] != "pending" for step in steps),
        "completed_at": complete["updated_at"] if complete else None,
        "last_completed_at": last["updated_at"] if last else None,
        "last_completed_period": last["period"] if last else None,
    }


async def _run_warm_explore(scheduler: Any, names: Iterable[str]) -> None:
    for name in names:
        for _ in range(900):
            try:
                result = await scheduler.trigger_task(name)
            except Exception:  # noqa: BLE001
                logger.exception("Monday catch-up: %s crashed", name)
                break
            if result.get("status") != "busy":
                break
            await asyncio.sleep(2)


def queue_warm_explore(scheduler: Any) -> List[str]:
    """Queue Warm Explore tasks to run one after another in the background."""
    available = {str(state.get("name")) for state in scheduler.get_task_states()}
    names = [name for name in WARM_EXPLORE_TASKS if name in available]
    if names:
        job = asyncio.get_running_loop().create_task(
            _run_warm_explore(scheduler, names), name="monday-catch-up"
        )
        _warm_explore_jobs.add(job)
        job.add_done_callback(_warm_explore_jobs.discard)
    return names


# --- Failed tasks + Needs attention ---------------------------------------------------


def _task_label(name: str) -> str:
    text = str(name or "").replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else "Unknown task"


def failed_tasks(scheduler: Any) -> List[Dict[str, Any]]:
    if scheduler is None:
        return []
    try:
        states = scheduler.get_task_states()
    except Exception:  # noqa: BLE001
        return []
    failed = []
    for state in states:
        if not state.get("enabled"):
            continue
        status = str(state.get("last_status") or "")
        quarantined = bool((state.get("quarantine") or {}).get("is_quarantined"))
        if status.startswith("error") or quarantined:
            failed.append(
                {
                    "name": str(state.get("name")),
                    "quarantined": quarantined,
                    "last_run_at": state.get("last_run_at"),
                }
            )
    return failed


def build_needs_attention(
    *,
    secrets: Mapping[str, Any],
    setup: Mapping[str, Any],
    monday: Mapping[str, Any],
    failed: List[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    labels = {s["id"]: s["label"] for s in secrets.get("services", [])}
    unreadable_services = [s["label"] for s in secrets.get("services", []) if s.get("key_unreadable")]
    if secrets.get("unreadable_fields"):
        items.append(
            {
                "id": "secrets-unreadable",
                "kind": "secrets",
                "severity": "high",
                "title": "Saved keys can't be read",
                "detail": (
                    "The secrets key changed since these were saved"
                    + (f": {', '.join(unreadable_services)}" if unreadable_services else "")
                    + ". Re-enter each key and press Test, or restore the old key."
                ),
                "to": "/admin/connections",
            }
        )
    for service_id in secrets.get("disagreements", []):
        service = next((s for s in secrets.get("services", []) if s["id"] == service_id), {})
        stale = service.get("state") == "stale"
        items.append(
            {
                "id": f"secrets-{service_id}",
                "kind": "secrets",
                "severity": "medium",
                "title": f"{labels.get(service_id, service_id)} "
                + ("is marked connected but has no saved key" if stale else "has a key that was never tested"),
                "detail": "Open Connections and press Test so the badge matches the key.",
                "to": "/admin/connections",
            }
        )
    if failed:
        names = ", ".join(_task_label(t["name"]) for t in failed[:4])
        more = f" and {len(failed) - 4} more" if len(failed) > 4 else ""
        items.append(
            {
                "id": "tasks-failed",
                "kind": "tasks",
                "severity": "medium",
                "title": f"{len(failed)} task{'s' if len(failed) != 1 else ''} failed last run",
                "detail": f"{names}{more}.",
                "to": "/admin/tasks",
            }
        )
    for item in setup.get("items", []):
        if item["status"] == "pending" and not item["optional"]:
            items.append(
                {
                    "id": f"setup-{item['id']}",
                    "kind": "setup",
                    "severity": "low",
                    "title": item["label"],
                    "detail": item["detail"],
                    "to": item["to"],
                }
            )
    if not monday.get("completed_at"):
        pending = sum(1 for s in monday.get("steps", []) if s["status"] == "pending")
        items.append(
            {
                "id": "monday-pass",
                "kind": "monday",
                "severity": "low",
                "title": "This week's Monday pass isn't done",
                "detail": f"{pending} of 4 steps left." if pending else "All steps done. Mark the pass done.",
                "to": "/admin/overview#monday-pass",
            }
        )
    items.sort(key=lambda entry: _SEVERITY_ORDER.get(entry["severity"], 9))
    return items


def build_owner_ops_overview(
    db: Any, settings: Any, data_dir: Optional[Path], scheduler: Any
) -> Dict[str, Any]:
    secrets = build_secrets_health(db, settings, data_dir)
    setup = build_setup_checklist(db, settings, secrets)
    monday = build_monday_pass(db)
    failed = failed_tasks(scheduler)
    try:
        activity = db.local_event_counts(days=7)
    except Exception:  # noqa: BLE001
        activity = {"chat_turns": 0, "plays": 0, "plays_from_picks": 0}
    return {
        "setup": setup,
        "monday": monday,
        "secrets": secrets,
        "failed_tasks": failed,
        "needs_attention": build_needs_attention(
            secrets=secrets, setup=setup, monday=monday, failed=failed
        ),
        "activity_7d": activity,
    }
