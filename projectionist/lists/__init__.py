"""Named curated lists (local Projectionist shelf).

**Status: Future for Plex Lists publish.** Local list CRUD ships via the agent
and UI. Plex Discover personal Lists (`watch.plex.tv/watchlist/my-lists`) have
no clear public/stable API — PMS docs cover Playlists and Collections; Discover
exposes Watchlist add/remove only. Publish-to-Plex-Lists stays deferred — we
must not fake a broken publish.

Product narrative is ambient / chat-first; lenses remain an internal/advanced
agent context mechanism, not a parallel product surface.
"""

from __future__ import annotations

__all__ = ["PLEX_LISTS_PUBLISH_SUPPORTED"]

# Spike result: defer publish until Plex ships a documented personal-Lists API.
PLEX_LISTS_PUBLISH_SUPPORTED = False
