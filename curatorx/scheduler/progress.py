"""Library/backlog progress helpers for scheduled-task ETA estimates."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Protocol

from curatorx.library.db import Database


class _HasProgress(Protocol):
    items_per_cycle: Optional[int]
    progress_scope: Optional[str]


def count_remaining(db: Database, scope: Optional[str]) -> Optional[int]:
    """Return remaining items for a known progress scope, or None if unknown."""
    if not scope:
        return None
    if scope == "metadata_backlog":
        return db.count_items_needing_metadata_enrichment()
    if scope == "llm_logline_backlog":
        return db.count_items_needing_llm_logline()
    if scope == "embeddings_pending":
        return db.count_items_needing_embeddings()
    if scope == "embeddings_pass":
        return db.count_embeddings()
    return None


def estimate_progress(
    *,
    remaining: Optional[int],
    items_per_cycle: Optional[int],
    interval_seconds: int,
    library_size: int,
    scope: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Build a progress/ETA payload for trickle tasks.

    ``estimated_seconds`` assumes one cycle every ``interval_seconds`` and that
    each cycle processes ``items_per_cycle`` items (idle time ignored).
    """
    if items_per_cycle is None or items_per_cycle <= 0 or remaining is None:
        return None
    remaining = max(0, int(remaining))
    per_cycle = max(1, int(items_per_cycle))
    cycles = 0 if remaining == 0 else int(math.ceil(remaining / per_cycle))
    interval = max(60, int(interval_seconds or 60))
    scope_labels = {
        "metadata_backlog": "titles still missing TMDB dates/plot",
        "llm_logline_backlog": "titles still needing an LLM logline",
        "embeddings_pending": "titles with plot text still needing embeddings",
        "embeddings_pass": "embedded titles in one full neighbor pass",
    }
    return {
        "scope": scope,
        "scope_label": scope_labels.get(scope or "", "remaining work"),
        "remaining_items": remaining,
        "items_per_cycle": per_cycle,
        "library_size": int(library_size),
        "estimated_cycles": cycles,
        "estimated_seconds": cycles * interval,
    }


def progress_for_definition(
    db: Database,
    defn: Optional[_HasProgress],
    *,
    interval_seconds: int,
) -> Optional[Dict[str, Any]]:
    """Resolve progress for a registered task definition."""
    if defn is None or defn.items_per_cycle is None:
        return None
    library_size = int(db.library_counts().get("items") or 0)
    remaining = count_remaining(db, defn.progress_scope)
    return estimate_progress(
        remaining=remaining,
        items_per_cycle=defn.items_per_cycle,
        interval_seconds=interval_seconds,
        library_size=library_size,
        scope=defn.progress_scope,
    )
