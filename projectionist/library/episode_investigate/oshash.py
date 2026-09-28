"""OSHash (OpenSubtitles moviehash) and optional REST lookup."""

from __future__ import annotations

import logging
import os
import struct
from typing import Any, Callable, Dict, Mapping, Optional

from projectionist.library.episode_investigate.capabilities import opensubtitles_api_key

logger = logging.getLogger(__name__)

CHUNK = 65536
OPENSUBTITLES_SEARCH = "https://api.opensubtitles.com/api/v1/subtitles"

LookupFn = Callable[[str, str], Optional[Mapping[str, Any]]]


def file_oshash(path: str) -> Optional[str]:
    """OpenSubtitles moviehash (64-bit size + first/last 64 KiB)."""
    try:
        size = os.path.getsize(path)
    except OSError:
        return None
    if size <= 0:
        return None
    digest = size & 0xFFFFFFFFFFFFFFFF
    try:
        with open(path, "rb") as handle:
            digest = _add_chunk(handle, digest)
            if size > CHUNK:
                handle.seek(size - CHUNK)
                digest = _add_chunk(handle, digest)
    except OSError as error:
        logger.info("oshash read failed path=%s error=%s", path, error)
        return None
    return f"{digest:016x}"


def _add_chunk(handle: Any, digest: int) -> int:
    remaining = CHUNK
    while remaining >= 8:
        buf = handle.read(8)
        if len(buf) < 8:
            break
        digest = (digest + struct.unpack("<Q", buf)[0]) & 0xFFFFFFFFFFFFFFFF
        remaining -= 8
    return digest


def parse_opensubtitles_payload(payload: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    rows = payload.get("data") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        attrs = row.get("attributes") if isinstance(row.get("attributes"), Mapping) else {}
        feature = attrs.get("feature_details") if isinstance(attrs.get("feature_details"), Mapping) else {}
        season = feature.get("season_number")
        episode = feature.get("episode_number")
        try:
            season_i = int(season) if season is not None else None
        except (TypeError, ValueError):
            season_i = None
        try:
            episode_i = int(episode) if episode is not None else None
        except (TypeError, ValueError):
            episode_i = None
        title = str(feature.get("title") or attrs.get("feature_title") or "").strip()
        parent = str(feature.get("parent_title") or feature.get("parent_title") or "").strip()
        if season_i is None and episode_i is None and not title and not parent:
            continue
        return {
            "found": True,
            "season": season_i,
            "episode": episode_i,
            "title": title,
            "series_title": parent,
            "imdb_id": str(feature.get("imdb_id") or "") or None,
        }
    return None


def lookup_opensubtitles(
    moviehash: str,
    *,
    api_key: str = "",
    settings: Any = None,
    fetch: Optional[LookupFn] = None,
) -> Optional[Dict[str, Any]]:
    """Query OpenSubtitles Identification-by-hash when a key exists. Miss is not a failure."""
    key = api_key or opensubtitles_api_key(settings)
    digest = str(moviehash or "").strip().lower()
    if not key or not digest:
        return None
    if fetch is not None:
        payload = fetch(digest, key)
        if isinstance(payload, Mapping):
            return parse_opensubtitles_payload(payload)
        return None
    try:
        from projectionist.connectors.http import request_json

        payload = request_json(
            f"{OPENSUBTITLES_SEARCH}?moviehash={digest}",
            headers={
                "Api-Key": key,
                "Accept": "application/json",
                "User-Agent": "Projectionist v1.36.0",
            },
            timeout=20,
        )
    except Exception as error:  # noqa: BLE001 — lane miss must not fail the job
        logger.info("opensubtitles lookup failed hash=%s error=%s", digest, error)
        return None
    if isinstance(payload, Mapping):
        return parse_opensubtitles_payload(payload)
    return None
