"""Owned Live programme candidates (LP-01).

A programming assistant's recipe list is owned ``library_query`` hits with a
playable ``rating_key``. ``discover_missing_titles`` gaps are a shopping list,
not a lineup. Publish stays in Admin — there is no MCP Live publish tool.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

GAP_REFUSE_NOTE = (
    "Gap titles from discover_missing_titles are not a Live programme. "
    "Use owned library_query hits with a playable rating_key. "
    "The owner publishes in Admin (Go on air / Rebuild)."
)

NOT_PLAYABLE_NOTE = (
    "Programme candidates must be owned library_query hits with a playable "
    "rating_key."
)


def _title_of(item: Mapping[str, Any]) -> str:
    return str(item.get("title") or item.get("name") or "").strip()


def _rating_key_of(item: Mapping[str, Any]) -> str:
    return str(item.get("rating_key") or item.get("plex_rating_key") or "").strip()


def is_gap_title(item: Mapping[str, Any]) -> bool:
    """True for discover_missing_titles-style rows (explicitly not in library)."""
    flag = item.get("in_library")
    if flag is False or flag == 0:
        return True
    return False


def is_owned_programme(item: Any) -> bool:
    """Owned, playable library hit — safe to propose as a station programme."""
    if not isinstance(item, Mapping):
        return False
    if is_gap_title(item):
        return False
    key = _rating_key_of(item)
    if not key:
        return False
    playable = item.get("playable")
    if playable is False or playable == 0:
        return False
    return True


def owned_programme_candidates(items: Sequence[Any] | None) -> Dict[str, Any]:
    """Filter a mixed candidate list down to owned playable library hits.

    Gap titles are refused with ``GAP_REFUSE_NOTE``. This does not publish a
    channel.
    """
    accepted: List[Dict[str, Any]] = []
    refused: List[Dict[str, Any]] = []
    for raw in items or []:
        if not isinstance(raw, Mapping):
            refused.append({"title": "", "reason": NOT_PLAYABLE_NOTE})
            continue
        item = dict(raw)
        title = _title_of(item)
        if is_gap_title(item):
            refused.append({"title": title, "reason": GAP_REFUSE_NOTE})
            continue
        if not is_owned_programme(item):
            refused.append({"title": title, "reason": NOT_PLAYABLE_NOTE})
            continue
        key = _rating_key_of(item)
        accepted.append(
            {
                "title": title,
                "year": item.get("year"),
                "media_type": item.get("media_type"),
                "rating_key": key,
                "playable": True,
                "in_library": True,
            }
        )
    payload: Dict[str, Any] = {
        "items": accepted,
        "refused": refused,
        "count": len(accepted),
        "published": False,
    }
    if refused and any(row.get("reason") == GAP_REFUSE_NOTE for row in refused):
        payload["error"] = GAP_REFUSE_NOTE
    return payload
