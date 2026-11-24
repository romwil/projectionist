"""Keep household responses out of a shared cache (SEC-021).

Art, playlists, segments, subtitles, avatars, and every other ``/api/``
response are private. A route may keep ``private, max-age=…`` when a
browser cache is useful. Content-addressed frontend files are not ``/api/``
and stay public.
"""

from __future__ import annotations

PRIVATE_NO_STORE = "private, no-store"


def cache_control_is_private(value: str) -> bool:
    """True when a shared cache is already told not to store this response."""
    lowered = str(value or "").lower()
    if "private" not in lowered:
        return False
    return "no-store" in lowered or "max-age=" in lowered


def apply_private_api_cache(path: str, headers) -> None:
    """Set ``private, no-store`` on an ``/api/`` response that is not already private."""
    if not str(path or "").startswith("/api/"):
        return
    current = headers.get("cache-control") or ""
    if cache_control_is_private(current):
        return
    headers["cache-control"] = PRIVATE_NO_STORE
