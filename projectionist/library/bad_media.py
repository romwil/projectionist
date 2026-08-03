"""Ask Radarr/Sonarr to replace bad on-disk files without import exclusion."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional

from projectionist.config_store import Settings
from projectionist.connectors.arr_errors import format_arr_http_error
from projectionist.connectors.radarr import RadarrClient
from projectionist.connectors.sonarr import SonarrClient
from projectionist.library.db import Database
from projectionist.library.full_remove import _optional_int, _row_value
from projectionist.library.tv_remove import _sonarr_episode_file_ids

logger = logging.getLogger("projectionist.library.bad_media")


class BadMediaError(LookupError):
    """Bad-media replace could not resolve the title in *arr or the library index."""


def _resolve_library_row(
    db: Database,
    *,
    rating_key: Optional[str] = None,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    media_type: Optional[str] = None,
):
    key = str(rating_key or "").strip()
    if key:
        row = db.library_item_by_rating_key(key)
        if row is not None:
            return row
    mt = str(media_type or "").strip().lower()
    if tmdb_id is not None and mt in {"", "movie", "show"}:
        row = db.library_item_by_tmdb(int(tmdb_id), mt if mt else "movie")
        if row is not None:
            return row
    if tvdb_id is not None:
        row = db.library_item_by_tvdb(int(tvdb_id))
        if row is not None:
            return row
    return None


def mark_bad_media(
    db: Database,
    settings: Settings,
    *,
    rating_key: Optional[str] = None,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    media_type: Optional[str] = None,
    episode_rating_key: Optional[str] = None,
    season_number: Optional[int] = None,
    episode_number: Optional[int] = None,
    note: str = "",
) -> Dict[str, Any]:
    """Delete the known bad file(s) in *arr and trigger a replacement search.

    Does **not** add Radarr/Sonarr import exclusions or Projectionist acquisition
    exclusions — the title stays wanted and should be re-downloaded.
    """
    row = _resolve_library_row(
        db,
        rating_key=rating_key,
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
        media_type=media_type,
    )
    resolved_type = str(media_type or (_row_value(row, "media_type") if row else "") or "movie")
    title = str(_row_value(row, "title") if row else "") or "Untitled"
    resolved_tmdb = _optional_int(tmdb_id if tmdb_id is not None else _row_value(row, "tmdb_id"))
    resolved_tvdb = _optional_int(tvdb_id if tvdb_id is not None else _row_value(row, "tvdb_id"))

    if resolved_type == "movie":
        return _mark_bad_movie(
            settings,
            title=title,
            tmdb_id=resolved_tmdb,
            note=note,
        )
    return _mark_bad_show(
        db,
        settings,
        title=title,
        tvdb_id=resolved_tvdb,
        episode_rating_key=episode_rating_key,
        season_number=season_number,
        episode_number=episode_number,
        show_row=row,
        note=note,
    )


def _mark_bad_movie(
    settings: Settings,
    *,
    title: str,
    tmdb_id: Optional[int],
    note: str,
) -> Dict[str, Any]:
    if not settings.radarr_url or not settings.radarr_api_key:
        raise BadMediaError("Radarr is not configured — cannot replace a bad movie file.")
    if tmdb_id is None:
        raise BadMediaError("TMDB id is required to replace a bad movie file.")

    client = RadarrClient(settings.radarr_url, settings.radarr_api_key)
    try:
        movie = client.movie_by_tmdb_id(int(tmdb_id))
    except RuntimeError as error:
        raise RuntimeError(format_arr_http_error(error)) from error
    if movie is None:
        raise BadMediaError(f'"{title}" is not managed by Radarr.')

    files_removed = 0
    if movie.movie_file_id is not None:
        try:
            client.mark_movie_file_failed(movie.movie_file_id)
            files_removed = 1
        except RuntimeError as error:
            raise RuntimeError(format_arr_http_error(error)) from error
    try:
        command = client.search_movie(movie.id)
    except RuntimeError as error:
        raise RuntimeError(format_arr_http_error(error)) from error

    action = "radarr delete-file-and-search" if files_removed else "radarr search"
    payload = {
        "ok": True,
        "media_type": "movie",
        "title": movie.title or title,
        "tmdb_id": int(tmdb_id),
        "action": action,
        "files_removed": files_removed,
        "command": command,
        "add_exclusion": False,
        "note": str(note or "").strip(),
    }
    logger.info(
        "mark_bad_media movie title=%r tmdb_id=%s action=%s files_removed=%d",
        payload["title"],
        tmdb_id,
        action,
        files_removed,
    )
    return payload


def _resolve_episode_numbers(
    show_row,
    *,
    episode_rating_key: Optional[str],
    season_number: Optional[int],
    episode_number: Optional[int],
    db: Database,
) -> tuple[Optional[int], Optional[int]]:
    if season_number is not None and episode_number is not None:
        return int(season_number), int(episode_number)
    ep_key = str(episode_rating_key or "").strip()
    if not ep_key or show_row is None:
        return (
            int(season_number) if season_number is not None else None,
            int(episode_number) if episode_number is not None else None,
        )
    show_id = int(show_row["id"])
    for ep in db.library_episodes_for_show(show_id):
        if str(ep["rating_key"] or "").strip() != ep_key:
            continue
        sn = ep["season_number"]
        en = ep["episode_number"]
        return (
            int(sn) if sn is not None else None,
            int(en) if en is not None else None,
        )
    return (
        int(season_number) if season_number is not None else None,
        int(episode_number) if episode_number is not None else None,
    )


def _mark_bad_show(
    db: Database,
    settings: Settings,
    *,
    title: str,
    tvdb_id: Optional[int],
    episode_rating_key: Optional[str],
    season_number: Optional[int],
    episode_number: Optional[int],
    show_row,
    note: str,
) -> Dict[str, Any]:
    if not settings.sonarr_url or not settings.sonarr_api_key:
        raise BadMediaError("Sonarr is not configured — cannot replace a bad TV file.")
    if tvdb_id is None:
        raise BadMediaError("TVDB id is required to replace a bad TV file.")

    client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
    try:
        series = client.series_by_tvdb_id(int(tvdb_id))
    except RuntimeError as error:
        raise RuntimeError(format_arr_http_error(error)) from error
    if series is None:
        raise BadMediaError(f'"{title}" is not managed by Sonarr.')

    match_season, match_episode = _resolve_episode_numbers(
        show_row,
        episode_rating_key=episode_rating_key,
        season_number=season_number,
        episode_number=episode_number,
        db=db,
    )
    scoped_episode = match_season is not None and match_episode is not None

    try:
        sonarr_episodes = client.episodes(series.id)
        episode_files = client.episode_files(series.id)
    except RuntimeError as error:
        raise RuntimeError(format_arr_http_error(error)) from error

    file_ids = _sonarr_episode_file_ids(
        sonarr_episodes,
        season_number=match_season,
        episode_number=match_episode if scoped_episode else None,
    )
    if not file_ids and scoped_episode:
        for raw in episode_files:
            if not isinstance(raw, Mapping):
                continue
            try:
                if int(raw.get("seasonNumber")) != int(match_season):
                    continue
            except (TypeError, ValueError):
                continue
            file_id = _optional_int(raw.get("id"))
            if file_id and file_id > 0:
                file_ids = [file_id]
                break

    if not file_ids and not scoped_episode:
        file_ids = _sonarr_episode_file_ids(sonarr_episodes)

    episode_ids_for_search: List[int] = []
    if scoped_episode:
        for raw in sonarr_episodes:
            if not isinstance(raw, Mapping):
                continue
            try:
                if int(raw.get("seasonNumber")) != int(match_season):
                    continue
                if int(raw.get("episodeNumber")) != int(match_episode):
                    continue
            except (TypeError, ValueError):
                continue
            ep_id = _optional_int(raw.get("id"))
            if ep_id and ep_id > 0:
                episode_ids_for_search.append(ep_id)

    files_removed = 0
    if file_ids:
        try:
            client.delete_episode_files(file_ids)
            files_removed = len(file_ids)
        except RuntimeError as error:
            raise RuntimeError(format_arr_http_error(error)) from error

    try:
        if episode_ids_for_search:
            command = client.search_episodes(episode_ids_for_search)
            action = "sonarr delete-episode-file-and-search"
        else:
            command = client.search_series(series.id)
            action = (
                "sonarr delete-episode-files-and-search"
                if files_removed
                else "sonarr search"
            )
    except RuntimeError as error:
        raise RuntimeError(format_arr_http_error(error)) from error

    label = title
    if scoped_episode:
        label = f"{title} · S{int(match_season):02d}E{int(match_episode):02d}"

    payload = {
        "ok": True,
        "media_type": "show",
        "title": label,
        "tvdb_id": int(tvdb_id),
        "action": action,
        "files_removed": files_removed,
        "episode_file_ids": list(file_ids),
        "command": command,
        "add_exclusion": False,
        "note": str(note or "").strip(),
    }
    logger.info(
        "mark_bad_media show title=%r tvdb_id=%s action=%s files_removed=%d",
        label,
        tvdb_id,
        action,
        files_removed,
    )
    return payload


def mark_bad_media_for_issue(
    db: Database,
    settings: Settings,
    issue: Mapping[str, Any],
) -> Dict[str, Any]:
    """Run the replace playbook for an approved media issue row."""
    return mark_bad_media(
        db,
        settings,
        rating_key=str(issue.get("rating_key") or "") or None,
        tmdb_id=_optional_int(issue.get("tmdb_id")),
        tvdb_id=_optional_int(issue.get("tvdb_id")),
        media_type=str(issue.get("media_type") or ""),
        note=str(issue.get("note") or ""),
    )
