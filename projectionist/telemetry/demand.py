"""P2 metadata-demand telemetry helpers (Phase C pilot).

Fire-and-forget upserts into ``telemetry_events`` for sparse / stale repository
memory. Uses the same Database bind as facet closed-loop
(``facets.closed_loop.bind_closed_loop_database``). Never blocks callers.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)

EVENT_METADATA_DEMAND = "metadata_demand"
VALID_ENTITY_TYPES = frozenset({"title", "person", "company"})


def schedule_metadata_demand(
    *,
    entity_type: str,
    name: str,
    reason: str = "sparse_or_stale",
    entity_id: Optional[str] = None,
    context_source: str = "recall",
    extra: Optional[Mapping[str, Any]] = None,
) -> None:
    """Enqueue a P2 ``metadata_demand`` event (non-blocking).

    ``entity_key`` is ``name`` casefolded so hit_count aggregates across recalls.
    Optional ``entity_id`` is stored in the payload for enrichment lookup.
    """
    cleaned_name = str(name or "").strip()
    kind = str(entity_type or "").strip().lower()
    if not cleaned_name or kind not in VALID_ENTITY_TYPES:
        return

    from projectionist.facets.closed_loop import resolve_closed_loop_database
    from projectionist.telemetry.ingestion import schedule_closed_loop_event

    db = resolve_closed_loop_database()
    if db is None:
        return

    payload: dict[str, Any] = {
        "name": cleaned_name,
        "reason": str(reason or "sparse_or_stale")[:80],
        "context_source": str(context_source or "recall")[:80],
    }
    eid = str(entity_id or "").strip()
    if eid:
        payload["entity_id"] = eid
    if extra:
        for key, value in dict(extra).items():
            key_s = str(key)
            if key_s in payload or key_s in {"name", "entity_id", "reason", "context_source"}:
                continue
            payload[key_s] = value

    schedule_closed_loop_event(
        db,
        event_type=EVENT_METADATA_DEMAND,
        priority_tier="P2",
        entity_type=kind,
        entity_key=cleaned_name.casefold(),
        payload=payload,
    )
