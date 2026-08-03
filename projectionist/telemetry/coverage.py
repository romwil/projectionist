"""Coverage-deficit closed-loop telemetry (P1/P2 knowledge gaps).

Fire-and-forget upserts into ``telemetry_events`` when enrichment tasks detect
missing themes, motifs, synopsis, embeddings, or metadata. Never blocks callers.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)

EVENT_COVERAGE_DEFICIT = "coverage_deficit"

VALID_DEFICIT_KINDS = frozenset(
    {
        "theme_keyword",
        "motif",
        "synopsis",
        "embedding",
        "metadata",
    }
)


def schedule_coverage_deficit(
    *,
    deficit_kind: str,
    entity_type: str,
    entity_key: str,
    priority_tier: str = "P2",
    context_source: str = "idle_task",
    extra: Optional[Mapping[str, Any]] = None,
) -> None:
    """Enqueue a ``coverage_deficit`` event (non-blocking).

    ``entity_key`` should be stable and casefolded where appropriate so
    ``hit_count`` aggregates across repeated observations.
    """
    kind = str(deficit_kind or "").strip().lower()
    etype = str(entity_type or "").strip().lower()
    key = str(entity_key or "").strip()
    if not key or kind not in VALID_DEFICIT_KINDS:
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
        "deficit_kind": kind,
        "context_source": str(context_source or "idle_task")[:80],
    }
    if extra:
        for field, value in dict(extra).items():
            field_s = str(field)
            if field_s in payload:
                continue
            payload[field_s] = value

    schedule_closed_loop_event(
        db,
        event_type=EVENT_COVERAGE_DEFICIT,
        priority_tier=tier,
        entity_type=etype,
        entity_key=key.casefold(),
        payload=payload,
    )
