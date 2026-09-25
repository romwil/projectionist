"""Show picker + Sonarr episode-file inventory for an investigation."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.library.episode_investigate.filenames import claimed_from_path, claimed_from_sonarr
from projectionist.library.full_remove import resolve_arr_file_path

logger = logging.getLogger(__name__)

MAX_FILES = 80


def row_value(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, Mapping):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def list_investigate_shows(db: Any) -> List[Dict[str, Any]]:
    rows = db.library_shows() if db is not None else []
    out: List[Dict[str, Any]] = []
    for row in rows:
        try:
            item_id = int(row_value(row, "id") or 0)
        except (TypeError, ValueError):
            continue
        if item_id <= 0:
            continue
        year = row_value(row, "year")
        try:
            year_i = int(year) if year is not None else None
        except (TypeError, ValueError):
            year_i = None
        out.append(
            {
                "id": item_id,
                "title": str(row_value(row, "title") or ""),
                "year": year_i,
                "tmdb_id": _opt_int(row_value(row, "tmdb_id")),
                "tvdb_id": _opt_int(row_value(row, "tvdb_id")),
                "season_count": _opt_int(row_value(row, "season_count")),
                "rating_key": str(row_value(row, "rating_key") or ""),
            }
        )
    return out


def household_titles(db: Any, *, limit: int = 40) -> List[str]:
    titles = []
    for show in list_investigate_shows(db):
        title = str(show.get("title") or "").strip()
        if title:
            titles.append(title)
        if len(titles) >= limit:
            break
    return titles


def load_show(db: Any, show_id: int) -> Optional[Dict[str, Any]]:
    row = db.library_item_by_id(int(show_id)) if db is not None else None
    if row is None:
        return None
    if str(row_value(row, "media_type") or "") != "show":
        return None
    year = row_value(row, "year")
    try:
        year_i = int(year) if year is not None else None
    except (TypeError, ValueError):
        year_i = None
    return {
        "id": int(row_value(row, "id")),
        "title": str(row_value(row, "title") or ""),
        "year": year_i,
        "tmdb_id": _opt_int(row_value(row, "tmdb_id")),
        "tvdb_id": _opt_int(row_value(row, "tvdb_id")),
        "season_count": _opt_int(row_value(row, "season_count")),
        "rating_key": str(row_value(row, "rating_key") or ""),
    }


def sonarr_configured(settings: Any) -> bool:
    return bool(
        str(getattr(settings, "sonarr_url", "") or "").strip()
        and str(getattr(settings, "sonarr_api_key", "") or "").strip()
    )


def find_sonarr_series(client: Any, show: Mapping[str, Any]) -> Optional[Any]:
    tvdb = show.get("tvdb_id")
    if tvdb:
        found = client.series_by_tvdb_id(int(tvdb))
        if found:
            return found
    tmdb = show.get("tmdb_id")
    if tmdb and hasattr(client, "series_list"):
        for series in client.series_list():
            series_tmdb = getattr(series, "tmdb_id", None)
            if series_tmdb and int(series_tmdb) == int(tmdb):
                return series
    title = str(show.get("title") or "").strip().lower()
    if title and hasattr(client, "series_list"):
        for series in client.series_list():
            if str(getattr(series, "title", "") or "").strip().lower() == title:
                return series
    return None


def list_episode_files(
    settings: Any,
    show: Mapping[str, Any],
    *,
    season: Optional[int] = None,
    client: Any = None,
    limit: int = MAX_FILES,
) -> Dict[str, Any]:
    if not sonarr_configured(settings) and client is None:
        return {"ok": False, "error": "Sonarr is not configured — Investigate needs episode files.", "files": []}
    if client is None:
        from projectionist.connectors.sonarr import SonarrClient

        client = SonarrClient(settings.sonarr_url, settings.sonarr_api_key)
    series = find_sonarr_series(client, show)
    if series is None:
        return {"ok": False, "error": "This show is not in Sonarr.", "files": []}
    series_id = int(series.id)
    raw_files = client.episode_files(series_id)
    raw_episodes = client.episodes(series_id)
    by_file: Dict[int, List[Mapping[str, Any]]] = {}
    catalog: List[Dict[str, Any]] = []
    for episode in raw_episodes:
        if not isinstance(episode, Mapping):
            continue
        try:
            ep_season = int(episode.get("seasonNumber"))
            ep_number = int(episode.get("episodeNumber"))
        except (TypeError, ValueError):
            continue
        if season is not None and ep_season != int(season):
            continue
        file_id = episode.get("episodeFileId")
        try:
            file_i = int(file_id) if file_id else 0
        except (TypeError, ValueError):
            file_i = 0
        if file_i:
            by_file.setdefault(file_i, []).append(episode)
        catalog.append(
            {
                "season": ep_season,
                "episode": ep_number,
                "title": str(episode.get("title") or ""),
                "runtime_minutes": _opt_int(episode.get("runtime")),
                "sonarr_episode_id": episode.get("id"),
                "has_file": bool(file_i),
            }
        )
    root = str(getattr(settings, "sonarr_root_folder", "") or "")
    files: List[Dict[str, Any]] = []
    for raw in raw_files:
        if not isinstance(raw, Mapping):
            continue
        try:
            file_id = int(raw.get("id"))
        except (TypeError, ValueError):
            continue
        path = resolve_arr_file_path(raw, root_path=root)
        if not path:
            continue
        linked = by_file.get(file_id) or []
        if season is not None:
            keep = False
            for episode in linked:
                try:
                    if int(episode.get("seasonNumber")) == int(season):
                        keep = True
                        break
                except (TypeError, ValueError):
                    continue
            file_season = raw.get("seasonNumber")
            try:
                if file_season is not None and int(file_season) == int(season):
                    keep = True
            except (TypeError, ValueError):
                pass
            if not keep:
                continue
        files.append(
            {
                "id": str(file_id),
                "file_id": file_id,
                "series_id": series_id,
                "path": path,
                "size": int(raw.get("size") or 0),
                "claimed": claimed_from_path(path),
                "sonarr": claimed_from_sonarr(linked[0] if linked else None),
                "sonarr_episodes": [claimed_from_sonarr(item) for item in linked],
            }
        )
        if len(files) >= limit:
            break
    seasons = sorted(
        {
            int(item["season"])
            for item in catalog
            if item.get("season") is not None and int(item["season"]) >= 0
        }
    )
    return {
        "ok": True,
        "error": "",
        "series_id": series_id,
        "files": files,
        "catalog": catalog,
        "seasons": seasons,
    }


def merge_tmdb_runtimes(
    catalog: Sequence[Mapping[str, Any]],
    tmdb_episodes: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    by_se = {
        (int(item["season"]), int(item["episode"])): dict(item)
        for item in catalog
        if item.get("season") is not None and item.get("episode") is not None
    }
    for entry in tmdb_episodes:
        try:
            key = (int(entry["season"]), int(entry["episode"]))
        except (TypeError, ValueError, KeyError):
            continue
        row = by_se.setdefault(
            key,
            {
                "season": key[0],
                "episode": key[1],
                "title": str(entry.get("title") or ""),
                "runtime_minutes": entry.get("runtime_minutes"),
                "sonarr_episode_id": None,
                "has_file": False,
            },
        )
        if not row.get("runtime_minutes") and entry.get("runtime_minutes"):
            row["runtime_minutes"] = entry.get("runtime_minutes")
        if not row.get("title") and entry.get("title"):
            row["title"] = entry.get("title")
        row["still_url"] = entry.get("still_url") or row.get("still_url") or ""
        row["still_path"] = entry.get("still_path") or row.get("still_path") or ""
    return list(by_se.values())


def _opt_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
