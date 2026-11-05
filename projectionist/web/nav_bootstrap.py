"""Stamp Live onto the HTML shell so the icon bar does not wait on SQLite.

`/api/features` and `/api/auth/me` look up the session and can sit on
``SQLITE_BUSY_TIMEOUT_MS`` (30s). The Live peer reads the feature flag and
``live_lineup.json`` only — not the library database, and not a Tunarr URL.
"""

from __future__ import annotations

from typing import Any


def live_channels_nav_ready(settings: Any) -> bool:
    """True when Live is on and Projectionist already has at least one station.

    A saved Tunarr base URL does not count. Enabled with an empty lineup stays
    out of the nav; ``/live`` can still show its empty state.
    """
    features = getattr(settings, "features", None)
    enabled = bool(getattr(features, "live_channels_enabled", False))
    if not enabled:
        return False
    from projectionist.live_channels.native_schedule import schedule_has_channels

    return schedule_has_channels(settings)


def nav_bootstrap_markup(ready: bool) -> str:
    flag = "true" if ready else "false"
    return f'<script>window.__PROJECTIONIST_NAV__={{"liveChannelsReady":{flag}}}</script>'


def inject_nav_bootstrap(html: str, *, ready: bool) -> str:
    snippet = nav_bootstrap_markup(ready)
    if "</head>" in html:
        return html.replace("</head>", f"{snippet}</head>", 1)
    return snippet + html
