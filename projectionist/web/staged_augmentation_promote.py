"""Owner promote/act handlers for non-facet staged augmentations."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.scheduler.tasks.entity_memory_enrichment import (
    TASK_NAME as ENTITY_MEMORY_TASK,
    _enrich_entity,
)
from projectionist.scheduler.tasks.long_synopsis_enrichment import (
    _fetch_for_row,
    resolve_synopsis_source,
)
from projectionist.scheduler.tasks.summary_motifs import extract_motif_rows

logger = logging.getLogger(__name__)

COVERAGE_TASK = "coverage_deficit_audit"


def _parse_candidate(row: Dict[str, Any]) -> Dict[str, Any]:
    raw = row.get("candidate_data_json")
    try:
        data = json.loads(raw) if raw else {}
    except (TypeError, json.JSONDecodeError):
        data = {}
    return data if isinstance(data, dict) else {}


def act_label_for_row(row: Dict[str, Any]) -> Optional[str]:
    """Human-readable button label for a pending staged row."""
    task = str(row.get("task_name") or "")
    entity_type = str(row.get("target_entity_type") or "")
    if task == "facet_taxonomy_audit" and entity_type == "facet":
        return "Approve → overlay"
    if task == ENTITY_MEMORY_TASK:
        return "Run enrichment"
    if task == COVERAGE_TASK:
        candidate = _parse_candidate(row)
        kind = str(candidate.get("deficit_kind") or "")
        if kind == "theme_keyword":
            return "Run theme tagging"
        if kind in {"motif", "metadata", "synopsis", "embedding"}:
            return "Run enrichment"
        return "Act on gap"
    return None


def act_description_for_row(row: Dict[str, Any]) -> str:
    """Explain what the act button will do."""
    task = str(row.get("task_name") or "")
    candidate = _parse_candidate(row)
    if task == ENTITY_MEMORY_TASK:
        name = candidate.get("name") or row.get("target_entity_id")
        return f"Refresh repository-memory research for “{name}” via official APIs."
    if task == COVERAGE_TASK:
        kind = str(candidate.get("deficit_kind") or "gap")
        title = candidate.get("title") or candidate.get("keyword") or row.get("target_entity_id")
        if kind == "theme_keyword":
            return (
                f"Queue a keyword/theme tagging pass for “{title}”. "
                "Does not auto-map keywords — review mapping separately."
            )
        if kind == "motif":
            return f"Extract motif facets from plot text for “{title}”."
        if kind == "metadata":
            return f"Fetch TMDB metadata for “{title}”."
        if kind == "synopsis":
            return f"Fetch long synopsis for “{title}” (Wikipedia/OMDb per settings)."
        if kind == "embedding":
            return f"Generate semantic embedding for “{title}”."
        return f"Run the best available enrichment for this {kind} gap."
    return ""


async def _enrich_library_metadata(db: Database, settings: Settings, item_id: int) -> Dict[str, Any]:
    from projectionist.connectors.tmdb import TMDBClient
    from projectionist.library.sync import apply_tmdb_details_to_library_row

    api_key = (settings.tmdb_api_key or "").strip()
    if not api_key:
        raise HTTPException(status_code=400, detail="TMDB API key required for metadata enrichment")

    row = db.library_item_by_id(int(item_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Library item not found")

    tmdb_id = row["tmdb_id"]
    media_type = str(row["media_type"] or "")
    if not tmdb_id or media_type not in {"movie", "show"}:
        raise HTTPException(status_code=400, detail="Item lacks TMDB id for metadata enrichment")

    tmdb = TMDBClient(api_key)
    if media_type == "movie":
        details = tmdb.movie_details(int(tmdb_id))
    else:
        details = tmdb.tv_details(int(tmdb_id))

    patch: dict[str, Any] = {
        "rating_key": row["rating_key"],
        "media_type": media_type,
        "title": row["title"],
        "tmdb_id": int(tmdb_id),
    }
    for key in row.keys():
        if key in {"id", "updated_at"}:
            continue
        value = row[key]
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
    db.upsert_library_item(patch)
    return {"action": "metadata_enriched", "item_id": int(item_id)}


async def _enrich_library_motifs(db: Database, item_id: int) -> Dict[str, Any]:
    all_rows = extract_motif_rows(db)
    item_rows = [row for row in all_rows if int(row[0]) == int(item_id)]
    if not item_rows:
        return {"action": "motif_no_tokens", "item_id": int(item_id), "motifs_written": 0}

    with db.connect() as conn:
        kept = conn.execute(
            """
            SELECT item_id, facet_type, facet_value
            FROM library_facets
            WHERE facet_type = 'motif' AND item_id != ?
            """,
            (int(item_id),),
        ).fetchall()
    merged = [(int(r[0]), str(r[1]), str(r[2])) for r in kept] + list(item_rows)
    count = db.replace_facets_of_type("motif", merged)
    return {"action": "motifs_written", "item_id": int(item_id), "motifs_written": count}


async def _enrich_library_synopsis(db: Database, settings: Settings, item_id: int) -> Dict[str, Any]:
    source, skip_reason = resolve_synopsis_source(settings)
    if skip_reason:
        raise HTTPException(
            status_code=400,
            detail=f"Long synopsis source not configured ({skip_reason})",
        )

    row = db.library_item_by_id(int(item_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Library item not found")

    from projectionist.connectors.omdb import OMDbClient

    omdb = None
    omdb_key = str(getattr(settings, "omdb_api_key", "") or "").strip()
    if source in {"omdb", "auto"} and omdb_key:
        omdb = OMDbClient(omdb_key)

    synopsis, provenance = _fetch_for_row(row, source=source, omdb=omdb)
    if not synopsis:
        return {"action": "synopsis_miss", "item_id": int(item_id)}

    db.set_long_synopsis(int(item_id), synopsis, provenance)
    return {"action": "synopsis_written", "item_id": int(item_id), "provenance": provenance}


async def _enrich_library_embedding(
    db: Database, settings: Settings, item_id: int
) -> Dict[str, Any]:
    from projectionist.library.embeddings import (
        build_item_embedding_text,
        content_hash_for_text,
        embed_texts,
        embedding_model_label,
    )

    row = db.library_item_by_id(int(item_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Library item not found")

    text = build_item_embedding_text(row)
    if not text.strip():
        raise HTTPException(status_code=400, detail="Item has no embeddable plot text")

    content_hash = content_hash_for_text(text)
    vectors = await embed_texts([text], settings, db=db)
    if not vectors:
        raise HTTPException(status_code=502, detail="Embedding provider returned no vector")

    db.set_embeddings(
        [(int(item_id), vectors[0], content_hash)],
        embedding_model=embedding_model_label(settings),
    )
    return {"action": "embedding_written", "item_id": int(item_id)}


async def promote_staged_row(
    row: Dict[str, Any],
    *,
    db: Database,
    settings: Settings,
    scheduler_trigger: Optional[Callable[[str], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Execute the owner-approved action for a pending staged row."""
    task = str(row.get("task_name") or "")
    entity_type = str(row.get("target_entity_type") or "")
    entity_id = str(row.get("target_entity_id") or "").strip()
    candidate = _parse_candidate(row)

    if task == ENTITY_MEMORY_TASK:
        if entity_type not in {"title", "person", "company"}:
            raise HTTPException(status_code=400, detail="Unsupported demand entity type")
        name = str(candidate.get("name") or entity_id).strip()
        if not name:
            raise HTTPException(status_code=400, detail="Staged demand row is missing a name")
        external_ids: Dict[str, Any] = {}
        raw_tmdb = candidate.get("tmdb_id")
        if raw_tmdb is not None:
            try:
                external_ids["tmdb_id"] = int(raw_tmdb)
            except (TypeError, ValueError):
                pass
        entity = {
            "entity_type": entity_type,
            "name": name,
            "external_ids": external_ids,
        }
        if not (settings.tmdb_api_key or "").strip():
            raise HTTPException(status_code=400, detail="TMDB API key required for entity enrichment")
        attempted = _enrich_entity(settings, db, entity)
        if not attempted:
            raise HTTPException(status_code=400, detail="Could not enrich this entity type")
        return {"action": "repository_research", "entity_type": entity_type, "name": name}

    if task == COVERAGE_TASK:
        deficit_kind = str(candidate.get("deficit_kind") or "")
        if deficit_kind == "theme_keyword":
            if scheduler_trigger is None:
                raise HTTPException(status_code=503, detail="Scheduler not available")
            result = scheduler_trigger("keyword_theme_tagging")
            if result.get("status") == "busy":
                raise HTTPException(status_code=409, detail="keyword_theme_tagging already running")
            if result.get("error"):
                raise HTTPException(status_code=404, detail=str(result["error"]))
            return {
                "action": "queued_keyword_theme_tagging",
                "keyword": candidate.get("keyword") or entity_id,
                "scheduler": result,
            }

        if entity_type == "library_item":
            try:
                item_id = int(entity_id)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail="Invalid library item id") from exc

            if deficit_kind == "motif":
                return await _enrich_library_motifs(db, item_id)
            if deficit_kind == "metadata":
                return await _enrich_library_metadata(db, settings, item_id)
            if deficit_kind == "synopsis":
                return await _enrich_library_synopsis(db, settings, item_id)
            if deficit_kind == "embedding":
                return await _enrich_library_embedding(db, settings, item_id)

        raise HTTPException(
            status_code=400,
            detail=f"No safe promote path for deficit kind {deficit_kind!r}",
        )

    raise HTTPException(status_code=400, detail=f"Task {task!r} does not support promote/act")
