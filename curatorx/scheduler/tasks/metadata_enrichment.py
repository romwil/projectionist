"""Idle trickle: backfill missing TMDB release/air dates and credits.

Library sync already enriches new/rescanned titles.  This task catches older
rows that have a ``tmdb_id`` but empty ``release_date`` / ``first_air_date``
(added before Wave 1 metadata enrichment).

Design constraints (homelab-friendly):
- Small batches per run (default 25) so we never hammer TMDB.
- Short sleep between requests to stay under free-tier rate limits.
- Respects ``should_stop`` for clean idle-scheduler interruption.
- Never invents dates from ``year`` — only writes what TMDB returns.

Default interval: 6 hours.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Dict

from curatorx.config_store import Settings
from curatorx.connectors.tmdb import TMDBClient
from curatorx.library.db import Database
from curatorx.library.sync import apply_tmdb_details_to_library_row
from curatorx.scheduler.engine import IdleScheduler, TaskDefinition
from curatorx.scheduler.run_log import emit_task_event

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 21600  # 6 hours
DEFAULT_BATCH_SIZE = 25
# Pause between TMDB detail calls (~40 req/min with headroom for other traffic).
REQUEST_PAUSE_SECONDS = 1.5


async def run(
    db: Database, settings: Settings, should_stop: Callable[[], bool]
) -> Dict[str, Any]:
    if should_stop():
        return {"status": "interrupted", "enriched": 0}

    api_key = (settings.tmdb_api_key or "").strip()
    if not api_key:
        return {"status": "skipped", "reason": "no_tmdb_api_key", "enriched": 0}

    batch_size = DEFAULT_BATCH_SIZE
    backlog = db.items_needing_metadata_enrichment(limit=batch_size)
    if not backlog:
        return {"status": "completed", "enriched": 0, "remaining": 0}

    tmdb = TMDBClient(api_key)
    enriched = 0
    errors = 0
    emit_task_event(f"Enriching metadata for {len(backlog)} titles", batch_size=len(backlog))

    for idx, row in enumerate(backlog):
        if should_stop():
            return {
                "status": "interrupted",
                "enriched": enriched,
                "errors": errors,
            }

        tmdb_id = row["tmdb_id"]
        media_type = str(row["media_type"] or "")
        if not tmdb_id or media_type not in {"movie", "show"}:
            continue

        try:
            if media_type == "movie":
                details = tmdb.movie_details(int(tmdb_id))
            else:
                details = tmdb.tv_details(int(tmdb_id))
        except RuntimeError as error:
            errors += 1
            logger.debug(
                "Metadata trickle: TMDB fetch failed id=%s tmdb_id=%s: %s",
                row["id"],
                tmdb_id,
                error,
            )
            await asyncio.sleep(REQUEST_PAUSE_SECONDS)
            continue

        patch: dict[str, Any] = {
            "rating_key": row["rating_key"],
            "media_type": media_type,
            "title": row["title"],
            "tmdb_id": int(tmdb_id),
        }
        # Load the full row so upsert does not blank JSON fields we are not refreshing.
        existing = db.library_item_by_id(int(row["id"]))
        if existing is not None:
            for key in existing.keys():
                if key in {"id", "updated_at"}:
                    continue
                value = existing[key]
                if key in {
                    "genres",
                    "cast",
                    "directors",
                    "keywords",
                    "countries",
                    "networks",
                    "production_companies",
                }:
                    try:
                        patch[key] = json.loads(value) if value else []
                    except (TypeError, json.JSONDecodeError):
                        patch[key] = []
                else:
                    patch[key] = value

        apply_tmdb_details_to_library_row(
            patch,
            dict(details),
            media_type=media_type,
            tmdb_client=tmdb,
        )
        # Re-upsert by rating_key so COALESCE paths keep prior non-empty fields.
        db.upsert_library_item(patch)
        enriched += 1
        if enriched == 1 or enriched % 5 == 0:
            emit_task_event(
                f"Enriched {enriched}/{len(backlog)}",
                enriched=enriched,
                errors=errors,
            )

        if idx + 1 < len(backlog):
            await asyncio.sleep(REQUEST_PAUSE_SECONDS)

    remaining = len(db.items_needing_metadata_enrichment(limit=1))
    logger.info(
        "Metadata enrichment trickle: enriched=%s errors=%s remaining_sample=%s",
        enriched,
        errors,
        remaining,
    )
    return {
        "status": "completed",
        "enriched": enriched,
        "errors": errors,
        "batch_size": batch_size,
        "has_more": remaining > 0,
    }


def register(scheduler: IdleScheduler) -> None:
    scheduler.register(
        TaskDefinition(
            name="metadata_enrichment",
            run_interval_seconds=INTERVAL_SECONDS,
            enabled=True,
            run_fn=run,
            description=(
                "Trickles through titles that have a TMDB id but still lack release/air "
                f"dates or plot text. Processes about {DEFAULT_BATCH_SIZE} titles per run "
                "with paced TMDB requests so free-tier limits stay safe."
            ),
            items_per_cycle=DEFAULT_BATCH_SIZE,
            progress_scope="metadata_backlog",
        )
    )
