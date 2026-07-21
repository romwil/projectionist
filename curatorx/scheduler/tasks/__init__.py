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
        entity_memory_enrichment,
        gap_analysis,
        health_metrics,
        keyword_theme_tagging,
        llm_logline_enrichment,
        llm_theme_tagging,
        long_synopsis_enrichment,
        metadata_enrichment,
        plot_neighbors,
        purge_candidates,
        recommendation_warmup,
        semantic_embeddings,
        summary_motifs,
        taste_refresh,
        title_relations_refresh,
        weekly_digest,
    )

    semantic_embeddings.register(scheduler)
    taste_refresh.register(scheduler)
    health_metrics.register(scheduler)
    anniversary_scanner.register(scheduler)
    recommendation_warmup.register(scheduler)
    gap_analysis.register(scheduler)
    data_retention.register(scheduler)
    entity_memory_enrichment.register(scheduler)
    metadata_enrichment.register(scheduler)
    plot_neighbors.register(scheduler)
    summary_motifs.register(scheduler)
    llm_logline_enrichment.register(scheduler)
    long_synopsis_enrichment.register(scheduler)
    title_relations_refresh.register(scheduler)
    keyword_theme_tagging.register(scheduler)
    llm_theme_tagging.register(scheduler)
    purge_candidates.register(scheduler)
    weekly_digest.register(scheduler)
