"""Helpers for idle tasks to emit closed-loop coverage deficit signals."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from projectionist.library.db import Database
from projectionist.library.theme_map import KEYWORD_TO_THEME, normalize_keyword, parse_keywords
from projectionist.telemetry.coverage import schedule_coverage_deficit


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

    emitted = 0
    for keyword, count in counts.most_common(max_emit):
        if count < min_item_count:
            break
        schedule_coverage_deficit(
            deficit_kind="theme_keyword",
            entity_type="keyword",
            entity_key=keyword,
            priority_tier="P1",
            context_source="keyword_theme_tagging",
            extra={"item_count": count, "keyword": keyword},
        )
        emitted += 1
    return emitted


def emit_motif_deficit_signals(
    db: Database,
    *,
    max_emit: int = 50,
) -> int:
    """Emit P1 coverage_deficit for library items with plot text but zero motifs."""
    with db.connect() as conn:
        motif_titles = {
            int(row[0])
            for row in conn.execute(
                "SELECT DISTINCT item_id FROM library_facets WHERE facet_type = 'motif'"
            ).fetchall()
        }

    emitted = 0
    for row in db.all_library_items():
        if emitted >= max_emit:
            break
        item_id = int(row["id"])
        if item_id in motif_titles:
            continue
        keys = row.keys() if hasattr(row, "keys") else row
        parts = []
        for col in ("summary", "tmdb_overview", "tagline", "long_synopsis", "llm_logline"):
            if col in keys and str(row[col] or "").strip():
                parts.append(str(row[col]))
        if not parts:
            continue
        schedule_coverage_deficit(
            deficit_kind="motif",
            entity_type="library_item",
            entity_key=str(item_id),
            priority_tier="P1",
            context_source="summary_motifs",
            extra={
                "item_id": item_id,
                "title": str(_row_val(row, "title") or ""),
            },
        )
        emitted += 1
    return emitted


def emit_metadata_backlog_signals(
    db: Database,
    *,
    limit: int = 25,
) -> int:
    """Emit P2 metadata deficit signals for titles needing TMDB enrichment."""
    backlog = db.items_needing_metadata_enrichment(limit=limit)
    emitted = 0
    for row in backlog:
        item_id = int(row["id"])
        schedule_coverage_deficit(
            deficit_kind="metadata",
            entity_type="library_item",
            entity_key=str(item_id),
            priority_tier="P2",
            context_source="metadata_enrichment",
            extra={
                "item_id": item_id,
                "title": str(_row_val(row, "title") or ""),
                "tmdb_id": _row_val(row, "tmdb_id"),
            },
        )
        emitted += 1
    return emitted


def emit_synopsis_backlog_signals(
    db: Database,
    *,
    limit: int = 15,
) -> int:
    """Emit P2 synopsis deficit signals for titles missing long_synopsis."""
    with db.connect() as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(library_items)")}
        if "long_synopsis" not in cols:
            return 0
        rows = conn.execute(
            """
            SELECT id, title, tmdb_id
            FROM library_items
            WHERE TRIM(COALESCE(long_synopsis, '')) = ''
              AND TRIM(COALESCE(title, '')) != ''
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 50)),),
        ).fetchall()
    emitted = 0
    for row in rows:
        item_id = int(row["id"])
        schedule_coverage_deficit(
            deficit_kind="synopsis",
            entity_type="library_item",
            entity_key=str(item_id),
            priority_tier="P2",
            context_source="long_synopsis_enrichment",
            extra={
                "item_id": item_id,
                "title": str(row["title"] or ""),
                "tmdb_id": row["tmdb_id"],
            },
        )
        emitted += 1
    return emitted


def emit_embedding_backlog_signals(
    db: Database,
    *,
    limit: int = 30,
) -> int:
    """Emit P2 embedding deficit signals for items with overview but no embedding."""
    existing = set(db.embedding_content_hashes().keys())
    emitted = 0
    for row in db.all_library_items():
        if emitted >= limit:
            break
        item_id = int(row["id"])
        if item_id in existing:
            continue
        overview = str(_row_val(row, "summary") or _row_val(row, "tmdb_overview") or "").strip()
        if not overview:
            continue
        schedule_coverage_deficit(
            deficit_kind="embedding",
            entity_type="library_item",
            entity_key=str(item_id),
            priority_tier="P2",
            context_source="semantic_embeddings",
            extra={
                "item_id": item_id,
                "title": str(_row_val(row, "title") or ""),
            },
        )
        emitted += 1
    return emitted
