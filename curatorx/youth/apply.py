"""Apply Youth content-rating gate to library filters and payloads."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from curatorx.config_store import Settings
from curatorx.library.query import LibraryFilters
from curatorx.youth.rating_gate import (
    content_rating_allowed,
    filter_items_for_youth,
    resolve_youth_max_rating,
    youth_gate_active,
)


def apply_youth_gate_to_filters(
    filters: LibraryFilters,
    *,
    user: Any,
    settings: Settings,
) -> LibraryFilters:
    """Stamp youth_max_content_rating onto filters when the viewer is Youth."""
    if not youth_gate_active(user):
        return filters
    max_rating = resolve_youth_max_rating(settings)
    filters.youth_max_content_rating = max_rating
    return filters


def youth_max_for_user(user: Any, settings: Settings) -> Optional[str]:
    if not youth_gate_active(user):
        return None
    return resolve_youth_max_rating(settings)


def filter_payload_for_youth(
    payload: Any,
    *,
    user: Any,
    settings: Settings,
) -> Any:
    """Recursively filter item lists in feed/query payloads for Youth viewers."""
    max_rating = youth_max_for_user(user, settings)
    if max_rating is None:
        return payload
    return _filter_value(payload, max_rating=max_rating)


def title_allowed_for_user(
    detail: Mapping[str, Any] | Any,
    *,
    user: Any,
    settings: Settings,
) -> bool:
    max_rating = youth_max_for_user(user, settings)
    if max_rating is None:
        return True
    rating = (
        detail.get("content_rating")
        if isinstance(detail, Mapping)
        else getattr(detail, "content_rating", "")
    )
    return content_rating_allowed(rating, max_rating=max_rating)


def _filter_value(value: Any, *, max_rating: str) -> Any:
    if isinstance(value, list):
        if value and all(isinstance(item, Mapping) for item in value):
            # Prefer content_rating key when present; otherwise leave list alone
            # (not every list is a title list).
            if any("content_rating" in item or "rating_key" in item for item in value):
                return filter_items_for_youth(value, max_rating=max_rating)
        return [_filter_value(item, max_rating=max_rating) for item in value]
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, child in value.items():
            if key in {"items", "results", "titles", "cards"} and isinstance(child, list):
                out[key] = filter_items_for_youth(child, max_rating=max_rating)
                if key == "items" and "total" in value and isinstance(value.get("total"), int):
                    out["total"] = len(out[key])
            else:
                out[key] = _filter_value(child, max_rating=max_rating)
        return out
    return value


def filter_cards_for_youth(
    cards: Sequence[Mapping[str, Any]],
    *,
    user: Any,
    settings: Settings,
) -> List[Dict[str, Any]]:
    max_rating = youth_max_for_user(user, settings)
    if max_rating is None:
        return [dict(c) for c in cards]
    return filter_items_for_youth(cards, max_rating=max_rating)
