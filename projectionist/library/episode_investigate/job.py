"""Admin execution jobs for Investigate and same-show Apply."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.library.admin_execution import (
    finished_message,
    flatten_result,
    request_cancel,
    start_worker,
    store_for,
)
from projectionist.library.episode_investigate.apply import apply_rows, undo_apply
from projectionist.library.episode_investigate.capabilities import llm_accepts_images
from projectionist.library.episode_investigate.acrcloud import identify_file
from projectionist.library.episode_investigate.catalog import (
    household_series,
    list_episode_files,
    load_show,
    merge_tmdb_runtimes,
)
from projectionist.library.episode_investigate.ffmpeg import extract_stills, probe_runtime_seconds
from projectionist.library.episode_investigate.fusion import fuse_row
from projectionist.library.episode_investigate.oshash import file_oshash, lookup_opensubtitles
from projectionist.library.episode_investigate.path_map import (
    TranslationLog,
    discover_media_roots,
    resolve_visible_media_path,
)
from projectionist.library.episode_investigate.stills import still_url, stills_dir
from projectionist.library.episode_investigate.tmdb_stills import (
    download_episode_stills,
    season_episodes,
    series_seasons,
)
from projectionist.library.episode_investigate.vision import identify_from_stills

logger = logging.getLogger(__name__)

KIND = "episode_investigate"
APPLY_KIND = "episode_investigate_apply"
IDLE_MESSAGE = "Pick a show to investigate"
APPLY_IDLE = "Nothing to apply"
UNREADABLE_PATH = "unreadable_path"
UNREADABLE_REASON = (
    "Episode file is not readable in this container. "
    "Sonarr's path could not be mapped to a file visible here "
    "(configured TV/Sonarr roots and Plex library locations were tried)."
)


def build_status() -> Dict[str, Any]:
    return flatten_result(store_for(KIND, idle_message=IDLE_MESSAGE).snapshot())


def build_apply_status() -> Dict[str, Any]:
    return flatten_result(store_for(APPLY_KIND, idle_message=APPLY_IDLE).snapshot())


def cancel_job() -> Dict[str, Any]:
    return request_cancel(KIND)


def cancel_apply_job() -> Dict[str, Any]:
    return request_cancel(APPLY_KIND)


def start_investigate_job(
    db: Any,
    settings: Any,
    *,
    show_id: int,
    season: Optional[int] = None,
    use_vision: Optional[bool] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    show = load_show(db, int(show_id))
    if show is None:
        return {"accepted": False, "ok": False, "error": "Show not found.", "message": "Show not found."}
    inventory = list_episode_files(settings, show, season=season)
    if not inventory.get("ok"):
        message = str(inventory.get("error") or "Could not list episode files.")
        return {"accepted": False, "ok": False, "error": message, "message": message}
    files = list(inventory.get("files") or [])
    if not files:
        return {
            "accepted": False,
            "ok": False,
            "error": "No episode files found for that show or season.",
            "message": "No episode files found for that show or season.",
        }
    vision_on = llm_accepts_images(settings) if use_vision is None else bool(use_vision)
    items = [
        {
            "id": row["id"],
            "title": _item_title(row),
            "status": "queued",
        }
        for row in files
    ]
    store = store_for(KIND, idle_message=IDLE_MESSAGE)
    job_id = store.begin(phase="queued", message="Queued episode investigation…", items=items)
    if not job_id:
        snap = store.snapshot()
        snap["accepted"] = False
        snap["message"] = snap.get("message") or "An investigation is already running."
        return snap

    root = Path(data_dir) if data_dir is not None else _data_dir()
    house = household_series(db, settings)

    def _run(job_store, cancel) -> Mapping[str, Any]:
        job_store.update("running", "Investigating episode files…")
        rows = investigate_files(
            settings,
            show,
            files,
            catalog=list(inventory.get("catalog") or []),
            season=season,
            use_vision=vision_on,
            household=house.get("titles") or [],
            household_tmdb_ids=house.get("tmdb_ids") or [],
            job_id=job_id,
            data_dir=root,
            store=job_store,
            cancel=cancel,
            series_id=inventory.get("series_id"),
        )
        payload = {
            "show": show,
            "season": season,
            "use_vision": vision_on,
            "vision_used": bool(
                vision_on
                and llm_accepts_images(settings)
                and any(row.get("stills") for row in rows)
            ),
            "stills_leave_lan": vision_on and llm_accepts_images(settings),
            "rows": rows,
            "series_id": inventory.get("series_id"),
            "seasons": inventory.get("seasons") or [],
        }
        snap = job_store.snapshot()
        phase = "cancelled" if cancel.is_set() else "done"
        job_store.set_done(
            finished_message(snap.get("execution") or {}, noun="file", action="Investigated"),
            result=payload,
            phase=phase,
        )
        return payload

    if not start_worker(KIND, _run, name="episode-investigate"):
        snap = flatten_result(store.snapshot())
        snap["accepted"] = False
        return snap
    snap = flatten_result(store.snapshot())
    snap["accepted"] = True
    snap["job_id"] = job_id
    return snap


def start_apply_job(
    settings: Any,
    *,
    file_ids: Sequence[str],
    rows: Optional[Sequence[Mapping[str, Any]]] = None,
    show: Optional[Mapping[str, Any]] = None,
    create_opt_in: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    snap = build_status()
    result = snap.get("result") if isinstance(snap.get("result"), Mapping) else {}
    review_rows = list(rows or result.get("rows") or [])
    review_show = show or result.get("show") or {}
    if not review_rows or not review_show:
        return {
            "accepted": False,
            "ok": False,
            "error": "Investigate a show before applying.",
            "message": "Investigate a show before applying.",
        }
    wanted = [str(item) for item in file_ids if str(item)]
    if not wanted:
        return {
            "accepted": False,
            "ok": False,
            "error": "Select at least one same-show row to apply.",
            "message": "Select at least one same-show row to apply.",
        }
    items = [{"id": file_id, "title": file_id, "status": "queued"} for file_id in wanted]
    store = store_for(APPLY_KIND, idle_message=APPLY_IDLE)
    job_id = store.begin(phase="queued", message="Queued same-show remap…", items=items)
    if not job_id:
        out = store.snapshot()
        out["accepted"] = False
        out["message"] = out.get("message") or "An apply is already running."
        return out

    def _run(job_store, cancel) -> Mapping[str, Any]:
        del cancel
        job_store.update("running", "Applying same-show remaps…")
        selected_rows = [row for row in review_rows if str(row.get("id")) in set(wanted)]
        for row in selected_rows:
            job_store.set_item(str(row.get("id")), "running", message=str(row.get("filename") or row.get("id")))
        payload = apply_rows(
            settings,
            review_show,
            review_rows,
            wanted,
            create_opt_in=create_opt_in or [],
        )
        for change in payload.get("changes") or []:
            job_store.set_item(str(change.get("id")), "completed", outcome="applied")
        for skipped in payload.get("skipped_rows") or []:
            job_store.set_item(str(skipped.get("id")), "skipped", outcome="other_show")
        for failed in payload.get("failed_rows") or []:
            job_store.set_item(str(failed.get("id")), "failed", error=str(failed.get("error") or "failed"))
        snap_now = job_store.snapshot()
        job_store.set_done(
            finished_message(snap_now.get("execution") or {}, noun="file", action="Applied"),
            result=payload,
            phase="done",
        )
        return payload

    if not start_worker(APPLY_KIND, _run, name="episode-investigate-apply"):
        out = flatten_result(store.snapshot())
        out["accepted"] = False
        return out
    out = flatten_result(store.snapshot())
    out["accepted"] = True
    out["job_id"] = job_id
    return out


def start_undo_job(settings: Any, *, apply_id: str) -> Dict[str, Any]:
    snap = build_apply_status()
    result = snap.get("result") if isinstance(snap.get("result"), Mapping) else {}
    if str(result.get("apply_id") or "") != str(apply_id):
        return {
            "accepted": False,
            "ok": False,
            "error": "No matching apply to undo.",
            "message": "No matching apply to undo.",
        }
    payload = undo_apply(settings, result)
    store = store_for(APPLY_KIND, idle_message=APPLY_IDLE)
    store.set_done(
        f"Undid {payload.get('restored') or 0} remaps.",
        result={**dict(result), "undo": payload},
        phase="done",
    )
    out = flatten_result(store.snapshot())
    out["accepted"] = True
    out["undo"] = payload
    return out


def investigate_files(
    settings: Any,
    show: Mapping[str, Any],
    files: Sequence[Mapping[str, Any]],
    *,
    catalog: Sequence[Mapping[str, Any]],
    season: Optional[int],
    use_vision: bool,
    household: Sequence[str],
    household_tmdb_ids: Sequence[Any] = (),
    job_id: str,
    data_dir: Path,
    store: Any = None,
    cancel: Any = None,
    series_id: Any = None,
) -> List[Dict[str, Any]]:
    tmdb_catalog: List[Dict[str, Any]] = list(catalog)
    tmdb_client = None
    tmdb_key = str(getattr(settings, "tmdb_api_key", "") or "").strip()
    if tmdb_key:
        from projectionist.connectors.tmdb import TMDBClient

        tmdb_client = TMDBClient(tmdb_key)
        if show.get("tmdb_id"):
            seasons = [int(season)] if season is not None else []
            if not seasons:
                seasons = series_seasons(tmdb_client, int(show["tmdb_id"])) or sorted(
                    {int(item["season"]) for item in catalog if item.get("season") is not None}
                )
            fetched: List[Dict[str, Any]] = []
            for season_n in seasons:
                if season_n < 0:
                    continue
                fetched.extend(season_episodes(tmdb_client, int(show["tmdb_id"]), season_n))
            tmdb_catalog = merge_tmdb_runtimes(catalog, fetched)

    extra_roots = discover_media_roots(settings)
    translation_log = TranslationLog()
    rows: List[Dict[str, Any]] = []
    for file_row in files:
        file_id = str(file_row.get("id"))
        if cancel is not None and cancel.is_set():
            if store is not None:
                store.set_item(file_id, "cancelled", outcome="cancelled")
            continue
        if store is not None:
            store.set_item(file_id, "running", message=_item_title(file_row))
        sonarr_path = str(file_row.get("path") or "")
        resolved = resolve_visible_media_path(sonarr_path, settings, extra_roots=extra_roots)
        translation_log.emit(sonarr_path, resolved)
        mapped_row = {**dict(file_row), "resolved_path": resolved or ""}
        try:
            row = investigate_one(
                settings,
                show,
                mapped_row,
                catalog=tmdb_catalog,
                use_vision=use_vision,
                household=household,
                household_tmdb_ids=household_tmdb_ids,
                job_id=job_id,
                data_dir=data_dir,
                tmdb_client=tmdb_client,
                series_id=series_id or file_row.get("series_id"),
            )
            rows.append(row)
            if store is not None:
                if row.get("stills_error") == UNREADABLE_PATH:
                    store.set_item(
                        file_id,
                        "failed",
                        error=UNREADABLE_REASON,
                        outcome="unreadable",
                    )
                else:
                    store.set_item(file_id, "completed", outcome=str(row.get("confidence") or ""))
        except Exception as error:  # noqa: BLE001
            logger.warning("investigate file failed id=%s error=%s", file_id, error)
            if store is not None:
                store.set_item(file_id, "failed", error=str(error)[:400], outcome="failed")
    return rows


def investigate_one(
    settings: Any,
    show: Mapping[str, Any],
    file_row: Mapping[str, Any],
    *,
    catalog: Sequence[Mapping[str, Any]],
    use_vision: bool,
    household: Sequence[str],
    household_tmdb_ids: Sequence[Any] = (),
    job_id: str,
    data_dir: Path,
    tmdb_client: Any = None,
    series_id: Any = None,
) -> Dict[str, Any]:
    sonarr_path = str(file_row.get("path") or "")
    resolved = str(file_row.get("resolved_path") or "").strip()
    if not resolved and sonarr_path:
        resolved = resolve_visible_media_path(sonarr_path, settings) or ""
    media_path = resolved or sonarr_path
    readable = bool(media_path) and Path(media_path).is_file()
    dest = stills_dir(data_dir, job_id, str(file_row.get("id")))
    runtime = probe_runtime_seconds(media_path) if readable else None
    extracted = extract_stills(media_path, dest, runtime_seconds=runtime) if readable else []
    digest = file_oshash(media_path) if readable else None
    opensub = lookup_opensubtitles(digest or "", settings=settings) if digest else None
    vision = None
    if use_vision and extracted and llm_accepts_images(settings):
        vision = identify_from_stills(
            settings,
            extracted,
            this_series=str(show.get("title") or ""),
            household_shows=household,
        )
    identify = None
    try:
        identify = identify_file(
            media_path if readable else sonarr_path,
            dest,
            settings=settings,
            runtime_seconds=runtime,
            tmdb_client=tmdb_client,
            this_show=show,
            file_key=str(file_row.get("id") or sonarr_path),
        )
    except Exception as error:  # noqa: BLE001 — Identify miss must not fail the job
        logger.info("identify lane skipped id=%s error=%s", file_row.get("id"), error)
        identify = {"found": False, "ok": True, "message": str(error)[:400], "title": ""}
    fused = fuse_row(
        show=show,
        catalog=catalog,
        runtime_seconds=runtime,
        opensubtitles=opensub,
        vision=vision,
        household_titles=household,
        household_tmdb_ids=household_tmdb_ids,
        identify=identify,
    )
    proposed = fused.get("proposed") or {}
    tmdb_still_paths: List[Path] = []
    if (
        tmdb_client
        and show.get("tmdb_id")
        and proposed.get("scope") == "this_series"
        and proposed.get("season") is not None
        and proposed.get("episode") is not None
    ):
        tmdb_still_paths = download_episode_stills(
            tmdb_client,
            int(show["tmdb_id"]),
            int(proposed["season"]),
            int(proposed["episode"]),
            dest,
        )
    file_id = str(file_row.get("id"))
    reasons = list(fused.get("reasons") or [])
    stills_error = UNREADABLE_PATH if not readable else ""
    if stills_error and UNREADABLE_REASON not in reasons:
        reasons.insert(0, UNREADABLE_REASON)
    return {
        "id": file_id,
        "file_id": file_row.get("file_id"),
        "series_id": series_id or file_row.get("series_id"),
        "path": sonarr_path,
        "resolved_path": media_path if readable else "",
        "filename": (file_row.get("claimed") or {}).get("filename") or Path(sonarr_path or media_path).name,
        "claimed": file_row.get("claimed") or {},
        "sonarr": file_row.get("sonarr") or {},
        "runtime_seconds": runtime,
        "oshash": digest,
        "opensubtitles": opensub,
        "stills": [still_url(job_id, file_id, path.name) for path in extracted],
        "tmdb_stills": [still_url(job_id, file_id, path.name) for path in tmdb_still_paths],
        "vision": vision,
        "identify": identify,
        "stills_error": stills_error,
        **fused,
        "reasons": reasons,
    }


def _item_title(row: Mapping[str, Any]) -> str:
    claimed = row.get("claimed") if isinstance(row.get("claimed"), Mapping) else {}
    label = str(claimed.get("label") or "")
    name = str(claimed.get("filename") or Path(str(row.get("path") or "")).name)
    return f"{label} {name}".strip() if label else name


def _data_dir() -> Path:
    from projectionist.web.jobs import get_job_manager

    return Path(get_job_manager().data_dir)
