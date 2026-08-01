"""Owner season/episode remove via Sonarr episode files + Plex + index."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from projectionist.agent.tools import resolve_arr_removal_target
from projectionist.config_store import Settings, plex_configuration_error
from projectionist.connectors.arr_errors import (
    ArrTitleNotFoundError,
    format_arr_http_error,
    is_arr_not_found_error,
)
from projectionist.connectors.plex import PlexClient
from projectionist.connectors.sonarr import SonarrClient
from projectionist.library.db import Database
from projectionist.library.full_remove import (
    _as_dict,
    _as_nonneg_int,
    _as_path,
    _optional_int,
    _row_value,
    apply_library_bytes_fallback,
    infer_removed_folders,
    resolve_arr_file_path,
)

logger = logging.getLogger("projectionist.library.tv_remove")

TV_REMOVE_SCOPES = frozenset({"season", "episode"})


def normalize_tv_remove_scope(value: Any) -> str:
    scope = str(value or "").strip().lower()
    if scope not in TV_REMOVE_SCOPES:
        raise ValueError('scope must be "season" or "episode"')
    return scope


def _resolve_show_row(
    db: Database,
    *,
    show_id: Optional[int] = None,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    rating_key: Optional[str] = None,
):
    if show_id is not None:
        row = db.library_item_by_id(int(show_id))
        if row is not None and str(row["media_type"] or "") == "show":
            return row
    if rating_key:
        row = db.library_item_by_rating_key(str(rating_key).strip())
        if row is not None and str(row["media_type"] or "") == "show":
            return row
    if tmdb_id is not None:
        return db.library_item_by_tmdb(int(tmdb_id), "show")
    if tvdb_id is not None:
        return db.library_item_by_tvdb(int(tvdb_id))
    return None


def _sonarr_episode_file_ids(
    episodes: Sequence[Mapping[str, Any]],
    *,
    season_number: Optional[int] = None,
    episode_number: Optional[int] = None,
) -> List[int]:
    ids: List[int] = []
    seen: Set[int] = set()
    for raw in episodes:
        ep = _as_dict(raw)
        if season_number is not None:
            try:
                if int(ep.get("seasonNumber")) != int(season_number):
                    continue
            except (TypeError, ValueError):
                continue
        if episode_number is not None:
            try:
                if int(ep.get("episodeNumber")) != int(episode_number):
                    continue
            except (TypeError, ValueError):
                continue
        file_id = _optional_int(ep.get("episodeFileId"))
        if file_id is None or file_id <= 0 or file_id in seen:
            continue
        # Skip episodes without a file on disk.
        if ep.get("hasFile") is False:
            continue
        seen.add(file_id)
        ids.append(file_id)
    return ids


def _snapshot_from_episode_files(
    series: Mapping[str, Any],
    episode_files: Sequence[Mapping[str, Any]],
    *,
    file_ids: Sequence[int],
) -> Dict[str, Any]:
    wanted = {int(value) for value in file_ids}
    root_path = _as_path(series.get("path"))
    files: List[str] = []
    bytes_from_files = 0
    for raw in episode_files:
        row = _as_dict(raw)
        file_id = _optional_int(row.get("id"))
        if file_id is None or file_id not in wanted:
            continue
        path = resolve_arr_file_path(row, root_path=root_path)
        if path:
            files.append(path)
        bytes_from_files += _as_nonneg_int(row.get("size"))
    # Partial season/episode deletes: folder list from file parents only (not whole series root).
    folders = infer_removed_folders(files, root_path=None)
    if not folders and root_path and not files:
        folders = infer_removed_folders([], root_path=root_path)
    note = ""
    if not files and folders:
        note = (
            "Sonarr reported the series folder but no matching episode file paths "
            "for this season/episode."
        )
    return apply_library_bytes_fallback(
        {
            "files": files,
            "folders": folders,
            "bytes_freed": bytes_from_files,
            "bytes_source": "arr" if bytes_from_files > 0 else "unknown",
            "note": note,
        }
    )


def _remove_plex_keys(settings: Settings, rating_keys: Sequence[str]) -> Dict[str, Any]:
    config_error = plex_configuration_error(settings)
    if config_error:
        return {"removed": 0, "skipped": True, "reason": "plex_not_configured"}
    client = PlexClient(settings.plex_url, settings.plex_token)
    removed = 0
    errors: List[str] = []
    for key in rating_keys:
        text = str(key or "").strip()
        if not text:
            continue
        try:
            client.delete_metadata(text)
            removed += 1
        except Exception as error:  # noqa: BLE001 — continue other episodes
            logger.warning("Plex episode metadata delete failed for %s: %s", text, error)
            errors.append(str(error))
    return {
        "removed": removed,
        "skipped": False,
        "errors": errors[:5],
    }


def remove_tv_scope(
    db: Database,
    settings: Settings,
    *,
    scope: str,
    show_id: Optional[int] = None,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    rating_key: Optional[str] = None,
    season_number: Optional[int] = None,
    episode_rating_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Remove one season or episode: Sonarr files → Plex metadata → index rows."""
    normalized = normalize_tv_remove_scope(scope)
    show_row = _resolve_show_row(
        db,
        show_id=show_id,
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
        rating_key=rating_key,
    )
    if show_row is None:
        raise RuntimeError("Show not found in the Projectionist library index")

    title = str(_row_value(show_row, "title") or "Untitled")
    show_item_id = int(show_row["id"])
    show_tvdb = _optional_int(_row_value(show_row, "tvdb_id"))
    show_tmdb = _optional_int(_row_value(show_row, "tmdb_id"))

    if not settings.sonarr_url or not settings.sonarr_api_key:
        raise RuntimeError("Sonarr is not configured — cannot delete episode files")

    library_eps = db.library_episodes_for_show(show_item_id)
    target_eps: List[Any]
    if normalized == "season":
        if season_number is None:
            raise ValueError("season_number is required for season scope")
        target_eps = [
            ep
            for ep in library_eps
            if ep["season_number"] is not None and int(ep["season_number"]) == int(season_number)
        ]
        if not target_eps:
            raise RuntimeError(f"No indexed episodes for season {int(season_number)}")
        match_season = int(season_number)
        match_episode = None
        label = f"{title} · Season {match_season}"
    else:
        ep_key = str(episode_rating_key or "").strip()
        if not ep_key:
            raise ValueError("episode_rating_key is required for episode scope")
        target_eps = [ep for ep in library_eps if str(ep["rating_key"] or "").strip() == ep_key]
        if not target_eps:
            raise RuntimeError("Episode not found in the Projectionist library index")
        match_season = (
            int(target_eps[0]["season_number"])
            if target_eps[0]["season_number"] is not None
            else None
        )
        match_episode = (
            int(target_eps[0]["episode_number"])
            if target_eps[0]["episode_number"] is not None
            else None
        )
        ep_title = str(target_eps[0]["title"] or "Episode")
        label = f"{title} · S{match_season or 0:02d}E{match_episode or 0:02d} · {ep_title}"

    library_bytes = sum(int(ep["file_size"] or 0) for ep in target_eps)
    plex_keys = [
        str(ep["rating_key"]).strip()
        for ep in target_eps
        if str(ep["rating_key"] or "").strip()
    ]

    try:
        resolved = resolve_arr_removal_target(
            settings,
            media_type="show",
            tmdb_id=None,
            tvdb_id=show_tvdb,
            title=title,
        )
    except ArrTitleNotFoundError:
        raise
    except RuntimeError as error:
        raise RuntimeError(format_arr_http_error(error)) from error

    arr_id = int(resolved["arr_id"])
    client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
    try:
        series = client.series_by_id(arr_id) or {}
        sonarr_episodes = client.episodes(arr_id)
        episode_files = client.episode_files(arr_id)
    except RuntimeError as error:
        raise RuntimeError(format_arr_http_error(error)) from error

    file_ids = _sonarr_episode_file_ids(
        sonarr_episodes,
        season_number=match_season,
        episode_number=match_episode if normalized == "episode" else None,
    )
    # If Sonarr episode records lack episodeFileId, fall back to episodefile seasonNumber.
    if not file_ids:
        for raw in episode_files:
            row = _as_dict(raw)
            try:
                season_ok = match_season is None or int(row.get("seasonNumber")) == int(match_season)
            except (TypeError, ValueError):
                season_ok = False
            if not season_ok:
                continue
            if normalized == "episode" and match_episode is not None:
                # episodefile payload often lacks episodeNumber; keep season filter only
                # when matching a single episode via library S/E was already applied above.
                pass
            file_id = _optional_int(row.get("id"))
            if file_id and file_id > 0:
                file_ids.append(file_id)
        # For single-episode deletes without a reliable Sonarr match, avoid deleting
        # an entire season via the episodefile season filter.
        if normalized == "episode" and len(file_ids) != 1:
            file_ids = []

    snapshot = apply_library_bytes_fallback(
        _snapshot_from_episode_files(series, episode_files, file_ids=file_ids),
        library_bytes=library_bytes,
    )

    try:
        if file_ids:
            client.delete_episode_files(file_ids)
    except RuntimeError as error:
        if is_arr_not_found_error(error):
            raise ArrTitleNotFoundError("Sonarr", title=title, arr_id=arr_id) from error
        raise RuntimeError(format_arr_http_error(error)) from error

    plex_result = _remove_plex_keys(settings, plex_keys)

    if normalized == "season":
        index_deleted = db.delete_episodes_for_season(show_item_id, int(season_number))
    else:
        index_deleted = db.delete_episode_by_rating_key(
            show_item_id, str(episode_rating_key or "").strip()
        )

    entry = {
        "rating_key": str(_row_value(show_row, "rating_key") or ""),
        "title": label,
        "media_type": "show",
        "scope": normalized,
        "season_number": match_season,
        "episode_rating_key": str(episode_rating_key or "").strip() or None,
        "ok": index_deleted > 0 or bool(file_ids),
        "index_deleted": index_deleted > 0,
        "files": list(snapshot.get("files") or []),
        "folders": list(snapshot.get("folders") or []),
        "bytes_freed": int(snapshot.get("bytes_freed") or 0),
        "bytes_source": str(snapshot.get("bytes_source") or "unknown"),
        "note": str(snapshot.get("note") or ""),
        "arr": {
            "service": "sonarr",
            "removed": bool(file_ids),
            "arr_id": arr_id,
            "episode_file_ids": file_ids,
            "delete_files": True,
        },
        "plex": plex_result,
        "show_id": show_item_id,
        "tmdb_id": show_tmdb,
        "tvdb_id": show_tvdb,
    }

    logger.info(
        "tv_remove scope=%s title=%r files=%d bytes_freed=%d bytes_source=%s",
        normalized,
        label,
        len(entry["files"]),
        entry["bytes_freed"],
        entry["bytes_source"],
    )

    from projectionist.library.full_remove import aggregate_removal_totals

    return {
        "mode": "full",
        "scope": normalized,
        "deleted": 1 if entry["ok"] else 0,
        "results": [entry],
        "errors": [],
        "totals": aggregate_removal_totals([entry]),
    }
