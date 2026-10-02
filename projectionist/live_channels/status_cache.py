"""SWR wrapper for the owner Live Channels status (Admin overview / Live tab).

``build_live_channels_status`` fans out to Tunarr, Plex, XMLTV, Docker, and the
guide — dozens of sequential network calls with 5–20s timeouts. Admin used to run
that on every open. Now:

* the last good status is served immediately (durable across restarts),
* the cheap, volatile ``job`` block is always overlaid live (progress polling),
* a background worker recomputes; ``stale`` / ``warming`` tell the client to
  re-poll briefly.
"""

from __future__ import annotations

import copy
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
    """Probe-free skeleton with the same shape as the real status."""
    tunarr = getattr(settings, "tunarr", None)
    real_url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    quiet = copy.deepcopy(settings)
    try:
        quiet.tunarr.url = ""
        quiet.tunarr.public_url = ""
        quiet.plex_url = ""
        quiet.plex_token = ""
    except Exception:  # noqa: BLE001
        pass
    skeleton = build_live_channels_status(quiet)
    block = skeleton.get("tunarr")
    if isinstance(block, dict):
        block["url"] = real_url
        block["url_configured"] = bool(real_url)
        block["reachability"] = {
            "reachable": False,
            "error": "Checking Live Channels status…",
            "checking": True,
        }
    skeleton["warming"] = True
    return skeleton


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
