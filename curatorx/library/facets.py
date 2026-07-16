"""Facet index and FTS rebuild for library intelligence queries."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from curatorx.library.db import Database

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str, int, int, str], None]]


def _parse_json_list(raw: Any) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(v).strip() for v in raw if str(v).strip()]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(v).strip() for v in parsed if str(v).strip()]
    return []


def _country_values_from_row(row: Mapping[str, Any]) -> List[str]:
    return _parse_json_list(row["countries"] if "countries" in row.keys() else [])


def _language_value_from_row(row: Mapping[str, Any]) -> str:
    if "original_language" not in row.keys():
        return ""
    return str(row["original_language"] or "").strip()


def _facet_catalog_from_items(db: Database, facet_type: str, *, limit: int) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for row in db.all_library_items():
        if facet_type == "country":
            for value in _country_values_from_row(row):
                counts[value] = counts.get(value, 0) + 1
        elif facet_type == "language":
            value = _language_value_from_row(row)
            if value:
                counts[value] = counts.get(value, 0) + 1
    facets = [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]
    return {"facet_type": facet_type, "facets": facets, "returned": len(facets)}


def ensure_library_facet_index(db: Database) -> int:
    """Rebuild facets when item columns have country/language data but the facet index does not."""
    with db.connect() as conn:
        country_facet_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM library_facets WHERE facet_type = 'country'"
        ).fetchone()["cnt"]
        language_facet_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM library_facets WHERE facet_type = 'language'"
        ).fetchone()["cnt"]
        items_with_countries = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM library_items
            WHERE countries IS NOT NULL AND countries != '' AND countries != '[]'
            """
        ).fetchone()["cnt"]
        items_with_language = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM library_items
            WHERE original_language IS NOT NULL AND original_language != ''
            """
        ).fetchone()["cnt"]
    needs_rebuild = (
        (items_with_countries > 0 and country_facet_count == 0)
        or (items_with_language > 0 and language_facet_count == 0)
    )
    if not needs_rebuild:
        return 0
    return rebuild_library_facets(db)


def _emit_rebuild_progress(
    progress: ProgressCallback,
    *,
    message: str,
    current: int,
    total: int,
    last_log: list[float],
    log_label: str,
    force: bool = False,
) -> None:
    now = time.time()
    should_emit = force or current <= 1 or current >= total or current % 50 == 0 or (now - last_log[0]) >= 3.0
    if not should_emit:
        return
    if progress:
        progress("indexing", current, max(total, 1), message)
    if force or now - last_log[0] >= 3.0 or current <= 1 or current >= total:
        logger.info("Library sync: %s — %s", log_label, message)
        last_log[0] = now


def _collect_facet_rows(row: Mapping[str, Any]) -> List[Tuple[int, str, str]]:
    item_id = int(row["id"])
    collected: List[Tuple[int, str, str]] = []
    for director in _parse_json_list(row["directors"]):
        collected.append((item_id, "director", director))
    for actor in _parse_json_list(row["cast"]):
        collected.append((item_id, "actor", actor))
    for keyword in _parse_json_list(row["keywords"]):
        collected.append((item_id, "keyword", keyword))
    for country in _country_values_from_row(row):
        collected.append((item_id, "country", country))
    language = _language_value_from_row(row)
    if language:
        collected.append((item_id, "language", language))
    return collected


def rebuild_library_facets(db: Database, *, progress: ProgressCallback = None) -> int:
    """Rebuild the facet index with a single bulk transaction."""
    items = db.all_library_items()
    total_items = len(items)
    facet_rows: List[Tuple[int, str, str]] = []
    last_log = [0.0]

    _emit_rebuild_progress(
        progress,
        message="Building search facets…",
        current=0,
        total=max(total_items, 1),
        last_log=last_log,
        log_label="building search facets",
        force=True,
    )

    for index, row in enumerate(items, start=1):
        facet_rows.extend(_collect_facet_rows(row))
        _emit_rebuild_progress(
            progress,
            message=f"Building search facets… {len(facet_rows):,} rows",
            current=index,
            total=max(total_items, 1),
            last_log=last_log,
            log_label="building search facets",
        )

    count = db.replace_library_facets(facet_rows)
    _emit_rebuild_progress(
        progress,
        message=f"Building search facets… {count:,} rows",
        current=max(total_items, 1),
        total=max(total_items, 1),
        last_log=last_log,
        log_label="building search facets",
        force=True,
    )
    return count


def rebuild_library_fts(db: Database, *, progress: ProgressCallback = None) -> int:
    """Rebuild the FTS index with a single bulk transaction."""
    items = db.all_library_items()
    total_items = len(items)
    fts_rows: List[Tuple[int, str, str, str, str, str]] = []
    last_log = [0.0]

    _emit_rebuild_progress(
        progress,
        message="Building search index…",
        current=0,
        total=max(total_items, 1),
        last_log=last_log,
        log_label="building search index",
        force=True,
    )

    for index, row in enumerate(items, start=1):
        cast_text = " ".join(_parse_json_list(row["cast"]))
        directors_text = " ".join(_parse_json_list(row["directors"]))
        keywords_text = " ".join(_parse_json_list(row["keywords"]))
        fts_rows.append(
            (
                int(row["id"]),
                str(row["title"] or ""),
                str(row["summary"] or ""),
                cast_text,
                directors_text,
                keywords_text,
            )
        )
        _emit_rebuild_progress(
            progress,
            message=f"Building search index… {index:,} of {total_items:,} titles",
            current=index,
            total=max(total_items, 1),
            last_log=last_log,
            log_label="building search index",
        )

    count = db.replace_library_fts(fts_rows)
    _emit_rebuild_progress(
        progress,
        message=f"Building search index… {count:,} titles",
        current=max(total_items, 1),
        total=max(total_items, 1),
        last_log=last_log,
        log_label="building search index",
        force=True,
    )
    return count


def library_facet_catalog(
    db: Database,
    facet_type: str,
    *,
    limit: int = 50,
) -> Dict[str, Any]:
    normalized = facet_type.strip().lower()
    allowed = {"director", "actor", "keyword", "country", "language", "motif", "theme"}
    if normalized not in allowed:
        raise ValueError(f"facet_type must be one of: {', '.join(sorted(allowed))}")
    capped = min(max(1, limit), 100)
    if normalized in {"country", "language"}:
        return _facet_catalog_from_items(db, normalized, limit=capped)
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT facet_value, COUNT(*) AS cnt
            FROM library_facets
            WHERE facet_type = ?
            GROUP BY facet_value
            ORDER BY cnt DESC, facet_value ASC
            LIMIT ?
            """,
            (normalized, capped),
        ).fetchall()
    facets = [{"value": str(r["facet_value"]), "count": int(r["cnt"])} for r in rows]
    return {"facet_type": normalized, "facets": facets, "returned": len(facets)}
