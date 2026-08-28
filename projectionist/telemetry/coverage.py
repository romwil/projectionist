"""Coverage-deficit closed-loop telemetry (P1/P2 knowledge gaps).

Fire-and-forget upserts into ``telemetry_events`` when enrichment tasks detect
missing themes, motifs, synopsis, embeddings, or metadata. Never blocks callers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence

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


def _build_deficit_event(deficit: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize one deficit mapping into a closed-loop event, or None if unusable."""
    kind = str(deficit.get("deficit_kind") or "").strip().lower()
    etype = str(deficit.get("entity_type") or "").strip().lower()
    key = str(deficit.get("entity_key") or "").strip()
    if not key or kind not in VALID_DEFICIT_KINDS:
        return None

    tier = str(deficit.get("priority_tier") or "P2").strip().upper()
    if tier not in {"P0", "P1", "P2", "P3"}:
        tier = "P2"

    payload: Dict[str, Any] = {
        "deficit_kind": kind,
        "context_source": str(deficit.get("context_source") or "idle_task")[:80],
    }
    extra = deficit.get("extra")
    if extra:
        for field, value in dict(extra).items():
            field_s = str(field)
            if field_s in payload:
                continue
            payload[field_s] = value

    return {
        "event_type": EVENT_COVERAGE_DEFICIT,
        "priority_tier": tier,
        "entity_type": etype,
        "entity_key": key.casefold(),
        "payload": payload,
    }


def schedule_coverage_deficits(deficits: Sequence[Mapping[str, Any]]) -> None:
    """Enqueue many ``coverage_deficit`` events as one batch (non-blocking).

    Each mapping accepts the same fields as :func:`schedule_coverage_deficit`.
    The whole batch becomes a single background job and a single SQLite write
    transaction, so a scan emitting dozens of deficits no longer floods the
    write serializer.
    """
    events: List[Dict[str, Any]] = []
    for deficit in deficits or ():
        if not deficit:
            continue
        event = _build_deficit_event(deficit)
        if event is not None:
            events.append(event)
    if not events:
        return

    from projectionist.facets.closed_loop import resolve_closed_loop_database
    from projectionist.telemetry.ingestion import schedule_closed_loop_events

    db = resolve_closed_loop_database()
    if db is None:
        return

    schedule_closed_loop_events(db, events)


def schedule_coverage_deficit(
    *,
    deficit_kind: str,
    entity_type: str,
    entity_key: str,
    priority_tier: str = "P2",
    context_source: str = "idle_task",
    extra: Optional[Mapping[str, Any]] = None,
) -> None:
    """Enqueue a single ``coverage_deficit`` event (non-blocking).

    ``entity_key`` should be stable and casefolded where appropriate so
    ``hit_count`` aggregates across repeated observations.
    """
    schedule_coverage_deficits(
        [
            {
                "deficit_kind": deficit_kind,
                "entity_type": entity_type,
                "entity_key": entity_key,
                "priority_tier": priority_tier,
                "context_source": context_source,
                "extra": extra,
            }
        ]
    )
