"""Idle task: prune expired ephemeral Plex collections.

Only deletes collections CuratorX recorded in ``ephemeral_plex_collections``
(agent / movie-night shelves with the ``[CuratorX]`` prefix). Owner-named
evergreen collections without that marker are never touched.

Owner toggles (``features.ephemeral_collection_gc_enabled`` /
``features.ephemeral_collection_gc_dry_run``) control whether the task deletes
or only logs. Default interval: 6 hours.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 21600  # 6 hours
TASK_NAME = "collection_gc"


def _gc_enabled(settings: Settings) -> bool:
    flags = getattr(settings, "features", None)
    if flags is None:
        return True
    return bool(getattr(flags, "ephemeral_collection_gc_enabled", True))


def _gc_dry_run(settings: Settings) -> bool:
    flags = getattr(settings, "features", None)
    if flags is None:
        return False
    return bool(getattr(flags, "ephemeral_collection_gc_dry_run", False))


def prune_expired_ephemeral_collections(
    db: Database,
    settings: Settings,
    *,
    should_stop: Callable[[], bool] | None = None,
) -> Dict[str, Any]:
    """Delete (or dry-run log) expired ephemeral Plex collections.

    Never deletes a Plex collection that is not in ``ephemeral_plex_collections``.
    """
    if not _gc_enabled(settings):
        return {"status": "skipped", "reason": "ephemeral_collection_gc_enabled=false"}

    if not settings.plex_url or not settings.plex_token:
        return {"status": "skipped", "reason": "Plex not configured"}

    expired = db.list_expired_ephemeral_plex_collections()
    if not expired:
        return {"status": "completed", "expired": 0, "deleted": 0, "dry_run": _gc_dry_run(settings)}

    dry_run = _gc_dry_run(settings)
    deleted = 0
    errors: List[str] = []
    planned: List[str] = []

    if dry_run:
        for row in expired:
            if should_stop and should_stop():
                break
            title = str(row.get("title") or row.get("plex_rating_key"))
            planned.append(title)
            logger.info(
                "collection_gc dry-run: would delete ephemeral collection %s (%s)",
                row.get("plex_rating_key"),
                title,
            )
        return {
            "status": "completed",
            "expired": len(expired),
            "deleted": 0,
            "dry_run": True,
            "would_delete": planned,
        }

    from curatorx.connectors.plex import PlexClient
    from curatorx.connectors.plex_collections import delete_collection

    client = PlexClient(settings.plex_url, settings.plex_token)
    for row in expired:
        if should_stop and should_stop():
            return {
                "status": "interrupted",
                "expired": len(expired),
                "deleted": deleted,
                "errors": errors,
                "dry_run": False,
            }
        key = str(row.get("plex_rating_key") or "").strip()
        title = str(row.get("title") or key)
        try:
            delete_collection(client, key)
            db.delete_ephemeral_plex_collection_row(key)
            deleted += 1
            logger.info("collection_gc: deleted ephemeral collection %s (%s)", key, title)
        except Exception as exc:  # noqa: BLE001 — keep pruning other rows
            msg = f"{key}: {exc}"
            errors.append(msg)
            logger.warning("collection_gc: failed to delete %s: %s", key, exc)

    return {
        "status": "completed",
        "expired": len(expired),
        "deleted": deleted,
        "errors": errors,
        "dry_run": False,
    }


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    return prune_expired_ephemeral_collections(db, settings, should_stop=should_stop)


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name=TASK_NAME,
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Prunes expired CuratorX movie-night / agent Plex collections "
                "(``[CuratorX]`` prefix + tracked TTL). Never deletes evergreen "
                "collections without the ephemeral marker. Owner can disable or "
                "dry-run from Admin → Connections."
            ),
        )
    )
