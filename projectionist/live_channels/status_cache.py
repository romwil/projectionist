"""SWR wrapper for the owner Live Channels status (Admin overview / Live tab).

``build_live_channels_status`` fans out to Tunarr, Plex, XMLTV, Docker, and the
guide — dozens of sequential network calls with 5–20s timeouts. Admin used to run
that on every open. Now:

* the last good status is served immediately (durable across restarts),
* the cheap, volatile ``job`` block is always overlaid live (progress polling),
* a background worker recomputes; ``stale`` / ``warming`` tell the client to
  re-poll briefly.

The warming skeleton is hand-built — it must never call ``build_live_channels_status``,
even with blanked URLs, because that path still hits Docker inspect when
orchestration is on.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from projectionist.live_channels.status import _live_job_snapshot, build_live_channels_status
from projectionist.swr_cache import SwrCache

logger = logging.getLogger(__name__)

STATUS_SOFT_TTL_SECONDS = 30.0
STATUS_HARD_TTL_SECONDS = 24 * 3600.0
STATUS_COLD_WAIT_SECONDS = 1.0

STATUS_CACHE = SwrCache(
    "admin_live_status",
    soft_ttl=STATUS_SOFT_TTL_SECONDS,
    hard_ttl=STATUS_HARD_TTL_SECONDS,
    durable=True,
)


def invalidate_live_status_cache() -> None:
    STATUS_CACHE.invalidate()


def _key(settings: Any) -> str:
    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    enabled = bool(getattr(getattr(settings, "features", None), "live_channels_enabled", False))
    return f"enabled={int(enabled)}|url={url}"


def _warming_status(settings: Any) -> Dict[str, Any]:
    """Probe-free skeleton with the same shape the Admin UI expects."""
    from projectionist.live_channels.docker import orchestration_enabled

    tunarr = getattr(settings, "tunarr", None)
    real_url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    enabled = bool(getattr(getattr(settings, "features", None), "live_channels_enabled", False))
    image_tag = str(getattr(tunarr, "image_tag", "") or "").strip() if tunarr else ""
    return {
        "live_channels_enabled": enabled,
        "broadcast": {
            "sidecar_up": False,
            "channel_count": 0,
            "last_publish_at": None,
            "last_error": "",
            "airing_count": 0,
            "stream_connections": 0,
            "lineup_playable": False,
            "xmltv_programme_count": 0,
            "guide_ok": False,
            "tuner_alive": False,
        },
        "channels": [],
        "channel_count": 0,
        "airing": [],
        "now_playing": [],
        "sessions": {"total_connections": 0, "channels": []},
        "guide_status": {},
        "guide_index": {
            "xmltv_url": "",
            "xmltv": {"ok": False},
            "tunarr_guide_status": {},
            "media_libraries": {"ok": False, "libraries": []},
            "lineup": {
                "channel_count": 0,
                "filled_count": 0,
                "empty_count": 0,
                "channels": [],
                "playable": False,
            },
            "plex_livetv": {},
            "ready_for_plex": False,
            "owner_hint": "Checking Live Channels status…",
        },
        "continuity": {"ok": False, "path_count": 0, "checks": []},
        "last_publish_at": None,
        "last_error": "",
        "tunarr": {
            "url": real_url,
            "url_configured": bool(real_url),
            "image_tag": image_tag or "chrisbenincasa/tunarr:1.3.9",
            "docker_orchestration": orchestration_enabled(settings),
            "docker_socket_available": False,
            "reachability": {
                "reachable": False,
                "error": "Checking Live Channels status…",
                "checking": True,
            },
            "docker": {"status": "checking", "ok": True, "message": "Checking…"},
            "plex_pass_confirmed": bool(getattr(tunarr, "plex_pass_confirmed", False))
            if tunarr
            else False,
            "volume_path": str(getattr(tunarr, "volume_path", "") or "tunarr") if tunarr else "tunarr",
            "channel_number_base": int(getattr(tunarr, "channel_number_base", 100) or 100)
            if tunarr
            else 100,
            "filler_binds": list(getattr(tunarr, "filler_binds", None) or []) if tunarr else [],
            "media_binds": list(getattr(tunarr, "media_binds", None) or []) if tunarr else [],
            "pad_flex_max_minutes": int(getattr(tunarr, "pad_flex_max_minutes", 15) or 15)
            if tunarr
            else 15,
            "last_guide_attach_at": None,
            "last_guide_attach_ok": False,
            "last_guide_attach_message": "",
            "last_guide_attach_dvr_key": None,
        },
        "icon_probe": {"ok": False, "url": "", "message": ""},
        "plex_pass": {"ok": False, "confirmed": False},
        "stream_warm": {"kept_hot": 0, "last_run_at": None, "ok": None, "message": ""},
        "job": {"busy": False},
        "warming": True,
    }


def get_live_channels_status(
    settings: Any,
    db: Optional[Any] = None,
    *,
    fresh: bool = False,
    cold_wait: float = STATUS_COLD_WAIT_SECONDS,
) -> Dict[str, Any]:
    """Cached owner status. ``fresh=True`` forces a synchronous rebuild."""
    key = _key(settings)
    if fresh:
        payload = STATUS_CACHE.refresh_now(key, lambda: build_live_channels_status(settings), db=db)
        out = dict(payload)
        out.update({"cached": False, "stale": False, "warming": False})
    else:
        result = STATUS_CACHE.get(
            key,
            lambda: build_live_channels_status(settings),
            db=db,
            warming=lambda: _warming_status(settings),
            cold_wait=cold_wait,
        )
        out = result.annotated()
    # Job progress is cheap and must never lag (publish / refill polling).
    try:
        out["job"] = _live_job_snapshot()
    except Exception:  # noqa: BLE001
        logger.debug("live job overlay failed", exc_info=True)
    return out


def prewarm_live_channels_status(settings: Any, db: Optional[Any] = None) -> None:
    features = getattr(settings, "features", None)
    if not bool(getattr(features, "live_channels_enabled", False)):
        return
    try:
        STATUS_CACHE.refresh_now(_key(settings), lambda: build_live_channels_status(settings), db=db)
    except Exception:  # noqa: BLE001
        logger.debug("live status prewarm skipped", exc_info=True)


# ---------------------------------------------------------------- craft options
CRAFT_CACHE = SwrCache(
    "admin_live_craft_options",
    soft_ttl=60.0,
    hard_ttl=24 * 3600.0,
    durable=False,
)


def get_craft_options(settings: Any, db: Any, *, owner_user_id: str) -> Dict[str, Any]:
    """Craft-form pickers without Tunarr / Plex round-trips on the request path."""
    from projectionist.live_channels.craft import build_craft_options
    from projectionist.live_channels.publish import tunarr_client_from_settings

    key = f"{_key(settings)}|owner={owner_user_id}"

    def _build() -> Dict[str, Any]:
        existing_numbers: list[int] = []
        if settings.features.live_channels_enabled and str(settings.tunarr.url or "").strip():
            try:
                client = tunarr_client_from_settings(settings)
                for ch in client.list_channels():
                    if isinstance(ch, dict) and ch.get("number") is not None:
                        existing_numbers.append(int(ch["number"]))
            except Exception:  # noqa: BLE001
                existing_numbers = []
        return build_craft_options(
            db,
            settings=settings,
            owner_user_id=owner_user_id,
            existing_channel_numbers=existing_numbers,
        )

    def _warming() -> Dict[str, Any]:
        # No Tunarr / Plex lookups: library-only pickers so the form still renders.
        skeleton = build_craft_options(
            db,
            settings=None,
            owner_user_id=owner_user_id,
            existing_channel_numbers=[],
        )
        skeleton["warming"] = True
        return skeleton

    result = CRAFT_CACHE.get(key, _build, warming=_warming, cold_wait=STATUS_COLD_WAIT_SECONDS)
    return result.annotated()
