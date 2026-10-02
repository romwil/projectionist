"""SWR caches for expensive library-derived dashboards.

``compute_knowledge_coverage`` and ``compute_library_health`` scan the whole
library. ``/api/library/stats`` runs on **every app shell load** and Admin runs
both on open, so they used to recompute on the first-paint request path.

They now serve from memory + durable ``sync_state`` and refresh in the
background; library sync rebuilds them off the request path so a post-sync
refetch already sees fresh numbers.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from projectionist.swr_cache import SwrCache

logger = logging.getLogger(__name__)

DERIVED_SOFT_TTL_SECONDS = 120.0
DERIVED_HARD_TTL_SECONDS = 7 * 24 * 3600.0
DERIVED_COLD_WAIT_SECONDS = 0.75

COVERAGE_CACHE = SwrCache(
    "library_coverage",
    soft_ttl=DERIVED_SOFT_TTL_SECONDS,
    hard_ttl=DERIVED_HARD_TTL_SECONDS,
    durable=True,
)
HEALTH_CACHE = SwrCache(
    "library_health",
    soft_ttl=DERIVED_SOFT_TTL_SECONDS,
    hard_ttl=DERIVED_HARD_TTL_SECONDS,
    durable=True,
)


def _key(db: Any) -> str:
    return f"{getattr(db, 'path', '')}|all"


def _warming_coverage() -> Dict[str, Any]:
    return {"warming": True}


def get_knowledge_coverage(db: Any, *, cold_wait: float = DERIVED_COLD_WAIT_SECONDS) -> Dict[str, Any]:
    from projectionist.library.query import compute_knowledge_coverage

    result = COVERAGE_CACHE.get(
        _key(db),
        lambda: compute_knowledge_coverage(db),
        db=db,
        warming=_warming_coverage,
        cold_wait=cold_wait,
    )
    return result.annotated()


def get_library_health(db: Any, *, cold_wait: float = DERIVED_COLD_WAIT_SECONDS) -> Dict[str, Any]:
    from projectionist.library.health import compute_library_health

    result = HEALTH_CACHE.get(
        _key(db),
        lambda: compute_library_health(db),
        db=db,
        warming=lambda: {"warming": True},
        cold_wait=cold_wait,
    )
    return result.annotated()


def rebuild_after_library_change(db: Any) -> None:
    """Rebuild derived dashboards synchronously on the *sync worker* thread."""
    from projectionist.library.health import compute_library_health
    from projectionist.library.query import compute_knowledge_coverage

    try:
        COVERAGE_CACHE.put(_key(db), compute_knowledge_coverage(db), db=db)
    except Exception:  # noqa: BLE001
        COVERAGE_CACHE.invalidate()
        logger.debug("coverage rebuild after sync failed", exc_info=True)
    try:
        HEALTH_CACHE.put(_key(db), compute_library_health(db), db=db)
    except Exception:  # noqa: BLE001
        HEALTH_CACHE.invalidate()
        logger.debug("health rebuild after sync failed", exc_info=True)
    try:
        from projectionist.journey.exploration import prewarm_journey

        prewarm_journey(db)
    except Exception:  # noqa: BLE001
        logger.debug("journey rebuild after sync failed", exc_info=True)
