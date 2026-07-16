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
        data_retention,
        gap_analysis,
        health_metrics,
        llm_logline_enrichment,
        llm_theme_tagging,
        metadata_enrichment,
        plot_neighbors,
        recommendation_warmup,
        semantic_embeddings,
        summary_motifs,
        taste_refresh,
        title_relations_refresh,
    )

    semantic_embeddings.register(scheduler)
    taste_refresh.register(scheduler)
    health_metrics.register(scheduler)
    anniversary_scanner.register(scheduler)
    recommendation_warmup.register(scheduler)
    gap_analysis.register(scheduler)
    data_retention.register(scheduler)
    metadata_enrichment.register(scheduler)
    plot_neighbors.register(scheduler)
    summary_motifs.register(scheduler)
    llm_logline_enrichment.register(scheduler)
    title_relations_refresh.register(scheduler)
    llm_theme_tagging.register(scheduler)
