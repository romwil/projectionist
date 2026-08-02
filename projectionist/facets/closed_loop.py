"""Fire-and-forget closed-loop hooks for facet resolve misses.

Bound at web/scheduler startup via ``bind_closed_loop_database``. Resolve stays
synchronous and never waits on SQLite — ``schedule_closed_loop_event`` returns
immediately.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, Sequence

from projectionist.library.db import Database

logger = logging.getLogger(__name__)

_db_provider: Optional[Callable[[], Optional[Database]]] = None


def bind_closed_loop_database(
    provider: Optional[Callable[[], Optional[Database]]],
) -> None:
    """Register (or clear) the Database factory used for miss telemetry."""
    global _db_provider
    _db_provider = provider


def resolve_closed_loop_database() -> Optional[Database]:
    """Return the bound Database for closed-loop emits, or ``None`` if unbound."""
    if _db_provider is None:
        return None
    try:
        return _db_provider()
    except Exception:  # noqa: BLE001 — never break resolve / demand emitters
        logger.debug("Closed-loop db provider failed", exc_info=True)
        return None


# Back-compat alias used by older call sites / tests.
_resolve_db = resolve_closed_loop_database


def schedule_unmapped_facet_tokens(
    tokens: Sequence[str],
    *,
    context_source: str = "resolve",
    media_type: Optional[str] = None,
) -> None:
    """Enqueue P1 ``unmapped_token`` / ``entity_type=facet`` events (non-blocking)."""
    cleaned = [str(t).strip() for t in tokens if str(t or "").strip()]
    if not cleaned:
        return
    db = resolve_closed_loop_database()
    if db is None:
        return

    from projectionist.telemetry.ingestion import schedule_closed_loop_event

    for raw in cleaned:
        payload: dict[str, Any] = {
            "raw": raw,
            "context_source": str(context_source or "resolve"),
        }
        if media_type:
            payload["media_type"] = str(media_type)
        schedule_closed_loop_event(
            db,
            event_type="unmapped_token",
            priority_tier="P1",
            entity_type="facet",
            entity_key=raw.casefold(),
            payload=payload,
        )
