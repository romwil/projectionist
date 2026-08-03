"""Explore / feed miss telemetry for Knowledge Ops closed loop.

Fire-and-forget upserts when Explore rails or facet browse return empty or
near-empty results. Never blocks callers.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)

EVENT_EXPLORE_MISS = "explore_miss"
EVENT_BAD_NEIGHBOR = "bad_neighbor_match"


def schedule_explore_miss(
    *,
    feed_id: str,
    entity_key: str,
    priority_tier: str = "P2",
    context_source: str = "explore",
    extra: Optional[Mapping[str, Any]] = None,
) -> None:
    """Enqueue an ``explore_miss`` event when a feed or browse path is empty."""
    feed = str(feed_id or "").strip()
    key = str(entity_key or "").strip()
    if not feed or not key:
        return

    from projectionist.facets.closed_loop import resolve_closed_loop_database
    from projectionist.telemetry.ingestion import schedule_closed_loop_event

    db = resolve_closed_loop_database()
    if db is None:
        return

    tier = str(priority_tier or "P2").strip().upper()
    if tier not in {"P0", "P1", "P2", "P3"}:
        tier = "P2"

    payload: dict[str, Any] = {
        "feed_id": feed,
        "context_source": str(context_source or "explore")[:80],
    }
    if extra:
        for field, value in dict(extra).items():
            field_s = str(field)
            if field_s in payload:
                continue
            payload[field_s] = value

    schedule_closed_loop_event(
        db,
        event_type=EVENT_EXPLORE_MISS,
        priority_tier=tier,
        entity_type="feed",
        entity_key=key.casefold(),
        payload=payload,
    )


def schedule_bad_neighbor_match(
    *,
    seed_item_id: int,
    neighbor_item_id: int,
    context_source: str = "plot_lab",
    extra: Optional[Mapping[str, Any]] = None,
) -> None:
    """Record owner/member dismissal of a cached plot-neighbor edge."""
    seed = int(seed_item_id)
    neighbor = int(neighbor_item_id)
    if seed <= 0 or neighbor <= 0 or seed == neighbor:
        return

    from projectionist.facets.closed_loop import resolve_closed_loop_database
    from projectionist.telemetry.ingestion import schedule_closed_loop_event

    db = resolve_closed_loop_database()
    if db is None:
        return

    entity_key = f"{seed}:{neighbor}"
    payload: dict[str, Any] = {
        "seed_item_id": seed,
        "neighbor_item_id": neighbor,
        "context_source": str(context_source or "plot_lab")[:80],
    }
    if extra:
        for field, value in dict(extra).items():
            field_s = str(field)
            if field_s in payload:
                continue
            payload[field_s] = value

    schedule_closed_loop_event(
        db,
        event_type=EVENT_BAD_NEIGHBOR,
        priority_tier="P2",
        entity_type="neighbor_pair",
        entity_key=entity_key,
        payload=payload,
    )
