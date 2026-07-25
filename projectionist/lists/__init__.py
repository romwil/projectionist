"""Named curated lists (local CuratorX shelf).

Plex Lists publish spike (2026-07): No clear public/stable API exists for
Plex Discover personal Lists (`watch.plex.tv/watchlist/my-lists`). Official
PMS docs cover Playlists and Collections; Discover exposes Watchlist
add/remove only. Third-party clients do not document a Lists CRUD surface.
Publish-to-Plex-Lists is deferred — CuratorX must not fake a broken publish.
"""

from __future__ import annotations

__all__ = ["PLEX_LISTS_PUBLISH_SUPPORTED"]

# Spike result: defer publish until Plex ships a documented personal-Lists API.
PLEX_LISTS_PUBLISH_SUPPORTED = False
