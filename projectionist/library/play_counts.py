"""Effective play counts for library titles (movies vs TV episode rollups)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from projectionist.library.db import Database

# SQL expression on bare ``library_items`` (no alias) for filters/sorts.
EFFECTIVE_VIEW_COUNT_SQL = """
CASE
  WHEN media_type = 'show' AND COALESCE(total_episode_count, 0) > 0 THEN (
    SELECT COALESCE(SUM(COALESCE(view_count, 0)), 0)
    FROM library_episodes
    WHERE show_item_id = library_items.id
  )
  ELSE COALESCE(view_count, 0)
END
"""

_EPISODE_PLAY_SUM_SUBQUERY = """
SELECT show_item_id, SUM(COALESCE(view_count, 0)) AS episode_play_sum
FROM library_episodes
GROUP BY show_item_id
"""


def library_items_with_episode_plays_select(*, alias: str = "li") -> str:
    """SELECT list joining episode play sums for shows."""
    a = alias
    return f"""
SELECT {a}.*, ep.episode_play_sum
FROM library_items {a}
LEFT JOIN ({_EPISODE_PLAY_SUM_SUBQUERY}) ep
  ON ep.show_item_id = {a}.id AND {a}.media_type = 'show'
"""


def _as_nonneg_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _row_get(item: Mapping[str, Any], key: str, default: Any = None) -> Any:
    if hasattr(item, "get"):
        return item.get(key, default)
    try:
        return item[key]
    except (KeyError, IndexError, TypeError):
        return default


def effective_view_count(item: Mapping[str, Any]) -> int:
    """Play count for agents/UI: movies use show/movie view_count; shows use episode play sum when synced."""
    media = str(_row_get(item, "media_type") or "").strip().lower()
    show_level = _as_nonneg_int(_row_get(item, "view_count"))
    if media != "show":
        return show_level
    total_eps = _as_nonneg_int(_row_get(item, "total_episode_count"))
    if total_eps <= 0:
        return show_level
    keys = item.keys() if hasattr(item, "keys") else item
    if "episode_play_sum" in keys and _row_get(item, "episode_play_sum") is not None:
        return _as_nonneg_int(_row_get(item, "episode_play_sum"))
    return show_level


def watched_episode_count(item: Mapping[str, Any]) -> int:
    total = _as_nonneg_int(_row_get(item, "total_episode_count"))
    raw_unwatched = _row_get(item, "unwatched_episode_count")
    if total <= 0 or raw_unwatched is None:
        return 0
    return max(0, total - _as_nonneg_int(raw_unwatched))


def enrich_rows_with_episode_play_sums(
    db: Database, rows: Sequence[Mapping[str, Any]]
) -> List[Dict[str, Any]]:
    """Attach ``episode_play_sum`` for synced shows (batch, avoids N+1)."""
    show_ids = [
        int(row["id"])
        for row in rows
        if str(_row_get(row, "media_type") or "") == "show"
        and _as_nonneg_int(_row_get(row, "total_episode_count")) > 0
    ]
    sums = db.show_episode_play_sums(show_ids) if show_ids else {}
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        if str(item.get("media_type") or "") == "show":
            show_id = int(item["id"])
            if show_id in sums:
                item["episode_play_sum"] = sums[show_id]
        enriched.append(item)
    return enriched
