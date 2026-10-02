"""Built-in idle scheduler tasks.

Each module exposes a single ``register(scheduler)`` function that registers
its :class:`TaskDefinition` with the scheduler.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from projectionist.scheduler.engine import IdleScheduler


# Tasks removed from the registry because nothing consumed their output.
# ``register_all`` deletes their persisted state/history so Admin → Tasks does
# not keep showing an unregistered ghost row forever.
#
# * ``recommendation_warmup`` — wrote ``cached_recommendations``; no API, agent
#   tool, or UI ever read it, yet it loaded the whole library every 12h.
# * ``health_metrics`` — wrote ``cached_health_metrics``; ``/api/library/health``
#   never read it (it computes live / via the SWR cache), so each run only
#   duplicated that scan.
RETIRED_TASKS: tuple[str, ...] = ("health_metrics", "recommendation_warmup")


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
        keyword_theme_tagging,
        llm_logline_enrichment,
        long_synopsis_enrichment,
        metadata_enrichment,
        plot_neighbors,
        purge_candidates,
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
        whisper_inbox,
        seasonal_rail,
        watch_history_ingest,
        weekly_letter,
        year_in_review,
    )

    semantic_embeddings.register(scheduler)
    taste_refresh.register(scheduler)
    anniversary_scanner.register(scheduler)
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
    whisper_inbox.register(scheduler)
    seasonal_rail.register(scheduler)
    watch_history_ingest.register(scheduler)
    weekly_letter.register(scheduler)
    year_in_review.register(scheduler)

    scheduler.retire_tasks(RETIRED_TASKS)
