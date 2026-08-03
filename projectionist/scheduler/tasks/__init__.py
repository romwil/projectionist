"""Built-in idle scheduler tasks.

Each module exposes a single ``register(scheduler)`` function that registers
its :class:`TaskDefinition` with the scheduler.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from projectionist.scheduler.engine import IdleScheduler


def register_all(scheduler: IdleScheduler) -> None:
    """Register every built-in task with the scheduler."""
    from projectionist.scheduler.tasks import (
        anniversary_scanner,
        collection_gc,
        coverage_deficit_audit,
        data_retention,
        entity_memory_enrichment,
        facet_taxonomy_audit,
        gap_analysis,
        health_metrics,
        keyword_theme_tagging,
        llm_logline_enrichment,
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
        member_newsletter,
        member_weekly_rail,
        owner_monthly_curation,
        arrival_notifications,
        enthusiast_nudge,
        seasonal_rail,
        watch_history_ingest,
        year_in_review,
    )

    semantic_embeddings.register(scheduler)
    taste_refresh.register(scheduler)
    health_metrics.register(scheduler)
    anniversary_scanner.register(scheduler)
    recommendation_warmup.register(scheduler)
    gap_analysis.register(scheduler)
    data_retention.register(scheduler)
    collection_gc.register(scheduler)
    facet_taxonomy_audit.register(scheduler)
    coverage_deficit_audit.register(scheduler)
    entity_memory_enrichment.register(scheduler)
    metadata_enrichment.register(scheduler)
    plot_neighbors.register(scheduler)
    summary_motifs.register(scheduler)
    llm_logline_enrichment.register(scheduler)
    long_synopsis_enrichment.register(scheduler)
    title_relations_refresh.register(scheduler)
    keyword_theme_tagging.register(scheduler)
    purge_candidates.register(scheduler)
    weekly_digest.register(scheduler)
    member_newsletter.register(scheduler)
    member_weekly_rail.register(scheduler)
    owner_monthly_curation.register(scheduler)
    arrival_notifications.register(scheduler)
    enthusiast_nudge.register(scheduler)
    seasonal_rail.register(scheduler)
    watch_history_ingest.register(scheduler)
    year_in_review.register(scheduler)
