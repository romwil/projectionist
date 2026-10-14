"""Stamp Live onto the HTML shell so the icon bar does not wait on SQLite.

`/api/features` and `/api/auth/me` look up the session and can sit on
``SQLITE_BUSY_TIMEOUT_MS`` (30s). The Live peer only depends on settings.
"""

from __future__ import annotations

from typing import Any


def live_channels_nav_ready(settings: Any) -> bool:
    features = getattr(settings, "features", None)
    tunarr = getattr(settings, "tunarr", None)
    enabled = bool(getattr(features, "live_channels_enabled", False))
    url = str(getattr(tunarr, "url", "") or "").strip()
    return bool(enabled and url)


def nav_bootstrap_markup(ready: bool) -> str:
    flag = "true" if ready else "false"
    return f'<script>window.__PROJECTIONIST_NAV__={{"liveChannelsReady":{flag}}}</script>'


def inject_nav_bootstrap(html: str, *, ready: bool) -> str:
    snippet = nav_bootstrap_markup(ready)
    if "</head>" in html:
        return html.replace("</head>", f"{snippet}</head>", 1)
    return snippet + html
