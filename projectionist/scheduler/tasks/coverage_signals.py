"""Helpers for idle tasks to emit closed-loop coverage deficit signals."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List, Mapping

from projectionist.library.db import Database
from projectionist.library.knowledge_fetch import (
    KIND_EMBEDDING,
    KIND_METADATA,
    KIND_SYNOPSIS,
    gap_is_open,
    list_exhausted,
)
from projectionist.library.theme_map import KEYWORD_TO_THEME, normalize_keyword, parse_keywords
from projectionist.telemetry.coverage import schedule_coverage_deficits


def _row_val(row: Any, key: str, default: Any = "") -> Any:
    keys = row.keys() if hasattr(row, "keys") else row
    if key in keys:
        return row[key]
    return default


def _keyword_maps_to_theme(keyword: str) -> bool:
    key = normalize_keyword(keyword)
    if not key:
        return False
    if key in KEYWORD_TO_THEME:
        return True
    for mapped_key in KEYWORD_TO_THEME:
        if mapped_key == key or mapped_key in key or key in mapped_key:
            return True
    return False


def emit_unmapped_keyword_signals(
    items: Iterable[Mapping[str, Any]],
    *,
    min_item_count: int = 3,
    max_emit: int = 40,
) -> int:
    """Emit P1 coverage_deficit signals for frequent TMDB keywords with no theme map."""
    counts: Counter[str] = Counter()
    for row in items:
        keys = row.keys() if hasattr(row, "keys") else row
        raw = row["keywords"] if "keywords" in keys else []
        for keyword in parse_keywords(raw):
            norm = normalize_keyword(keyword)
            if not norm or _keyword_maps_to_theme(norm):
                continue
            counts[norm] += 1

    deficits: List[Dict[str, Any]] = []
    for keyword, count in counts.most_common(max_emit):
        if count < min_item_count:
            break
        deficits.append(
            {
                "deficit_kind": "theme_keyword",
                "entity_type": "keyword",
                "entity_key": keyword,
                "priority_tier": "P1",
                "context_source": "keyword_theme_tagging",
                "extra": {"item_count": count, "keyword": keyword},
            }
        )
    schedule_coverage_deficits(deficits)
    return len(deficits)


def emit_motif_deficit_signals(
    db: Database,
    *,
    max_emit: int = 50,
) -> int:
    """Per-title motif gaps are no longer owner exceptions.

    Motifs are derived locally from plot text that is already in the library, in
    one corpus-wide pass (document-frequency thresholds). A title with plot text
    but no motif simply had no distinguishing tokens — there is nothing to fetch
    and nothing the owner can act on, and re-running the same pass cannot change
    that. Kept as a no-op so callers and ``coverage_signals`` result keys stay
    stable.
    """
    del db, max_emit
    return 0


def _emit_exhausted(
    db: Database,
    *,
    kind: str,
    context_source: str,
    limit: int,
) -> int:
    """Emit ``coverage_deficit`` only for titles whose automatic retrieval gave up."""
    rows = list_exhausted(db, kind, limit=max(1, min(int(limit), 50)))
    deficits: List[Dict[str, Any]] = []
    for row in rows:
        item_id = int(row["item_id"])
        if not gap_is_open(db, kind, item_id):
            continue
        deficits.append(
            {
                "deficit_kind": kind,
                "entity_type": "library_item",
                "entity_key": str(item_id),
                "priority_tier": "P2",
                "context_source": context_source,
                "extra": {
                    "item_id": item_id,
                    "title": str(row.get("title") or ""),
                    "tmdb_id": row.get("tmdb_id"),
                    "attempts": row.get("attempts"),
                    "failure": row.get("last_outcome"),
                    "failure_detail": row.get("last_detail"),
                    "retrieval_exhausted": True,
                },
            }
        )
    schedule_coverage_deficits(deficits)
    return len(deficits)


def emit_metadata_backlog_signals(
    db: Database,
    *,
    limit: int = 25,
) -> int:
    """Surface TMDB metadata that automatic retrieval tried and failed to fill.

    A merely-missing field is backlog the ``metadata_enrichment`` trickle works
    through; it is not signalled. Only exhausted retries reach the owner.
    """
    return _emit_exhausted(
        db, kind=KIND_METADATA, context_source="metadata_enrichment", limit=limit
    )


def emit_synopsis_backlog_signals(
    db: Database,
    *,
    limit: int = 15,
) -> int:
    """Surface plots that ``long_synopsis_enrichment`` tried and failed to fetch.

    Missing-but-not-yet-fetched plot text is backlog (fetched on the normal
    scheduled pass with backoff); it is not an exception.
    """
    return _emit_exhausted(
        db, kind=KIND_SYNOPSIS, context_source="long_synopsis_enrichment", limit=limit
    )


def emit_embedding_backlog_signals(
    db: Database,
    *,
    limit: int = 30,
) -> int:
    """Surface plot-similarity embeddings that automatic generation failed to build."""
    return _emit_exhausted(
        db, kind=KIND_EMBEDDING, context_source="semantic_embeddings", limit=limit
    )
