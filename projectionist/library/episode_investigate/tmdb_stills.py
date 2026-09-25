"""TMDB episode catalog + still downloads (no change to connectors/tmdb.py)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from projectionist.connectors.http import request_bytes, request_json
from projectionist.connectors.tmdb import TMDBClient

logger = logging.getLogger(__name__)


def season_episodes(client: TMDBClient, tmdb_id: int, season: int) -> List[Dict[str, Any]]:
    if not tmdb_id:
        return []
    try:
        payload = request_json(client._url(f"/tv/{int(tmdb_id)}/season/{int(season)}"), timeout=client.timeout)
    except Exception as error:  # noqa: BLE001
        logger.info("tmdb season failed tmdb=%s season=%s error=%s", tmdb_id, season, error)
        return []
    if not isinstance(payload, Mapping):
        return []
    out: List[Dict[str, Any]] = []
    for raw in payload.get("episodes") or []:
        if not isinstance(raw, Mapping):
            continue
        try:
            number = int(raw.get("episode_number"))
        except (TypeError, ValueError):
            continue
        runtime = raw.get("runtime")
        try:
            runtime_i = int(runtime) if runtime is not None else None
        except (TypeError, ValueError):
            runtime_i = None
        still = str(raw.get("still_path") or "").strip()
        out.append(
            {
                "season": int(season),
                "episode": number,
                "title": str(raw.get("name") or ""),
                "runtime_minutes": runtime_i,
                "still_path": still,
                "still_url": client.backdrop_url(still, size="w300") if still else "",
                "overview": str(raw.get("overview") or ""),
            }
        )
    return out


def series_seasons(client: TMDBClient, tmdb_id: int) -> List[int]:
    if not tmdb_id:
        return []
    try:
        details = client.tv_details(int(tmdb_id))
    except Exception as error:  # noqa: BLE001
        logger.info("tmdb tv details failed tmdb=%s error=%s", tmdb_id, error)
        return []
    seasons: List[int] = []
    for raw in details.get("seasons") or []:
        if not isinstance(raw, Mapping):
            continue
        try:
            number = int(raw.get("season_number"))
        except (TypeError, ValueError):
            continue
        if number >= 0:
            seasons.append(number)
    return seasons


def download_episode_stills(
    client: TMDBClient,
    tmdb_id: int,
    season: int,
    episode: int,
    dest_dir: Path,
    *,
    limit: int = 3,
) -> List[Path]:
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    urls: List[str] = []
    try:
        payload = request_json(
            client._url(f"/tv/{int(tmdb_id)}/season/{int(season)}/episode/{int(episode)}/images"),
            timeout=client.timeout,
        )
    except Exception as error:  # noqa: BLE001
        logger.info("tmdb episode images failed: %s", error)
        payload = {}
    stills = payload.get("stills") if isinstance(payload, Mapping) else None
    if isinstance(stills, list):
        for entry in stills:
            if not isinstance(entry, Mapping):
                continue
            url = client.backdrop_url(str(entry.get("file_path") or ""), size="w300")
            if url:
                urls.append(url)
            if len(urls) >= limit:
                break
    if not urls:
        try:
            details = request_json(
                client._url(f"/tv/{int(tmdb_id)}/season/{int(season)}/episode/{int(episode)}"),
                timeout=client.timeout,
            )
        except Exception:
            details = {}
        still = str(details.get("still_path") or "") if isinstance(details, Mapping) else ""
        url = client.backdrop_url(still, size="w300") if still else ""
        if url:
            urls.append(url)
    written: List[Path] = []
    for index, url in enumerate(urls[:limit]):
        out = dest / f"tmdb-{index}.jpg"
        try:
            blob = request_bytes(url, timeout=20, max_bytes=2_000_000)
        except Exception as error:  # noqa: BLE001
            logger.info("tmdb still download failed url=%s error=%s", url, error)
            continue
        if blob:
            out.write_bytes(blob)
            written.append(out)
    return written
