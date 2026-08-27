"""Normalize and validate nested theater settings."""

from __future__ import annotations

from typing import Any, Mapping

from projectionist.config_store import TheaterSettings

_ORIENTATIONS = frozenset({"landscape", "portrait"})
_AUDIENCES = frozenset({"everyone", "household"})
_IDLE_MODES = frozenset({"empty", "now_available"})
_MULTI_MODES = frozenset({"rotator", "panelled"})
_HEADER_MODES = frozenset({"dynamic", "static"})
_FEED_MODES = frozenset({"recently_added", "recently_released", "trending"})
_FEED_ALIASES = {
    "recently-added": "recently_added",
    "recentlyadded": "recently_added",
    "recent-releases": "recently_released",
    "recent_releases": "recently_released",
    "recently-released": "recently_released",
    "recentlyreleased": "recently_released",
    "popular": "trending",
}


def normalize_theater_feed(raw: str | None) -> str:
    """Lobby idle deck source — ``?feed=`` on the theater URL / SSE endpoint."""
    token = str(raw or "").strip().lower().replace("-", "_")
    token = _FEED_ALIASES.get(token, token)
    if token in _FEED_MODES:
        return token
    return "recently_added"


def normalize_theater_settings(raw: TheaterSettings | Mapping[str, Any] | None) -> TheaterSettings:
    if isinstance(raw, TheaterSettings):
        data = {
            "enabled": raw.enabled,
            "orientation": raw.orientation,
            "audience": raw.audience,
            "idle_mode": raw.idle_mode,
            "multi_mode": raw.multi_mode,
            "header_mode": raw.header_mode,
            "static_label": raw.static_label,
            "rotate_seconds": raw.rotate_seconds,
        }
    elif isinstance(raw, Mapping):
        data = dict(raw)
    else:
        data = {}

    orientation = str(data.get("orientation") or "landscape").strip().lower()
    if orientation not in _ORIENTATIONS:
        orientation = "landscape"
    audience = str(data.get("audience") or "everyone").strip().lower()
    if audience not in _AUDIENCES:
        audience = "everyone"
    idle_mode = str(data.get("idle_mode") or "empty").strip().lower()
    if idle_mode not in _IDLE_MODES:
        idle_mode = "empty"
    multi_mode = str(data.get("multi_mode") or "rotator").strip().lower()
    if multi_mode not in _MULTI_MODES:
        multi_mode = "rotator"
    header_mode = str(data.get("header_mode") or "dynamic").strip().lower()
    if header_mode not in _HEADER_MODES:
        header_mode = "dynamic"
    label = str(data.get("static_label") or "").strip()[:24]
    try:
        rotate = int(data.get("rotate_seconds") or 12)
    except (TypeError, ValueError):
        rotate = 12
    rotate = max(8, min(60, rotate))

    return TheaterSettings(
        enabled=bool(data.get("enabled")),
        orientation=orientation,
        audience=audience,
        idle_mode=idle_mode,
        multi_mode=multi_mode,
        header_mode=header_mode,
        static_label=label,
        rotate_seconds=rotate,
    )


def theater_host_port_hint() -> int:
    import os

    from projectionist.theater import DEFAULT_THEATER_PORT

    raw = (os.environ.get("PROJECTIONIST_THEATER_PORT") or "").strip()
    try:
        return int(raw) if raw else DEFAULT_THEATER_PORT
    except ValueError:
        return DEFAULT_THEATER_PORT
