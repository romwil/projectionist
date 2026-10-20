"""Owner demand catch-up: kinship miss signals → idle enrichment priority.

When More Like This, Related titles, or a household recommendation bridge
returns empty for a title the library already cares about, write a lightweight
``telemetry_events`` row (``event_type=kinship_miss``). Idle trickle tasks
prefer those item ids on the next bounded batch.

Never blocks callers. Cap new keys so a stampede of empty shelves cannot fill
the closed-loop table.
"""

from __future__ import annotations

import logging
from typing import Any, List, Mapping, Optional, Sequence

logger = logging.getLogger(__name__)

EVENT_KINSHIP_MISS = "kinship_miss"
# Soft cap on distinct kinship_miss entity keys (new inserts only; hit bumps OK).
KINSHIP_MISS_QUEUE_CAP = 500
DEFAULT_PREFER_BATCH = 25

VALID_REASONS = frozenset(
    {
        "more_like_this_empty",
        "relations_empty",
        "bridge_zero_peers",
    }
)


def _count_kinship_miss_keys(db: Any) -> int:
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM telemetry_events
            WHERE event_type = ?
            """,
            (EVENT_KINSHIP_MISS,),
        ).fetchone()
    return int(row["c"] if row else 0)


def _entity_key_exists(db: Any, entity_key: str) -> bool:
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM telemetry_events
            WHERE event_type = ? AND entity_type = 'title' AND entity_key = ?
            LIMIT 1
            """,
            (EVENT_KINSHIP_MISS, entity_key),
        ).fetchone()
    return row is not None


def schedule_kinship_miss(
    *,
    item_id: int,
    reason: str,
    context_source: str = "discovery",
    extra: Optional[Mapping[str, Any]] = None,
) -> bool:
    """Enqueue a ``kinship_miss`` event for ``item_id`` (non-blocking).

    Returns True when a write was scheduled (or would bump an existing key),
    False when the item is invalid or the queue cap blocked a new key.
    """
    try:
        seed = int(item_id)
    except (TypeError, ValueError):
        return False
    if seed <= 0:
        return False

    cleaned_reason = str(reason or "").strip()
    if cleaned_reason not in VALID_REASONS:
        cleaned_reason = "more_like_this_empty"

    from projectionist.facets.closed_loop import resolve_closed_loop_database
    from projectionist.telemetry.ingestion import schedule_closed_loop_event

    db = resolve_closed_loop_database()
    if db is None:
        return False

    entity_key = str(seed)
    try:
        if not _entity_key_exists(db, entity_key):
            if _count_kinship_miss_keys(db) >= KINSHIP_MISS_QUEUE_CAP:
                logger.debug(
                    "kinship_miss queue at cap (%s); skip new item_id=%s",
                    KINSHIP_MISS_QUEUE_CAP,
                    seed,
                )
                return False
    except Exception:  # noqa: BLE001 — never break discovery responses
        logger.debug("kinship_miss cap check failed", exc_info=True)

    payload: dict[str, Any] = {
        "item_id": seed,
        "reason": cleaned_reason,
        "context_source": str(context_source or "discovery")[:80],
    }
    if extra:
        for field, value in dict(extra).items():
            field_s = str(field)
            if field_s in payload:
                continue
            payload[field_s] = value

    schedule_closed_loop_event(
        db,
        event_type=EVENT_KINSHIP_MISS,
        priority_tier="P2",
        entity_type="title",
        entity_key=entity_key,
        payload=payload,
    )
    return True


def preferred_item_ids(
    db: Any,
    *,
    limit: int = DEFAULT_PREFER_BATCH,
    min_hit_count: int = 1,
) -> List[int]:
    """Return library item ids from kinship_miss backlog, hottest first."""
    capped = max(1, min(int(limit), KINSHIP_MISS_QUEUE_CAP))
    try:
        signals = db.list_closed_loop_events(
            event_type=EVENT_KINSHIP_MISS,
            entity_type="title",
            min_hit_count=max(1, int(min_hit_count)),
            limit=capped,
        )
    except Exception:  # noqa: BLE001
        logger.debug("kinship_miss prefer list failed", exc_info=True)
        return []

    out: List[int] = []
    seen: set[int] = set()
    for signal in signals or ():
        raw = str(signal.get("entity_key") or "").strip()
        try:
            item_id = int(raw)
        except (TypeError, ValueError):
            continue
        if item_id <= 0 or item_id in seen:
            continue
        seen.add(item_id)
        out.append(item_id)
        if len(out) >= capped:
            break
    return out


def merge_preferred_ids(
    preferred: Sequence[int],
    fallback: Sequence[int],
    *,
    limit: int,
) -> List[int]:
    """Prefer demand ids, then fill from ``fallback``, de-duplicated."""
    capped = max(1, int(limit))
    out: List[int] = []
    seen: set[int] = set()
    for item_id in list(preferred) + list(fallback):
        try:
            cleaned = int(item_id)
        except (TypeError, ValueError):
            continue
        if cleaned <= 0 or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
        if len(out) >= capped:
            break
    return out


def prioritize_enrichment_rows(
    db: Any,
    fallback_rows: Sequence[Any],
    *,
    limit: int,
    include_item_id=None,
) -> List[Any]:
    """Put kinship-miss titles first when they still qualify for the backlog.

    ``include_item_id(db, item_id) -> Optional[row]`` returns a backlog-eligible
    row for a preferred id, or None when that title does not need this task.
    """
    capped = max(1, int(limit))
    prefer_ids = preferred_item_ids(db, limit=capped)
    if not prefer_ids or include_item_id is None:
        return list(fallback_rows)[:capped]

    out: List[Any] = []
    seen: set[int] = set()
    for item_id in prefer_ids:
        row = include_item_id(db, item_id)
        if row is None:
            continue
        try:
            rid = int(row["id"])
        except (TypeError, ValueError, KeyError, IndexError):
            continue
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
        if len(out) >= capped:
            return out

    for row in fallback_rows:
        try:
            rid = int(row["id"])
        except (TypeError, ValueError, KeyError, IndexError):
            continue
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
        if len(out) >= capped:
            break
    return out
