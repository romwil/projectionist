"""Built-in idle scheduler tasks.

Each module exposes a single ``register(scheduler)`` function that registers
its :class:`TaskDefinition` with the scheduler.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from curatorx.scheduler.engine import IdleScheduler


def register_all(scheduler: IdleScheduler) -> None:
    """Register every built-in task with the scheduler."""
    from curatorx.scheduler.tasks import (
        anniversary_scanner,
        gap_analysis,
        health_metrics,
        recommendation_warmup,
        semantic_embeddings,
        taste_refresh,
    )

    semantic_embeddings.register(scheduler)
    taste_refresh.register(scheduler)
    health_metrics.register(scheduler)
    anniversary_scanner.register(scheduler)
    recommendation_warmup.register(scheduler)
    gap_analysis.register(scheduler)
