"""Shared watch-progress classification for library titles.

Returns one of ``unwatched`` | ``partial`` | ``watched``.

Rules
-----
**Movies**
- ``watched``: ``view_count > 0``
- ``partial``: unfinished in-progress playhead (``view_offset_ms > 0``) with
  ``view_count == 0``. Requires Plex sync of ``view_offset_ms``; when that
  field is absent CuratorX can only distinguish watched vs unwatched.
- ``unwatched``: otherwise

**Shows**
- ``watched``: ``total_episode_count > 0`` and ``unwatched_episode_count == 0``
  (``unwatched_episode_count`` must be present — ``None`` is not zero)
- ``partial``: some but not all episodes watched
  (``0 < unwatched < total``)
- When ``total_episode_count > 0`` but ``unwatched_episode_count`` is missing
  (episode progress not synced), treat as ``unwatched`` rather than inferring
  "all watched".
- When episode totals are unavailable, fall back to show-level ``view_count``
  (watched if ``> 0``, else unwatched). No honest partial without episode data.
"""

from __future__ import annotations

from typing import Any, Literal, Mapping

WatchProgressState = Literal["unwatched", "partial", "watched"]


def _as_nonneg_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def watch_progress_state(item: Mapping[str, Any] | None) -> WatchProgressState:
    """Classify a library/query/title-card mapping into a watch-progress state."""
    if not item:
        return "unwatched"

    media = str(item.get("media_type") or "").strip().lower()
    view_count = _as_nonneg_int(item.get("view_count"))
    view_offset_ms = _as_nonneg_int(item.get("view_offset_ms"))
    total = _as_nonneg_int(item.get("total_episode_count"))
    raw_unwatched = item.get("unwatched_episode_count")

    # Episode totals imply show semantics even when media_type is omitted
    # (e.g. privacy derive_watch_state payloads).
    is_show = media in {"show", "tv", "series"} or total > 0
    if is_show:
        if total > 0:
            # Missing unwatched count means episode progress was never synced;
            # do not treat None as 0 (all watched).
            if raw_unwatched is None:
                return "unwatched"
            unwatched = _as_nonneg_int(raw_unwatched)
            if unwatched == 0:
                return "watched"
            if unwatched < total:
                return "partial"
            return "unwatched"
        if view_count > 0:
            return "watched"
        return "unwatched"

    # Movies and unknown media types use movie semantics.
    if view_count > 0:
        return "watched"
    if view_offset_ms > 0:
        return "partial"
    return "unwatched"
