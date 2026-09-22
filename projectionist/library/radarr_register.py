"""Background Register-in-Radarr job — Sonarr-missing snapshot + per-title queue."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Sequence

from projectionist.agent.tools import mark_in_radarr
from projectionist.config_store import (
    radarr_add_configuration_error,
    resolve_radarr_root_folder,
    validate_arr_root_folder,
)
from projectionist.connectors.arr_errors import (
    classify_radarr_add_error,
    classify_radarr_catalog,
    folder_path_from_arr_error,
    intended_movie_folder,
)
from projectionist.connectors.radarr import RadarrClient, index_radarr_movies, movie_occupying_folder
from projectionist.library.admin_execution import (
    finished_message,
    flatten_result,
    request_cancel,
    start_worker,
    store_for,
)
from projectionist.library.db import Database

logger = logging.getLogger(__name__)

KIND = "radarr_register"
IDLE_MESSAGE = "Ready when you are"


def list_owned_not_indexed(db: Database, *, limit: int = 50) -> Dict[str, Any]:
    lim = min(max(1, int(limit or 50)), 200)
    with db.connect() as conn:
        needs_rematch = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM library_items
            WHERE media_type = 'movie' AND COALESCE(in_radarr, 0) = 0
              AND (tmdb_id IS NULL OR tmdb_id = 0)
            """
        ).fetchone()["cnt"]
        total = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM library_items
            WHERE media_type = 'movie' AND COALESCE(in_radarr, 0) = 0
              AND tmdb_id IS NOT NULL AND tmdb_id != 0
            """
        ).fetchone()["cnt"]
        rows = conn.execute(
            """
            SELECT id, title, year, tmdb_id
            FROM library_items
            WHERE media_type = 'movie' AND COALESCE(in_radarr, 0) = 0
              AND tmdb_id IS NOT NULL AND tmdb_id != 0
            ORDER BY title COLLATE NOCASE
            LIMIT ?
            """,
            (lim,),
        ).fetchall()
    items = [_preview_row(row) for row in rows]
    return {
        "total": int(total),
        "needs_rematch": int(needs_rematch),
        "items": items,
    }


def _preview_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    year = row["year"]
    return {
        "id": int(row["id"]),
        "title": str(row["title"] or ""),
        "year": int(year) if year is not None else None,
        "tmdb_id": int(row["tmdb_id"]),
    }


def _candidate_rows(db: Database, *, limit: int) -> List[Dict[str, Any]]:
    return list_owned_not_indexed(db, limit=limit)["items"]


def _item_from_preview(row: Mapping[str, Any]) -> Dict[str, Any]:
    title = str(row.get("title") or "")
    year = row.get("year")
    label = f"{title} ({year})" if year else title or f"TMDB {row.get('tmdb_id')}"
    return {
        "id": int(row["id"]),
        "title": label,
        "year": year,
        "tmdb_id": int(row["tmdb_id"]),
        "status": "queued",
        "outcome": "",
        "error": "",
    }


def build_status() -> Dict[str, Any]:
    return flatten_result(store_for(KIND, idle_message=IDLE_MESSAGE).snapshot())


def cancel_register_job() -> Dict[str, Any]:
    return request_cancel(KIND)


def start_register_job(
    db: Database,
    settings: Any,
    *,
    limit: int = 25,
    dry_run: bool = False,
) -> Dict[str, Any]:
    lim = min(max(1, int(limit or 25)), 200)
    config_error = radarr_add_configuration_error(settings)
    if config_error:
        raise ValueError(config_error)
    client = RadarrClient(settings.radarr_url, settings.radarr_api_key)
    root_error = validate_arr_root_folder(
        "Radarr",
        resolve_radarr_root_folder(settings),
        client.root_folders(),
    )
    if root_error:
        raise ValueError(root_error)

    preview = _candidate_rows(db, limit=lim)
    items = [_item_from_preview(row) for row in preview]
    if dry_run:
        return {
            "dry_run": True,
            "limit": lim,
            "candidate_count": len(preview),
            "items": preview,
            "registered": 0,
            "already": 0,
            "failed": [],
            "accepted": True,
            "busy": False,
        }

    store = store_for(KIND, idle_message=IDLE_MESSAGE)
    job_id = store.begin(
        phase="queued",
        message="Queued Register in Radarr…",
        items=items,
    )
    if not job_id:
        snap = store.snapshot()
        snap["accepted"] = False
        snap["message"] = snap.get("message") or "A Radarr register job is already running."
        return snap

    def _run(job_store, cancel) -> Mapping[str, Any]:
        return _register_batch(job_store, cancel, db=db, settings=settings, client=client, rows=preview)

    if not start_worker(KIND, _run, name="radarr-register"):
        snap = store.snapshot()
        snap["accepted"] = False
        snap["message"] = "A Radarr register job is already running."
        return snap
    snap = flatten_result(store.snapshot())
    snap["accepted"] = True
    snap["job_id"] = job_id
    snap["dry_run"] = False
    snap["limit"] = lim
    snap["candidate_count"] = len(preview)
    return snap


def _register_batch(
    store,
    cancel,
    *,
    db: Database,
    settings: Any,
    client: RadarrClient,
    rows: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    registered = 0
    already = 0
    failed: List[Dict[str, Any]] = []
    cancelled = 0
    store.update("registering", "Registering titles in Radarr…")
    catalog: List[Any] = []
    try:
        catalog = list(client.movies())
    except Exception as error:  # noqa: BLE001 — still try per-title add
        logger.warning("Radarr register could not load movie catalog: %s", error)
    by_tmdb, by_path = index_radarr_movies(catalog)
    root_folder = resolve_radarr_root_folder(settings)
    for row in rows:
        item_id = int(row["id"])
        tmdb_id = int(row["tmdb_id"])
        title = str(row.get("title") or "")
        year = row.get("year")
        if cancel.is_set():
            store.set_item(item_id, "cancelled", outcome="cancelled")
            cancelled += 1
            continue
        store.set_item(item_id, "running", message=f"Registering {title}…")
        intended_path = intended_movie_folder(
            root_folder=root_folder,
            title=title,
            year=year,
        )
        classified = classify_radarr_catalog(
            intended_tmdb_id=tmdb_id,
            intended_title=title,
            intended_path=intended_path,
            by_tmdb=by_tmdb.get(tmdb_id),
            by_path=movie_occupying_folder(by_path, intended_path),
        )
        if classified is None:
            try:
                client.add_movie(
                    tmdb_id,
                    root_folder=root_folder,
                    quality_profile_id=settings.radarr_quality_profile_id,
                    search_for_movie=False,
                )
                mark_in_radarr(db, tmdb_id, title=title)
                registered += 1
                store.set_item(item_id, "completed", outcome="registered")
            except Exception as error:  # noqa: BLE001 — continue remaining titles
                occupant = movie_occupying_folder(
                    by_path,
                    folder_path_from_arr_error(error) or intended_path,
                )
                classified = classify_radarr_add_error(
                    error,
                    intended_tmdb_id=tmdb_id,
                    intended_title=title,
                    occupant=occupant,
                )
            else:
                continue
        if classified.kind == "already":
            mark_in_radarr(db, tmdb_id, title=title or classified.occupant_title)
            already += 1
            store.set_item(
                item_id,
                "skipped",
                outcome="already",
                message=classified.message,
            )
            continue
        if classified.kind == "path_conflict":
            failed.append(
                {
                    "tmdb_id": tmdb_id,
                    "title": title,
                    "error": classified.message,
                    "outcome": "path_conflict",
                }
            )
            store.set_item(
                item_id,
                "failed",
                error=classified.message[:400],
                outcome="path_conflict",
            )
            logger.warning(
                "Radarr register path conflict tmdb_id=%s title=%r occupant_tmdb=%s path=%s",
                tmdb_id,
                title,
                classified.occupant_tmdb_id,
                classified.folder_path,
            )
            continue
        failed.append({"tmdb_id": tmdb_id, "title": title, "error": classified.message})
        store.set_item(item_id, "failed", error=classified.message[:400], outcome="failed")
        logger.warning(
            "Radarr register-existing failed tmdb_id=%s title=%r: %s",
            tmdb_id,
            title,
            classified.message,
        )
    snap = store.snapshot()
    result = {
        "dry_run": False,
        "candidate_count": len(rows),
        "registered": registered,
        "already": already,
        "failed": failed,
        "cancelled": cancelled,
    }
    phase = "cancelled" if cancel.is_set() else "done"
    store.set_done(
        finished_message(snap.get("execution") or {}, noun="title", action="Registered"),
        result=result,
        phase=phase,
    )
    return result
