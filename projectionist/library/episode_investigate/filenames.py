"""Filename / Sonarr SxxEyy helpers — display (left column) only, never evidence."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping, Optional, Tuple

SEASON_EPISODE_RE = re.compile(
    r"(?i)(?:^|[._\s\-\[(])s(\d{1,2})[ ._\-]*e(\d{1,3})(?:$|[._\s\-\])])"
)
# Scene-style 1x02 is still a claim, not evidence.
SCENE_PAIR_RE = re.compile(r"(?i)(?:^|[._\s\-\[(])(\d{1,2})x(\d{1,3})(?:$|[._\s\-\])])")
UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|]+')


def parse_season_episode(name: str) -> Optional[Tuple[int, int]]:
    """Parse a claimed SxxEyy (or 1x02) from a filename. Not evidence."""
    text = str(name or "")
    match = SEASON_EPISODE_RE.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = SCENE_PAIR_RE.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def format_se(season: Any, episode: Any) -> str:
    try:
        return f"S{int(season):02d}E{int(episode):02d}"
    except (TypeError, ValueError):
        return ""


def sanitize_filename_part(value: str) -> str:
    cleaned = UNSAFE_FILENAME.sub("", str(value or "")).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Episode"


def plex_proper_name(
    show_title: str,
    season: int,
    episode: int,
    episode_title: str,
    *,
    ext: str,
) -> str:
    """Plex-style episode filename in the current folder (no season move)."""
    show = sanitize_filename_part(show_title)
    title = sanitize_filename_part(episode_title)
    suffix = ext if str(ext or "").startswith(".") else f".{ext or 'mkv'}"
    return f"{show} - {format_se(season, episode)} - {title}{suffix}"


def claimed_from_path(path: str) -> dict[str, Any]:
    filename = Path(path).name
    parsed = parse_season_episode(filename)
    season, episode = parsed if parsed else (None, None)
    return {
        "source": "filename",
        "filename": filename,
        "season": season,
        "episode": episode,
        "label": format_se(season, episode) if parsed else "",
        "evidence": False,
    }


def claimed_from_sonarr(episode_row: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    if not isinstance(episode_row, Mapping):
        return {
            "source": "sonarr",
            "season": None,
            "episode": None,
            "title": "",
            "episode_id": None,
            "label": "",
            "evidence": False,
        }
    season = episode_row.get("seasonNumber", episode_row.get("season"))
    number = episode_row.get("episodeNumber", episode_row.get("episode"))
    try:
        season_i = int(season) if season is not None else None
    except (TypeError, ValueError):
        season_i = None
    try:
        number_i = int(number) if number is not None else None
    except (TypeError, ValueError):
        number_i = None
    return {
        "source": "sonarr",
        "season": season_i,
        "episode": number_i,
        "title": str(episode_row.get("title") or ""),
        "episode_id": episode_row.get("id") or episode_row.get("episode_id"),
        "label": format_se(season_i, number_i) if season_i is not None and number_i is not None else "",
        "evidence": False,
    }
