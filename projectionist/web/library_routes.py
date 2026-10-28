"""Library HTTP routes: sync, stats, feeds, query, TV, saved pages."""

from __future__ import annotations

import csv
import io
import json
import logging
import uuid
from datetime import date
from typing import Any, Callable, Dict, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from projectionist.agent.providers import get_chat_provider
from projectionist.config_store import Settings
from projectionist.connectors.plex import PlexClient, cached_plex_friendly_name
from projectionist.library.derived_caches import (
    get_knowledge_coverage as get_cached_knowledge_coverage,
    get_library_health as get_cached_library_health,
)
from projectionist.library.episodes import (
    get_episode_detail,
    query_episodes,
    query_show_seasons,
    summarize_tv_progress,
)
from projectionist.library.explore_hub import get_explore_hub
from projectionist.library.external_search import (
    ERROR_NOT_CONFIGURED,
    external_tmdb_search,
    normalize_external_media_type,
)
from projectionist.library.facets import library_facet_catalog
from projectionist.library.feeds import (
    EXPLORE_RAIL_LIMIT,
    feed_afterglow,
    feed_continue_watching,
    feed_director_spotlight,
    feed_genre_spotlight,
    feed_on_this_day,
    feed_recent_releases,
    feed_recently_added,
    feed_recently_added_episodes,
    feed_revisit_these,
    feed_seasonal_spotlight,
    feed_tonight_table,
    feed_unfinished,
    neighbors_payload,
)
from projectionist.library.query import (
    aggregate_library,
    filters_from_mapping,
    library_overview,
    query_library,
    query_library_async,
)
from projectionist.library.watch_state import set_library_item_watched, sync_watched_to_plex
from projectionist.scheduler.tasks.purge_candidates import (
    BUFFER_TARGET,
    DEFAULT_LIMIT as PURGE_BUFFER_DEFAULT_LIMIT,
    drop_cached_purge_keys,
    enrich_cached_purge_items,
    maybe_top_up_purge_candidates,
    read_cached_purge_candidates,
    recompute_purge_candidates,
)
from projectionist.web.auth import get_current_user_dep, require_role
from projectionist.web.jobs import get_job_manager
from projectionist.web.library_privacy import (
    normalize_saved_library_content,
    sanitize_library_payload,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["library"])

_db_factory: Optional[Callable[[], Any]] = None
_settings_factory: Optional[Callable[[], Settings]] = None
_safe_error_detail_fn: Optional[Callable[..., str]] = None


def _db():
    if _db_factory is None:
        raise RuntimeError("library routes not registered")
    return _db_factory()


def _settings() -> Settings:
    if _settings_factory is None:
        raise RuntimeError("library routes not registered")
    return _settings_factory()


def _safe_error_detail(error: Exception, context: str = "") -> str:
    if _safe_error_detail_fn is None:
        raise RuntimeError("library routes not registered")
    return _safe_error_detail_fn(error, context)


def _scoped_user_id(user) -> Optional[str]:
    """Return user.id when multi-user partitioning is active, else None."""
    if _settings().features.multi_user_enabled:
        return user.id
    return None


def _maybe_emit_explore_miss(payload: Any) -> None:
    """Fire-and-forget telemetry when Explore feeds or neighbors return empty."""
    if not isinstance(payload, dict):
        return
    if payload.get("items"):
        return
    note = payload.get("note")
    if not note:
        return
    feed_id = str(payload.get("feed") or "")
    if not feed_id and "item_id" in payload:
        feed_id = f"neighbors:{payload.get('mode', 'similar')}"
    if not feed_id:
        feed_id = str(payload.get("scope_id") or "explore")
    try:
        from projectionist.telemetry.explore import schedule_explore_miss

        schedule_explore_miss(
            feed_id=feed_id,
            entity_key=feed_id,
            context_source="explore_feed",
            extra={"note": str(note)[:200]},
        )
    except Exception:  # noqa: BLE001 — never break feed responses
        pass


def _sanitize_library_payload(payload: Any, user, *, attach_watch: bool = True) -> Any:
    settings = _settings()
    if attach_watch:
        from projectionist.watch_tracker.store import attach_user_watch_summaries

        tracker_adopted = attach_user_watch_summaries(
            _db(),
            payload,
            user_id=str(getattr(user, "id", "") or ""),
        )
    else:
        tracker_adopted = payload
    sanitized = sanitize_library_payload(tracker_adopted, settings=settings, user=user)
    from projectionist.youth.apply import filter_payload_for_youth

    filtered = filter_payload_for_youth(sanitized, user=user, settings=settings)
    _maybe_emit_explore_miss(filtered)
    return filtered


def _apply_youth_filters(filters, user):
    from projectionist.youth.apply import apply_youth_gate_to_filters

    return apply_youth_gate_to_filters(filters, user=user, settings=_settings())

class LibraryItemWatchedPayload(BaseModel):
    rating_key: str = Field(min_length=1, max_length=64)
    watched: bool = True


class LibraryItemSubtitlesDownloadPayload(BaseModel):
    language: str = ""
    confirm: bool = False


class SavedLibrarySharePayload(BaseModel):
    to_user_ids: List[str] = Field(min_length=1)
    message: Optional[str] = Field(default=None, max_length=280)


class SavedLibraryPagePayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    source_session_id: Optional[str] = Field(default=None, max_length=128)
    source_message_id: Optional[str] = Field(default=None, max_length=128)
    content: Dict[str, Any]
    summary: Optional[str] = Field(default=None, max_length=800)
    user_title: Optional[str] = Field(default=None, min_length=1, max_length=160)


class MarkBadMediaPayload(BaseModel):
    confirm: bool = False
    rating_key: Optional[str] = None
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    media_type: Optional[str] = None
    episode_rating_key: Optional[str] = None
    season_number: Optional[int] = None
    episode_number: Optional[int] = None
    note: str = Field(default="", max_length=2000)


class TvRemovePayload(BaseModel):
    scope: str = Field(min_length=1)
    show_id: Optional[int] = None
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    rating_key: Optional[str] = None
    season_number: Optional[int] = None
    episode_rating_key: Optional[str] = None


_EXPORT_COLUMNS = (
    "title", "year", "media_type", "genres", "runtime_minutes", "vote_average",
    "watch_state", "view_count", "added_at", "last_viewed_at", "tmdb_id", "tvdb_id",
)


@router.post("/api/library/sync")
def start_library_sync(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    job = get_job_manager().start_sync(_settings())
    logger.info("Library sync queued job_id=%s", job.id)
    return job.to_dict()


@router.get("/api/library/stats")
def library_stats(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    db = _db()
    counts = db.library_counts()
    settings = _settings()
    plex_server_name = ""
    if settings.plex_url and settings.plex_token:
        plex_server_name = cached_plex_friendly_name(settings.plex_url, settings.plex_token, timeout=5)
    payload = {
        "total": int(counts.get("items") or 0),
        "movies": int(counts.get("movies") or 0),
        "shows": int(counts.get("shows") or 0),
        "last_sync": db.get_sync_state("last_sync"),
        "plex_server_name": plex_server_name or None,
        # Phase A data surface for Admin/Explore knowledge-depth UI (Phase D).
        # SWR: coverage scans the whole library — never on the app-shell request path.
        "knowledge_coverage": get_cached_knowledge_coverage(db),
    }
    return _sanitize_library_payload(payload, user)


@router.get("/api/library/knowledge-coverage")
def library_knowledge_coverage(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    """Dedicated coverage stats for Admin / Explore knowledge-depth panels."""
    return _sanitize_library_payload(get_cached_knowledge_coverage(_db()), user)


@router.get("/api/library/kinship-miss")
def library_kinship_miss(
    limit: int = 50,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Titles someone opened to an empty More Like This / Related / bridge shelf.

    Read-only demand list. Does not auto-repair or promote into staged
    augmentations.
    """
    from projectionist.telemetry.kinship_miss import list_kinship_miss

    capped = max(1, min(int(limit or 50), 200))
    return _sanitize_library_payload(
        list_kinship_miss(_db(), limit=capped),
        user,
        attach_watch=False,
    )


@router.get("/api/library/health")
def library_health(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    return _sanitize_library_payload(get_cached_library_health(_db()), user)


@router.get("/api/library/purge-candidates")
def library_purge_candidates(
    limit: int = 12,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Return cached purge candidates for a fast dashboard load.

    When the cache is empty, returns an empty payload with ``stale=true``
    instead of recomputing synchronously (use POST .../refresh for that).
    """
    del limit  # limit applied at cache-build time; kept for API compatibility
    cached = read_cached_purge_candidates(_db())
    if cached is None:
        payload = {
            "count": 0,
            "items": [],
            "generated_at": None,
            "page_size": 20,
            "buffer_target": BUFFER_TARGET,
            "stale": True,
            "cached": False,
            "refilling": False,
        }
    else:
        payload = cached
    return _sanitize_library_payload(payload, user)


@router.post("/api/library/purge-candidates/refresh")
def refresh_library_purge_candidates(
    limit: int = PURGE_BUFFER_DEFAULT_LIMIT,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Force-recompute purge candidates and refresh the cache."""
    payload = recompute_purge_candidates(
        _db(),
        _settings(),
        limit=min(max(1, limit), BUFFER_TARGET),
    )
    return _sanitize_library_payload(payload, user)


@router.post("/api/library/purge-candidates/enrich")
def enrich_library_purge_candidates(
    payload: Dict[str, Any],
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Refresh size / last-watched for visible purge rows (SQLite + *arr when set)."""
    keys = _normalize_rating_keys(payload)
    cached = read_cached_purge_candidates(_db()) or {"items": []}
    by_key = {
        str(item.get("rating_key") or ""): item
        for item in (cached.get("items") or [])
        if str(item.get("rating_key") or "").strip()
    }
    selected = [by_key[key] for key in keys if key in by_key]
    # Also allow enriching keys not currently cached (title drawer / stale page).
    missing = [key for key in keys if key not in by_key]
    for key in missing:
        row = _db().library_item_by_rating_key(key)
        if row is None:
            continue
        selected.append(
            {
                "rating_key": key,
                "media_type": row["media_type"],
                "title": row["title"],
                "year": row["year"],
                "tmdb_id": row["tmdb_id"],
                "tvdb_id": row["tvdb_id"],
                "file_size": int(row["file_size"] or 0),
            }
        )
    enriched = enrich_cached_purge_items(_db(), _settings(), selected)
    return _sanitize_library_payload({"items": enriched, "count": len(enriched)}, user)


def _queue_purge_buffer_top_up(background_tasks: BackgroundTasks) -> None:
    """After purge/keep, refill the far end of the 5× candidate buffer."""

    def _run() -> None:
        try:
            maybe_top_up_purge_candidates(_db(), _settings())
        except Exception:  # noqa: BLE001 — background refill must not break the request
            logger.exception("Purge buffer top-up failed")

    background_tasks.add_task(_run)


def _normalize_rating_keys(payload: Dict[str, Any]) -> List[str]:
    rating_keys = payload.get("rating_keys", [])
    if not rating_keys or not isinstance(rating_keys, list):
        raise HTTPException(status_code=400, detail="rating_keys must be a non-empty list")
    keys = [str(key).strip() for key in rating_keys if str(key).strip()]
    if not keys:
        raise HTTPException(status_code=400, detail="rating_keys must be a non-empty list")
    return keys


def _pull_removal_event(iterator: Any) -> Any:
    try:
        return next(iterator)
    except StopIteration:
        return None


def _dump_removal_event(event: Dict[str, Any]) -> str:
    return json.dumps(event, separators=(",", ":"), default=str) + "\n"


async def _iter_removal_ndjson(request: Request, run: Any):
    """Yield NDJSON progress. Disconnect stops titles that have not started."""
    import anyio
    from functools import partial

    iterator = run.events()
    sent_complete = False
    try:
        while True:
            if await request.is_disconnected():
                break
            event = await anyio.to_thread.run_sync(partial(_pull_removal_event, iterator))
            if event is None:
                break
            if event.get("type") == "complete":
                sent_complete = True
            yield _dump_removal_event(event)
    finally:
        iterator.close()
    if not sent_complete and isinstance(getattr(run, "result", None), dict):
        disconnected = await request.is_disconnected()
        if not disconnected:
            yield _dump_removal_event({"type": "complete", "result": run.result})


def _removal_stream_response(request: Request, run: Any) -> StreamingResponse:
    return StreamingResponse(
        _iter_removal_ndjson(request, run),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _record_purge_index_undo(db: Any, user: Any, snapshot: Dict[str, Any], deleted: int) -> Optional[str]:
    items = list(snapshot.get("items") or [])
    if deleted <= 0 or not items:
        return None
    titles = [str(item.get("title") or "") for item in items if item.get("title")]
    preview = ", ".join(titles[:3])
    if len(titles) > 3:
        preview += f" +{len(titles) - 3} more"
    summary = f"Deleted {deleted} purge candidate{'s' if deleted != 1 else ''} (index only)"
    if preview:
        summary += f": {preview}"
    action = db.record_grooming_action(
        action_id=str(uuid.uuid4()),
        action_type="purge_delete",
        actor_user_id=getattr(user, "id", None),
        summary=summary,
        item_count=deleted,
        snapshot=snapshot,
    )
    return action["id"]


def _snapshot_for_deleted_keys(snapshot: Dict[str, Any], deleted_keys: List[str]) -> Dict[str, Any]:
    wanted = {str(key) for key in deleted_keys}
    items = [
        item
        for item in (snapshot.get("items") or [])
        if str(item.get("rating_key") or "") in wanted
    ]
    item_ids = {item.get("id") for item in items}
    episodes = [
        episode
        for episode in (snapshot.get("episodes") or [])
        if episode.get("show_item_id") in item_ids
    ]
    return {"items": items, "episodes": episodes}


@router.post("/api/library/items/delete")
async def delete_library_items(
    payload: Dict[str, Any],
    request: Request,
    user=Depends(require_role("owner")),
):
    """Owner-only library delete.

    ``mode=index`` (default): remove Projectionist index rows only. Does not
    delete Plex files; titles still in Plex may return on the next sync.

    ``mode=full``: delete via Radarr/Sonarr (files + import exclusion), remove
    Plex metadata when configured, then drop the Projectionist index row.
    A title that is not in Radarr/Sonarr is deleted from disk via Plex when
    configured (or via a file path this app can already see). A true no-op
    leaves the index and is listed under ``errors``. Other per-title failures
    also leave the index intact.
    """
    from projectionist.library.full_remove import (
        full_remove_library_items,
        normalize_library_delete_mode,
    )

    keys = _normalize_rating_keys(payload)
    try:
        mode = normalize_library_delete_mode(payload.get("mode"))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    db = _db()
    settings = _settings()
    del user
    if payload.get("stream"):
        from projectionist.library.full_remove import RemovalProgress
        from projectionist.library.removal_cancel import arm_removal_cancel, clear_removal_cancel

        run_id = str(payload.get("run_id") or "").strip()
        cancel_event = arm_removal_cancel(run_id) if run_id else None

        def _clear(run: Any) -> None:
            del run
            if run_id:
                clear_removal_cancel(run_id)

        run = RemovalProgress(
            db,
            settings,
            keys,
            mode=mode,
            cancel_event=cancel_event,
            on_before_complete=_clear,
        )
        return _removal_stream_response(request, run)

    if mode == "full":
        return full_remove_library_items(db, settings, keys)

    deleted = db.delete_library_items_by_rating_keys(keys)
    drop_cached_purge_keys(db, keys)
    return {"mode": "index", "deleted": deleted}


@router.post("/api/library/items/delete/cancel")
def cancel_library_item_delete(
    payload: Dict[str, Any],
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Stop a streamed removal before titles that have not started.

    Titles already removed stay removed. The in-flight title finishes.
    """
    del user
    from projectionist.library.removal_cancel import request_removal_cancel

    run_id = str(payload.get("run_id") or "").strip()
    if not run_id:
        raise HTTPException(status_code=400, detail="run_id is required")
    request_removal_cancel(run_id)
    return {"ok": True, "run_id": run_id}


@router.post("/api/library/items/mark-bad-media")
def mark_bad_media_endpoint(
    payload: MarkBadMediaPayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Owner-only: ask Radarr/Sonarr to delete bad file(s) and search for replacements.

    Does **not** add import or acquisition exclusions — the title stays wanted.
    """
    del user
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Marking bad media requires confirm=true",
        )
    from projectionist.library.bad_media import BadMediaError, mark_bad_media

    try:
        return mark_bad_media(
            _db(),
            _settings(),
            rating_key=payload.rating_key,
            tmdb_id=payload.tmdb_id,
            tvdb_id=payload.tvdb_id,
            media_type=payload.media_type,
            episode_rating_key=payload.episode_rating_key,
            season_number=payload.season_number,
            episode_number=payload.episode_number,
            note=payload.note,
        )
    except BadMediaError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(error, "Could not mark media for replacement"),
        ) from error


@router.post("/api/library/items/watched")
def set_library_item_watched_endpoint(
    payload: LibraryItemWatchedPayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Mark an in-library title watched/unwatched locally and on Plex when configured.

    Plex uses the caller's Sign-in-with-Plex token when present; otherwise the
    server ``plex_token`` (admin/account watched state — household-wide).
    """
    settings = _settings()
    db = _db()
    try:
        item = set_library_item_watched(
            db,
            payload.rating_key,
            watched=payload.watched,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=404 if "not found" in str(error).lower() else 400,
            detail=_safe_error_detail(error, "Could not update watched state"),
        ) from error

    plex = sync_watched_to_plex(
        db,
        settings,
        payload.rating_key,
        watched=payload.watched,
        user_id=_scoped_user_id(user) or user.id,
    )
    # Same in-process note playback uses so Continue Watching drops a finished
    # episode before the next Plex on-deck snapshot arrives.
    from projectionist.library.continue_watching_progress import note_playback_progress

    note_playback_progress(
        db,
        payload.rating_key,
        0,
        finished=bool(payload.watched),
    )
    return {**item, **plex}


@router.get("/api/library/items/{rating_key}/subtitles")
def library_item_subtitles_endpoint(
    rating_key: str,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """List Plex-attached subtitle streams for a movie or episode (soft-fail empty)."""
    del user
    from projectionist.library.subtitles import list_item_subtitles

    return list_item_subtitles(_settings(), rating_key)


@router.post("/api/library/items/{rating_key}/subtitles/download")
def library_item_subtitles_download_endpoint(
    rating_key: str,
    payload: LibraryItemSubtitlesDownloadPayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Ask Plex to download preferred-language subtitles (confirm-before-fleet)."""
    if not payload.confirm:
        raise HTTPException(
            status_code=400,
            detail="Asking Plex for subtitles requires confirm=true",
        )
    settings = _settings()
    from projectionist.library.subtitles import download_preferred_subtitles

    prefer_sdh = bool(getattr(user, "is_youth", False))
    return download_preferred_subtitles(
        settings,
        rating_key,
        language=str(payload.language or ""),
        prefer_sdh=prefer_sdh,
    )


@router.get("/api/library/items/{rating_key}/subtitles/{stream_id}/file")
def library_item_subtitle_file_endpoint(
    rating_key: str,
    stream_id: str,
    user=Depends(get_current_user_dep),
) -> Response:
    """Proxy a Plex subtitle track as WebVTT (sidecar or embedded text) for the player.

    Plex tokens stay server-side; the browser only sees this authenticated route.
    """
    del user
    from projectionist.library.subtitles import (
        fetch_subtitle_vtt,
        list_item_subtitles,
        plex_client_from_settings,
    )

    settings = _settings()
    listed = list_item_subtitles(settings, rating_key)
    wanted = str(stream_id or "").strip()
    match = next(
        (
            row
            for row in (listed.get("streams") or [])
            if isinstance(row, dict) and str(row.get("id") or "") == wanted
        ),
        None,
    )
    if not match:
        raise HTTPException(status_code=404, detail="Subtitle track not found")
    if not match.get("proxy_url"):
        raise HTTPException(
            status_code=415,
            detail=str(match.get("unavailable_reason") or "This subtitle track can’t be rendered as text"),
        )
    client = plex_client_from_settings(settings)
    if client is None:
        raise HTTPException(status_code=503, detail="Plex isn’t connected")
    try:
        text = fetch_subtitle_vtt(client, match)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail="This subtitle track isn’t available as text.",
        ) from error
    return Response(
        content=text.encode("utf-8"),
        media_type="text/vtt; charset=utf-8",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.post("/api/library/purge-candidates/delete")
async def delete_purge_candidates(
    payload: Dict[str, Any],
    request: Request,
    background_tasks: BackgroundTasks,
    user=Depends(require_role("owner")),
):
    """Owner-only purge-candidate delete.

    Default ``mode=full`` (missing/blank): delete via Radarr/Sonarr (files +
    import exclusion), remove Plex metadata when configured, then drop the
    Projectionist index row. Full removes are not undoable.

    ``mode=index``: remove Projectionist index rows only and record a grooming
    action so the owner can restore those rows. Does not delete disk files.
    """
    from projectionist.library.full_remove import (
        full_remove_library_items,
        normalize_library_delete_mode,
    )

    keys = _normalize_rating_keys(payload)
    raw_mode = payload.get("mode")
    if raw_mode is None or str(raw_mode).strip() == "":
        mode = "full"
    else:
        try:
            mode = normalize_library_delete_mode(raw_mode)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    db = _db()
    settings = _settings()
    if payload.get("stream"):
        from projectionist.library.full_remove import RemovalProgress
        from projectionist.library.removal_cancel import arm_removal_cancel, clear_removal_cancel

        run_id = str(payload.get("run_id") or "").strip()
        cancel_event = arm_removal_cancel(run_id) if run_id else None
        snapshot = db.snapshot_library_items_by_rating_keys(keys) if mode == "index" else None

        def _before_complete(run: Any) -> None:
            if run_id:
                clear_removal_cancel(run_id)
            if mode == "index":
                partial = _snapshot_for_deleted_keys(snapshot or {}, run.deleted_keys)
                action_id = _record_purge_index_undo(db, user, partial, len(run.deleted_keys))
                run.result = {
                    **(run.result or {}),
                    "action_id": action_id,
                    "undoable": action_id is not None,
                }
            else:
                run.result = {**(run.result or {}), "action_id": None, "undoable": False}

        run = RemovalProgress(
            db,
            settings,
            keys,
            mode=mode,
            cancel_event=cancel_event,
            on_before_complete=_before_complete,
        )
        _queue_purge_buffer_top_up(background_tasks)
        return _removal_stream_response(request, run)

    if mode == "full":
        result = full_remove_library_items(db, settings, keys)
        _queue_purge_buffer_top_up(background_tasks)
        return {**result, "action_id": None, "undoable": False}

    # Snapshot the index rows BEFORE deleting so the owner can undo this run.
    snapshot = db.snapshot_library_items_by_rating_keys(keys)
    deleted = db.delete_library_items_by_rating_keys(keys)
    drop_cached_purge_keys(db, keys)
    _queue_purge_buffer_top_up(background_tasks)
    action_id = _record_purge_index_undo(db, user, snapshot, deleted)
    return {
        "mode": "index",
        "deleted": deleted,
        "action_id": action_id,
        "undoable": action_id is not None,
    }


@router.post("/api/library/purge-candidates/dismiss")
def dismiss_purge_candidates_endpoint(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    user=Depends(require_role("owner")),
):
    rating_keys = payload.get("rating_keys", [])
    if not rating_keys or not isinstance(rating_keys, list):
        raise HTTPException(status_code=400, detail="rating_keys must be a non-empty list")
    db = _db()
    dismissed = db.dismiss_purge_candidates(rating_keys)
    drop_cached_purge_keys(db, [str(key) for key in rating_keys])
    _queue_purge_buffer_top_up(background_tasks)
    del user
    return {"dismissed": dismissed}


@router.get("/api/library/overview")
def library_overview_endpoint(user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    return _sanitize_library_payload(library_overview(_db()), user)


@router.get("/api/library/anniversaries")
def library_anniversaries_endpoint(
    limit: int = 5,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Return library titles with milestone release anniversaries (5, 10, 15, 20, 25+ years)."""
    import time as _time
    from datetime import date

    del user
    db = _db()
    today = date.today()
    current_year = today.year

    milestone_years = [current_year - n for n in (5, 10, 15, 20, 25, 30, 40, 50, 75)]
    placeholders = ",".join("?" * len(milestone_years))

    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, rating_key, media_type, title, year, genres, poster_url,
                   backdrop_url, view_count, last_viewed_at, tmdb_id, tvdb_id,
                   runtime_minutes, summary
            FROM library_items
            WHERE year IN ({placeholders})
            ORDER BY year ASC
            LIMIT ?
            """,
            (*milestone_years, limit),
        ).fetchall()

    items = []
    for row in rows:
        years_ago = current_year - (row["year"] or current_year)
        context = f"Released {years_ago} year{'s' if years_ago != 1 else ''} ago"
        last_viewed = row["last_viewed_at"]
        if last_viewed:
            months_ago = max(1, int((_time.time() - last_viewed) / (30 * 86400)))
            context += f" \u00b7 Last watched {months_ago} month{'s' if months_ago != 1 else ''} ago"
        item_data = dict(row)
        item_data["anniversary_context"] = context
        items.append(item_data)

    return {"items": items, "count": len(items)}


@router.get("/api/library/feeds/hub")
def library_feed_explore_hub(
    limit: int = EXPLORE_RAIL_LIMIT,
    refresh: bool = False,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Single Explore home payload (rails + pulse) with a short server TTL cache."""
    user_id = None
    if user is not None and getattr(user, "id", None):
        user_id = str(user.id)
    payload = get_explore_hub(
        _db(),
        _settings(),
        is_youth=bool(getattr(user, "is_youth", False)),
        user_id=user_id,
        rail_limit=limit,
        bypass_cache=bool(refresh),
    )
    # Sanitize nested rail items the same way individual feed routes do.
    rails = payload.get("rails") or {}
    sanitized_rails = {
        key: _sanitize_library_payload(value, user, attach_watch=False)
        if isinstance(value, dict)
        else value
        for key, value in rails.items()
    }
    payload = {
        **payload,
        "rails": sanitized_rails,
        "overview": _sanitize_library_payload(
            payload.get("overview") or {}, user, attach_watch=False
        ),
        "health": _sanitize_library_payload(
            payload.get("health") or {}, user, attach_watch=False
        ),
    }
    return payload


@router.get("/api/library/feeds/recently-added")
def library_feed_recently_added(
    limit: int = 12,
    days: int = 30,
    offset: int = 0,
    media_type: Optional[str] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore rail: titles added to the library within ``days``."""
    return _sanitize_library_payload(
        feed_recently_added(
            _db(),
            limit=limit,
            days=days,
            offset=offset,
            media_type=media_type,
        ),
        user,
    )


@router.get("/api/library/feeds/recently-added-episodes")
def library_feed_recently_added_episodes(
    limit: int = 12,
    days: int = 30,
    offset: int = 0,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore rail: recently added TV *episodes* (fresh arrivals), not shows."""
    return _sanitize_library_payload(
        feed_recently_added_episodes(
            _db(),
            limit=limit,
            days=days,
            offset=offset,
        ),
        user,
    )


@router.get("/api/library/feeds/recent-releases")
def library_feed_recent_releases(
    limit: int = 12,
    days: int = 90,
    offset: int = 0,
    media_type: Optional[str] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore rail: titles with release/first_air within ``days`` (honest empty)."""
    return _sanitize_library_payload(
        feed_recent_releases(
            _db(),
            limit=limit,
            days=days,
            offset=offset,
            media_type=media_type,
        ),
        user,
    )


@router.get("/api/library/feeds/revisit-these")
def library_feed_revisit_these(
    limit: int = 20,
    idle_days: int = 60,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore rail: partially watched TV idle for ``idle_days``+ (random ≤20)."""
    return _sanitize_library_payload(
        feed_revisit_these(
            _db(),
            limit=limit,
            idle_days=idle_days,
        ),
        user,
    )


@router.get("/api/library/feeds/continue-watching")
def library_feed_continue_watching(
    limit: int = 12,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore Continue Watching rail — Plex on-deck / in-progress (not live sessions)."""
    settings = _settings()
    plex_client = None
    if settings.plex_url and settings.plex_token:
        plex_client = PlexClient(
            settings.plex_url,
            settings.plex_token,
            movie_section=settings.plex_movie_section or None,
            tv_section=settings.plex_tv_section or None,
        )
    return _sanitize_library_payload(
        feed_continue_watching(_db(), limit=limit, plex_client=plex_client),
        user,
    )


@router.get("/api/library/feeds/unfinished")
def library_feed_unfinished(
    limit: int = 12,
    idle_days: int = 60,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore Unfinished rail — leftover runtime, not 60-day idle Revisit These."""
    return _sanitize_library_payload(
        feed_unfinished(_db(), limit=limit, idle_days=idle_days),
        user,
    )


@router.get("/api/library/feeds/afterglow")
def library_feed_afterglow(
    limit: int = 12,
    days: int = 14,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore Afterglow rail — post-watch review dialogue from persona presets."""
    user_id = None
    if user is not None and getattr(user, "id", None):
        user_id = str(user.id)
    return _sanitize_library_payload(
        feed_afterglow(_db(), limit=limit, days=days, user_id=user_id),
        user,
    )


@router.get("/api/library/feeds/tonight-table")
def library_feed_tonight_table(
    limit: int = 3,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore Tonight's table — two unwatched under 2h plus one comfort."""
    return _sanitize_library_payload(
        feed_tonight_table(_db(), limit=limit),
        user,
    )


@router.get("/api/library/feeds/for-you")
def library_feed_for_you(
    limit: int = 12,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore For you — watched_bridge picks (same refusal rules as inbox)."""
    from projectionist.library.feeds import feed_for_you
    from projectionist.youth.apply import youth_max_for_user

    settings = _settings()
    multi_user = bool(settings.features.multi_user_enabled)
    user_id = str(user.id) if multi_user and getattr(user, "id", None) else (
        str(getattr(user, "id", None) or "bootstrap-owner")
    )
    return _sanitize_library_payload(
        feed_for_you(
            _db(),
            limit=limit,
            user_id=user_id,
            multi_user_enabled=multi_user,
            youth_max_rating=youth_max_for_user(user, settings),
        ),
        user,
    )


@router.get("/api/library/feeds/pick-for-me")
def library_feed_pick_for_me(
    limit: int = 8,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Youth-friendly pick-for-me spinner: named bridge why, else no why."""
    from projectionist.library.feeds import feed_pick_for_me
    from projectionist.youth.apply import youth_max_for_user

    settings = _settings()
    multi_user = bool(settings.features.multi_user_enabled)
    user_id = str(user.id) if multi_user and getattr(user, "id", None) else (
        str(getattr(user, "id", None) or "bootstrap-owner")
    )
    capped = max(1, min(int(limit), 24))
    filters = filters_from_mapping(
        {
            "unwatched_only": True,
            "sort": "vote_average",
            "sort_dir": "desc",
            "limit": capped,
        }
    )
    filters = _apply_youth_filters(filters, user)
    result = query_library(_db(), filters)
    fillers = list(result.get("items") or [])
    import random

    random.shuffle(fillers)
    payload = feed_pick_for_me(
        _db(),
        limit=capped,
        user_id=user_id,
        multi_user_enabled=multi_user,
        youth_max_rating=youth_max_for_user(user, settings),
        filler_items=fillers,
    )
    # Youth + Live on → soft-suggest a youth-safe station when one exists.
    if bool(getattr(user, "is_youth", False)):
        settings = _settings()
        if bool(getattr(settings.features, "live_channels_enabled", False)):
            try:
                from projectionist.live_channels.airing_why import pick_youth_safe_live_station
                from projectionist.live_channels.guide_cache import get_on_now_snapshot
                from projectionist.youth.rating_gate import resolve_youth_max_rating

                snap = get_on_now_snapshot(
                    settings,
                    youth_max_rating=resolve_youth_max_rating(settings),
                    db=_db(),
                )
                payload["live_station"] = pick_youth_safe_live_station(
                    settings, snap.get("channels") or []
                )
            except Exception:  # noqa: BLE001
                payload["live_station"] = None
    return _sanitize_library_payload(payload, user)


@router.get("/api/library/feeds/on-this-day")
def library_feed_on_this_day(
    limit: int = 12,
    month: Optional[int] = None,
    day: Optional[int] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore On This Day — calendar dates when available, else milestone years."""
    return _sanitize_library_payload(
        feed_on_this_day(_db(), limit=limit, month=month, day=day),
        user,
    )


@router.get("/api/library/feeds/director-spotlight")
def library_feed_director_spotlight(
    limit: int = 12,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore rail: stable daily rotation through owned director filmographies."""
    return _sanitize_library_payload(feed_director_spotlight(_db(), limit=limit), user)


@router.get("/api/library/feeds/genre-spotlight")
def library_feed_genre_spotlight(
    limit: int = 12,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore rail: stable daily rotation through well-stocked genres."""
    return _sanitize_library_payload(feed_genre_spotlight(_db(), limit=limit), user)


@router.get("/api/library/feeds/seasonal-spotlight")
def library_feed_seasonal_spotlight(
    limit: int = 12,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Explore rail: holiday-window or season-aware owned title matches."""
    return _sanitize_library_payload(feed_seasonal_spotlight(_db(), limit=limit), user)


@router.get("/api/library/neighbors/{item_id}")
def library_neighbors_endpoint(
    item_id: int,
    mode: str = "similar",
    limit: int = 12,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Cached plot neighbors by library item id (similar | surprising)."""
    return _sanitize_library_payload(
        neighbors_payload(_db(), item_id, mode=mode, limit=limit),
        user,
    )


@router.post("/api/library/neighbors/{item_id}/{neighbor_id}/dismiss")
def dismiss_plot_neighbor(
    item_id: int,
    neighbor_id: int,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Remove a cached neighbor edge and emit bad-match telemetry (Plot Lab)."""
    del user
    db = _db()
    removed = db.remove_neighbor_edge(int(item_id), int(neighbor_id))
    if not removed:
        raise HTTPException(status_code=404, detail="Neighbor edge not found")

    from projectionist.telemetry.explore import schedule_bad_neighbor_match

    schedule_bad_neighbor_match(
        seed_item_id=int(item_id),
        neighbor_item_id=int(neighbor_id),
        context_source="plot_lab",
    )
    return {
        "removed": True,
        "item_id": int(item_id),
        "neighbor_id": int(neighbor_id),
    }


@router.get("/api/library/motifs")
def library_motifs_endpoint(
    limit: int = 50,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Motif facet catalog for Plot Lab chips."""
    return _sanitize_library_payload(
        library_facet_catalog(_db(), "motif", limit=limit),
        user,
    )


@router.get("/api/library/quick-pick")
def library_quick_pick_endpoint(
    max_runtime: Optional[int] = None,
    genre: Optional[str] = None,
    mood: Optional[str] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Pick ONE random unwatched title, optionally constrained by runtime/genre/mood.

    ``mood`` is a one-shot bias for this pick only — it does not write taste profile.
    """
    db = _db()
    settings = _settings()

    mood_genre_map = {
        "cozy": "drama,romance,family,comedy",
        "thrill": "thriller,action,horror,crime",
        "laugh": "comedy",
        "think": "drama,documentary,history,war",
        "escape": "fantasy,adventure,science fiction,animation",
    }
    mood_key = str(mood or "").strip().lower()
    effective_genre = genre
    mood_label = None
    if mood_key and mood_key in mood_genre_map and not genre:
        effective_genre = mood_genre_map[mood_key]
        mood_label = mood_key

    # Treat NULL view_count as unwatched (matches episode/query helpers).
    where_clauses = ["COALESCE(view_count, 0) = 0"]
    params: list = []
    if max_runtime is not None:
        where_clauses.append("runtime_minutes IS NOT NULL AND runtime_minutes <= ?")
        params.append(max_runtime)
    if effective_genre:
        genre_parts = [g.strip() for g in effective_genre.split(",") if g.strip()]
        if genre_parts:
            genre_or = " OR ".join("LOWER(genres) LIKE ?" for _ in genre_parts)
            where_clauses.append(f"({genre_or})")
            params.extend(f"%{g.lower()}%" for g in genre_parts)

    # Youth: fail-closed content-rating gate (same SQL shape as library query).
    if bool(getattr(user, "is_youth", False)):
        from projectionist.youth.rating_gate import resolve_youth_max_rating, youth_content_rating_sql

        max_rating = resolve_youth_max_rating(settings)
        sql_frag, rating_params = youth_content_rating_sql(max_rating)
        where_clauses.append(sql_frag)
        params.extend(rating_params)

    where_sql = " AND ".join(where_clauses)
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, rating_key, media_type, title, year, genres, poster_url,
                   backdrop_url, view_count, last_viewed_at, tmdb_id, tvdb_id,
                   runtime_minutes, summary, content_rating
            FROM library_items
            WHERE {where_sql}
            ORDER BY RANDOM()
            LIMIT 25
            """,
            params,
        ).fetchall()

    from projectionist.notifications.recommendation_reasons import (
        named_bridge_for_item,
        tracker_watched_item_ids,
    )
    from projectionist.youth.apply import youth_max_for_user

    multi_user = bool(settings.features.multi_user_enabled)
    user_id = str(user.id) if multi_user and getattr(user, "id", None) else (
        str(getattr(user, "id", None) or "bootstrap-owner")
    )
    watched_ids = tracker_watched_item_ids(db)
    row = None
    for candidate in rows:
        try:
            if int(candidate["id"]) in watched_ids:
                continue
        except (TypeError, ValueError, KeyError):
            pass
        row = candidate
        break

    if not row:
        return {"item": None, "why": "No unwatched titles match the criteria.", "mood": mood_label}

    genres_raw = row["genres"]
    genres_list: list = []
    if isinstance(genres_raw, list):
        genres_list = genres_raw
    elif isinstance(genres_raw, str) and genres_raw.strip():
        try:
            parsed = json.loads(genres_raw)
            genres_list = parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError, json.JSONDecodeError):
            genres_list = []

    item = {key: row[key] for key in row.keys()}
    item["genres"] = genres_list
    item["view_count"] = int(item.get("view_count") or 0)
    # TitleCard expects overview + in_library (DB column is summary).
    item["overview"] = str(item.get("summary") or "")
    item["in_library"] = True
    item["content_rating"] = str(item.get("content_rating") or "")

    explanation = named_bridge_for_item(
        db,
        item,
        user_id=user_id,
        multi_user_enabled=multi_user,
        youth_max_rating=youth_max_for_user(user, settings),
    )
    why = ""
    if explanation:
        item["explanation"] = explanation
        why = str(explanation.get("sentence") or "").strip()
        if why:
            item["why"] = why
    return {"item": item, "why": why, "mood": mood_label, "explanation": explanation}


@router.get("/api/library/query")
async def library_query_endpoint(
    media_type: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    genres: Optional[str] = None,
    directors: Optional[str] = None,
    cast: Optional[str] = None,
    keywords: Optional[str] = None,
    motifs: Optional[str] = None,
    themes: Optional[str] = None,
    countries: Optional[str] = None,
    content_ratings: Optional[str] = None,
    collection_name: Optional[str] = None,
    original_language: Optional[str] = None,
    query: Optional[str] = None,
    fts_query: Optional[str] = None,
    semantic_query: Optional[str] = None,
    unwatched_only: bool = False,
    min_view_count: Optional[int] = None,
    max_view_count: Optional[int] = None,
    stale_days: Optional[int] = None,
    recently_added_days: Optional[int] = None,
    added_from: Optional[str] = None,
    added_to: Optional[str] = None,
    last_viewed_from: Optional[str] = None,
    last_viewed_to: Optional[str] = None,
    runtime_min: Optional[int] = None,
    runtime_max: Optional[int] = None,
    vote_min: Optional[float] = None,
    vote_max: Optional[float] = None,
    file_size_min: Optional[int] = None,
    file_size_max: Optional[int] = None,
    in_radarr: Optional[bool] = None,
    in_sonarr: Optional[bool] = None,
    missing_tmdb_id: bool = False,
    in_progress_only: bool = False,
    sort: str = "title",
    sort_dir: Optional[Literal["asc", "desc"]] = None,
    offset: int = 0,
    limit: int = 25,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    filters = filters_from_mapping(
        {
            "media_type": media_type,
            "year_from": year_from,
            "year_to": year_to,
            "genres": genres,
            "directors": directors,
            "cast": cast,
            "keywords": keywords,
            "motifs": motifs,
            "themes": themes,
            "countries": countries,
            "content_ratings": content_ratings,
            "collection_name": collection_name,
            "original_language": original_language,
            "query": query,
            "fts_query": fts_query,
            "semantic_query": semantic_query,
            "unwatched_only": unwatched_only,
            "min_view_count": min_view_count,
            "max_view_count": max_view_count,
            "stale_days": stale_days,
            "recently_added_days": recently_added_days,
            "added_from": added_from,
            "added_to": added_to,
            "last_viewed_from": last_viewed_from,
            "last_viewed_to": last_viewed_to,
            "runtime_min": runtime_min,
            "runtime_max": runtime_max,
            "vote_min": vote_min,
            "vote_max": vote_max,
            "file_size_min": file_size_min,
            "file_size_max": file_size_max,
            "in_radarr": in_radarr,
            "in_sonarr": in_sonarr,
            "missing_tmdb_id": missing_tmdb_id,
            "in_progress_only": in_progress_only,
            "sort": sort,
            "sort_dir": sort_dir,
            "offset": offset,
            "limit": limit,
        }
    )
    filters = _apply_youth_filters(filters, user)
    if filters.semantic_query:
        result = await query_library_async(_db(), filters, _settings())
    else:
        result = query_library(_db(), filters)
    return _sanitize_library_payload(result, user)


@router.get("/api/search/external")
def external_search_endpoint(
    q: str = "",
    media_type: str = "movie",
    limit: int = 20,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Search beyond the collection: TMDB titles de-duped against the library.

    Returns TitleCard-shaped items flagged with in_library / in_radarr /
    in_sonarr / already_queued (plus tvdb_id enrichment for shows so Sonarr adds
    resolve), sanitized to the caller's audience. The acquisition-capable
    frontend card drives the role-aware add/request flow from these flags.
    """
    query = (q or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="Enter something to search for.")
    normalized_type = normalize_external_media_type(media_type)
    capped_limit = max(1, min(int(limit or 20), 20))
    result = external_tmdb_search(
        _db(),
        _settings(),
        media_type=normalized_type,
        title=query,
        limit=capped_limit,
    )
    if not result.ok:
        if result.error_kind == ERROR_NOT_CONFIGURED:
            # Non-leaky: never surface the raw provider/config detail to members.
            raise HTTPException(
                status_code=503,
                detail="Search beyond the collection isn't available right now.",
            )
        raise HTTPException(status_code=400, detail="Could not search beyond the collection.")
    items: List[Dict[str, Any]] = []
    for card in result.cards:
        payload = card.model_dump()
        payload["already_queued"] = bool(card.in_radarr or card.in_sonarr)
        items.append(payload)
    sanitized = _sanitize_library_payload(items, user)
    return {
        "query": query,
        "media_type": normalized_type,
        "total_matched": result.total_matched,
        "returned": len(sanitized) if isinstance(sanitized, list) else 0,
        "items": sanitized,
    }


@router.get("/api/library/export.csv")
async def library_export_csv(
    request: Request,
    columns: str = "all",
    user=Depends(get_current_user_dep),
) -> StreamingResponse:
    """Export the current filtered library view after applying the normal privacy boundary."""
    raw: Dict[str, Any] = dict(request.query_params)
    for key in ("unwatched_only", "missing_tmdb_id", "in_progress_only"):
        if key in raw:
            raw[key] = str(raw[key]).lower() in {"1", "true", "yes", "on"}
    raw["limit"] = 5000
    raw["offset"] = 0
    filters = filters_from_mapping(raw)
    filters = _apply_youth_filters(filters, user)
    result = (
        await query_library_async(_db(), filters, _settings())
        if filters.semantic_query
        else query_library(_db(), filters)
    )
    items = _sanitize_library_payload(result["items"], user)
    requested = list(_EXPORT_COLUMNS) if columns.strip().lower() == "all" else [
        value.strip() for value in columns.split(",") if value.strip()
    ]
    if not requested or any(value not in _EXPORT_COLUMNS for value in requested):
        raise HTTPException(status_code=400, detail="columns must be all or a comma-separated safe column list")

    def rows():
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=requested, extrasaction="ignore")
        writer.writeheader()
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
        for item in items:
            row = dict(item)
            for field in ("genres",):
                if isinstance(row.get(field), list):
                    row[field] = ", ".join(str(value) for value in row[field])
            writer.writerow({field: row.get(field, "") for field in requested})
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    filename = f"projectionist-library-{date.today().isoformat()}.csv"
    return StreamingResponse(
        rows(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/api/library/aggregate")
def library_aggregate_endpoint(
    group_by: str,
    media_type: Optional[str] = None,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
    genres: Optional[str] = None,
    directors: Optional[str] = None,
    keywords: Optional[str] = None,
    top_examples: int = 3,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    normalized = group_by.strip().lower()
    allowed = {
        "decade",
        "year",
        "genre",
        "media_type",
        "director",
        "actor",
        "keyword",
        "country",
        "language",
        "content_rating",
        "runtime_bucket",
        "decade_genre",
    }
    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail="group_by must be decade, year, genre, media_type, director, actor, keyword, "
            "country, language, content_rating, runtime_bucket, or decade_genre",
        )
    filters = filters_from_mapping(
        {
            "media_type": media_type,
            "year_from": year_from,
            "year_to": year_to,
            "genres": genres,
            "directors": directors,
            "keywords": keywords,
        }
    )
    filters = _apply_youth_filters(filters, user)
    example_limit = max(0, min(int(top_examples), 10))
    return _sanitize_library_payload(
        aggregate_library(_db(), normalized, filters, top_examples=example_limit),  # type: ignore[arg-type]
        user,
    )


@router.get("/api/library/facets")
def library_facets_endpoint(
    facet_type: str,
    limit: int = 50,
    q: Optional[str] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    try:
        return _sanitize_library_payload(
            library_facet_catalog(_db(), facet_type, limit=limit, q=q),
            user,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(exc, "Invalid facet query"),
        ) from exc


@router.get("/api/library/tv/episodes")
def library_tv_episodes_endpoint(
    show: Optional[str] = None,
    show_id: Optional[int] = None,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    season: Optional[int] = None,
    unwatched_only: bool = False,
    offset: int = 0,
    limit: int = 25,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    return _sanitize_library_payload(
        query_episodes(
            _db(),
            show=show,
            show_id=show_id,
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
            season=season,
            unwatched_only=unwatched_only,
            offset=offset,
            limit=limit,
        ),
        user,
    )


@router.get("/api/library/tv/episode/{rating_key}")
def library_tv_episode_detail_endpoint(
    rating_key: str,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    payload = get_episode_detail(_db(), rating_key)
    if payload.get("error"):
        raise HTTPException(status_code=404, detail=str(payload["error"]))
    return _sanitize_library_payload(payload, user)


@router.get("/api/library/tv/seasons")
def library_tv_seasons_endpoint(
    show: Optional[str] = None,
    show_id: Optional[int] = None,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    if show_id is None and tmdb_id is None and tvdb_id is None and not show:
        raise HTTPException(
            status_code=400,
            detail="Provide show_id, tmdb_id, tvdb_id, or show",
        )
    payload = query_show_seasons(
        _db(),
        show=show,
        show_id=show_id,
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
    )
    if payload.get("error"):
        raise HTTPException(status_code=404, detail=str(payload["error"]))
    return _sanitize_library_payload(payload, user)


@router.post("/api/library/tv/remove")
def library_tv_remove_endpoint(
    payload: TvRemovePayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Owner season/episode remove via Sonarr episode files + Plex + index."""
    del user
    from projectionist.connectors.arr_errors import ArrTitleNotFoundError
    from projectionist.library.tv_remove import remove_tv_scope

    try:
        return remove_tv_scope(
            _db(),
            _settings(),
            scope=payload.scope,
            show_id=payload.show_id,
            tmdb_id=payload.tmdb_id,
            tvdb_id=payload.tvdb_id,
            rating_key=payload.rating_key,
            season_number=payload.season_number,
            episode_rating_key=payload.episode_rating_key,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(error, "Invalid TV remove request"),
        ) from error
    except ArrTitleNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(error, "TV remove failed"),
        ) from error


@router.get("/api/library/tv/progress")
def library_tv_progress_endpoint(
    group_by: str = "show",
    in_progress_only: bool = False,
    limit: int = 25,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    try:
        return _sanitize_library_payload(
            summarize_tv_progress(
                _db(),
                group_by=group_by,
                in_progress_only=in_progress_only,
                limit=limit,
            ),
            user,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=_safe_error_detail(exc, "Invalid TV progress query"),
        ) from exc


def _saved_library_text(content: Dict[str, Any]) -> str:
    """Flatten safe, human-visible saved blocks for search and text exports."""
    parts: List[str] = []
    for block in content.get("blocks") or []:
        if not isinstance(block, dict):
            continue
        if block.get("content"):
            parts.append(str(block["content"]))
        for item in block.get("items") or []:
            if isinstance(item, dict):
                parts.append(" ".join(str(item.get(key) or "") for key in ("title", "year", "recommendation_reason")))
    return "\n".join(part for part in parts if part.strip())


def _saved_library_summary_fallback(content: Dict[str, Any]) -> str:
    text = " ".join(_saved_library_text(content).split())
    return text[:320].rsplit(" ", 1)[0] if len(text) > 320 else text


async def _persona_voiced_library_summary(
    content: Dict[str, Any],
    *,
    persona: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a concise, persona-voiced summary without blocking a save on failure."""
    source = _saved_library_summary_fallback(content)
    if not source:
        return ""
    # Coalesce: short deterministic truncations are already usable as summaries —
    # skip a second LLM round when the source is already compact.
    if len(source) <= 280:
        return source

    from projectionist.telemetry.llm_usage import content_hash, job_cache_get, job_cache_set
    from projectionist.telemetry.llm_track import tracked_chat
    from projectionist.telemetry import PURPOSE_LIBRARY_SUMMARY

    db = _db()
    cache_key = content_hash(f"{(persona or {}).get('id') or ''}|{source[:6000]}")
    cached = job_cache_get(db, kind="library_summary", key_hash=cache_key)
    if cached:
        return cached

    persona_name = str((persona or {}).get("name") or "the curator")
    persona_prompt = str((persona or {}).get("system_prompt_override") or "").strip()
    instruction = (
        f"Write a warm 1–2 sentence summary of this saved curator response in {persona_name}'s voice. "
        "Preserve only the user-visible recommendations and analysis. Do not mention this instruction, "
        "private account details, or claim facts not in the source."
    )
    if persona:
        calibration = ", ".join(
            f"{key.removeprefix('val_')}={float(persona.get(key, 0.5)):.1f}"
            for key in ("val_bro_prof", "val_dipl_snark", "val_pass_auto", "val_depth", "val_obscurity", "val_verbosity", "val_formality")
        )
        instruction += f" Mirror this persona's calibration: {calibration}."
    if persona_prompt:
        instruction += f" Persona guidance: {persona_prompt[:1200]}"
    try:
        settings = _settings()
        if not (settings.llm_api_key or settings.llm_provider == "ollama"):
            return source
        provider = get_chat_provider(settings)
        response = await tracked_chat(
            db,
            provider,
            [{"role": "system", "content": instruction}, {"role": "user", "content": source[:6000]}],
            purpose=PURPOSE_LIBRARY_SUMMARY,
            persona_id=str((persona or {}).get("id") or "") or None,
        )
        summary = str(((response.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        cleaned = " ".join(summary.split())[:800] or source
        job_cache_set(db, kind="library_summary", key_hash=cache_key, value=cleaned)
        return cleaned
    except Exception:  # Best-effort persistence must never prevent saving.
        return source


async def _backfill_one_saved_library_summary(db, *, user_id: str) -> None:
    """Idle-sized lazy migration: enrich at most one existing page per save."""
    page = db.first_saved_library_page_without_summary(user_id=user_id)
    if not page:
        return
    persona = db.get_persona_template(page["persona_id"]) if page.get("persona_id") else None
    summary = await _persona_voiced_library_summary(page["content"], persona=persona)
    if summary:
        db.update_saved_library_summary(page["id"], user_id=user_id, summary=summary)


def _saved_library_response(page: Dict[str, Any], user) -> Dict[str, Any]:
    """Attach only display-safe persona metadata to a member-visible saved page."""
    persona_id = page.get("persona_id")
    persona = _db().get_persona_template(persona_id) if persona_id else None
    content = normalize_saved_library_content(page.get("content"))
    if persona:
        page = {
            **page,
            "content": content,
            "persona": {
                "id": persona["id"],
                "name": persona["name"],
                "accent_color": persona.get("accent_color") or "",
            },
        }
    elif content is not page.get("content"):
        page = {**page, "content": content}
    return _sanitize_library_payload(page, user)


@router.post("/api/saved-library")
async def create_saved_library_page(
    payload: SavedLibraryPagePayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    db = _db()
    user_id = _scoped_user_id(user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in to save curator responses")
    source_thread = None
    if payload.source_session_id:
        source_thread = db.get_chat_thread(payload.source_session_id, user_id=user_id)
        if source_thread is None:
            raise HTTPException(status_code=404, detail="Source conversation not found")
    # Persist the same audience-safe representation that members can view.
    # Also bound/de-dupe title rails so a bad gap turn cannot save a crazy strip.
    content = normalize_saved_library_content(payload.content)
    content = _sanitize_library_payload(content, user)
    if not isinstance(content, dict):
        content = normalize_saved_library_content(payload.content)
        if not isinstance(content, dict):
            content = payload.content
    persona_id = source_thread.get("persona_id") if source_thread else None
    persona = db.get_persona_template(persona_id) if persona_id else None
    name = (payload.user_title or payload.name).strip()
    summary = (payload.summary or "").strip() or await _persona_voiced_library_summary(content, persona=persona)
    searchable_text = f"{name}\n{summary}\n{_saved_library_text(content)}"
    saved = db.create_saved_library_page(
        page_id=uuid.uuid4().hex,
        user_id=user_id,
        name=name,
        source_session_id=payload.source_session_id,
        source_message_id=payload.source_message_id,
        persona_id=persona_id,
        summary=summary,
        content=content,
        searchable_text=searchable_text,
    )
    # Keep old rows fresh gradually; failures are intentionally invisible to saves.
    try:
        await _backfill_one_saved_library_summary(db, user_id=user_id)
    except Exception:
        logger.debug("Saved-library summary backfill skipped", exc_info=True)
    return saved


@router.get("/api/saved-library")
def list_saved_library_pages(
    q: str = "",
    user=Depends(get_current_user_dep),
) -> List[Dict[str, Any]]:
    user_id = _scoped_user_id(user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in to view your library")
    pages = _db().list_saved_library_pages(user_id=user_id, query=q)
    return [_saved_library_response(page, user) for page in pages]


@router.get("/api/saved-library/{page_id}")
def get_saved_library_page(page_id: str, user=Depends(get_current_user_dep)) -> Dict[str, Any]:
    user_id = _scoped_user_id(user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in to view your library")
    page = _db().get_saved_library_page(page_id, user_id=user_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Saved page not found")
    return _saved_library_response(page, user)


@router.delete("/api/saved-library/{page_id}")
def delete_saved_library_page(page_id: str, user=Depends(get_current_user_dep)) -> Dict[str, bool]:
    user_id = _scoped_user_id(user)
    if not user_id or not _db().delete_saved_library_page(page_id, user_id=user_id):
        raise HTTPException(status_code=404, detail="Saved page not found")
    return {"deleted": True}


@router.get("/api/saved-library/{page_id}/export")
def export_saved_library_page(
    page_id: str,
    format: Literal["json", "markdown", "txt"] = "markdown",
    user=Depends(get_current_user_dep),
) -> Response:
    user_id = _scoped_user_id(user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in to view your library")
    page = _db().get_saved_library_page(page_id, user_id=user_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Saved page not found")
    text = _saved_library_text(page["content"])
    if format == "json":
        return Response(json.dumps(page, indent=2), media_type="application/json")
    if format == "txt":
        return Response(f"{page['name']}\n\n{text}\n", media_type="text/plain")
    return Response(f"# {page['name']}\n\n{text}\n", media_type="text/markdown")


@router.post("/api/saved-library/{page_id}/share")
def share_saved_library_page(
    page_id: str,
    payload: SavedLibrarySharePayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Notify household peers about an account-scoped saved page (never public)."""
    if not _settings().features.multi_user_enabled:
        raise HTTPException(status_code=400, detail="Multi-user mode is required to share with household")
    user_id = _scoped_user_id(user)
    if not user_id:
        raise HTTPException(status_code=401, detail="Sign in to share library pages")
    db = _db()
    page = db.get_saved_library_page(page_id, user_id=user_id)
    if page is None:
        raise HTTPException(status_code=404, detail="Saved page not found")
    settings = _settings()
    from_name = user.preferred_name or user.display_name or "Someone"
    page_name = str(page.get("name") or "a saved page").strip() or "a saved page"
    note = (payload.message or "").strip() or None
    recipient_ids: List[str] = []
    for raw_id in payload.to_user_ids:
        rid = str(raw_id or "").strip()
        if not rid or rid == user.id:
            continue
        target = db.get_user(rid)
        if target is None:
            raise HTTPException(status_code=404, detail=f"User not found: {rid}")
        if bool(int(target["disabled"] or 0)):
            raise HTTPException(status_code=400, detail=f"User is disabled: {rid}")
        recipient_ids.append(rid)
    if not recipient_ids:
        raise HTTPException(status_code=400, detail="Choose at least one recipient")
    from projectionist.notifications import deliver_notification

    delivered = []
    for rid in recipient_ids:
        try:
            result = deliver_notification(
                db,
                settings,
                user_id=rid,
                kind="library-share",
                title=page_name,
                body=note or f"{from_name} shared a saved curator page with you",
                payload={
                    "share_type": "saved_library",
                    "page_id": page["id"],
                    "page_name": page_name,
                    "path": f"/library/{page['id']}",
                },
                from_user_id=user.id,
                related_id=page["id"],
                email_subject=f"{from_name} shared “{page_name}”",
            )
            delivered.append({"user_id": rid, "notification": result.get("notification")})
        except Exception:  # noqa: BLE001
            logger.exception("Failed to share saved library page with %s", rid)
    return {"count": len(delivered), "items": delivered}



def register_library_routes(
    app,
    *,
    db_factory: Callable[[], Any],
    settings_factory: Callable[[], Settings],
    safe_error_detail: Callable[..., str],
) -> None:
    """Attach library routes to the FastAPI app. Lifespan stays in app.py."""
    global _db_factory, _settings_factory, _safe_error_detail_fn
    _db_factory = db_factory
    _settings_factory = settings_factory
    _safe_error_detail_fn = safe_error_detail
    app.include_router(router)
