"""Owner demand catch-up: kinship miss signals → idle enrichment priority.

When More Like This, Related titles, or a household recommendation bridge
returns empty for a title the library already cares about, write a lightweight
``telemetry_events`` row (``event_type=kinship_miss``). Idle trickle tasks
prefer those item ids on the next bounded batch.

Never blocks callers. Cap new keys so a stampede of empty shelves cannot fill
the closed-loop table.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import quote

logger = logging.getLogger(__name__)

EVENT_KINSHIP_MISS = "kinship_miss"
# Soft cap on distinct kinship_miss entity keys (new inserts only; hit bumps OK).
KINSHIP_MISS_QUEUE_CAP = 500
DEFAULT_PREFER_BATCH = 25

VALID_REASONS = frozenset(
    {
        "more_like_this_empty",
        "relations_empty",
        "bridge_zero_peers",
    }
)
# CA-02 public why codes (brief uses related_empty; storage keeps relations_empty).
PUBLIC_WHY_QUEUED = {
    "more_like_this_empty": "more_like_this_empty",
    "relations_empty": "related_empty",
    "related_empty": "related_empty",
    "bridge_zero_peers": "bridge_zero_peers",
}
WHY_QUEUED_LABELS = {
    "more_like_this_empty": "Empty More Like This",
    "related_empty": "Empty Related titles",
    "bridge_zero_peers": "Bridge with zero peers",
}
LIST_NOTE = (
    "Demand, not a grade. Idle catch-up prefers these titles. Nothing is auto-repaired."
)
_EMPTY_OPENED = {
    "opened_title_count": 0,
    "opened_with_explainable_count": 0,
    "with_explainable_neighbors_opened_pct": 0.0,
}


def _count_kinship_miss_keys(db: Any) -> int:
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM telemetry_events
            WHERE event_type = ?
            """,
            (EVENT_KINSHIP_MISS,),
        ).fetchone()
    return int(row["c"] if row else 0)


def _entity_key_exists(db: Any, entity_key: str) -> bool:
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM telemetry_events
            WHERE event_type = ? AND entity_type = 'title' AND entity_key = ?
            LIMIT 1
            """,
            (EVENT_KINSHIP_MISS, entity_key),
        ).fetchone()
    return row is not None


def schedule_kinship_miss(
    *,
    item_id: int,
    reason: str,
    context_source: str = "discovery",
    extra: Optional[Mapping[str, Any]] = None,
) -> bool:
    """Enqueue a ``kinship_miss`` event for ``item_id`` (non-blocking).

    Returns True when a write was scheduled (or would bump an existing key),
    False when the item is invalid or the queue cap blocked a new key.
    """
    try:
        seed = int(item_id)
    except (TypeError, ValueError):
        return False
    if seed <= 0:
        return False

    cleaned_reason = str(reason or "").strip()
    if cleaned_reason not in VALID_REASONS:
        cleaned_reason = "more_like_this_empty"

    from projectionist.facets.closed_loop import resolve_closed_loop_database
    from projectionist.telemetry.ingestion import schedule_closed_loop_event

    db = resolve_closed_loop_database()
    if db is None:
        return False

    entity_key = str(seed)
    try:
        if not _entity_key_exists(db, entity_key):
            if _count_kinship_miss_keys(db) >= KINSHIP_MISS_QUEUE_CAP:
                logger.debug(
                    "kinship_miss queue at cap (%s); skip new item_id=%s",
                    KINSHIP_MISS_QUEUE_CAP,
                    seed,
                )
                return False
    except Exception:  # noqa: BLE001 — never break discovery responses
        logger.debug("kinship_miss cap check failed", exc_info=True)

    payload: dict[str, Any] = {
        "item_id": seed,
        "reason": cleaned_reason,
        "context_source": str(context_source or "discovery")[:80],
    }
    if extra:
        for field, value in dict(extra).items():
            field_s = str(field)
            if field_s in payload:
                continue
            payload[field_s] = value

    schedule_closed_loop_event(
        db,
        event_type=EVENT_KINSHIP_MISS,
        priority_tier="P2",
        entity_type="title",
        entity_key=entity_key,
        payload=payload,
    )
    return True


def preferred_item_ids(
    db: Any,
    *,
    limit: int = DEFAULT_PREFER_BATCH,
    min_hit_count: int = 1,
) -> List[int]:
    """Return library item ids from kinship_miss backlog, hottest first."""
    capped = max(1, min(int(limit), KINSHIP_MISS_QUEUE_CAP))
    try:
        signals = db.list_closed_loop_events(
            event_type=EVENT_KINSHIP_MISS,
            entity_type="title",
            min_hit_count=max(1, int(min_hit_count)),
            limit=capped,
        )
    except Exception:  # noqa: BLE001
        logger.debug("kinship_miss prefer list failed", exc_info=True)
        return []

    out: List[int] = []
    seen: set[int] = set()
    for signal in signals or ():
        raw = str(signal.get("entity_key") or "").strip()
        try:
            item_id = int(raw)
        except (TypeError, ValueError):
            continue
        if item_id <= 0 or item_id in seen:
            continue
        seen.add(item_id)
        out.append(item_id)
        if len(out) >= capped:
            break
    return out


def merge_preferred_ids(
    preferred: Sequence[int],
    fallback: Sequence[int],
    *,
    limit: int,
) -> List[int]:
    """Prefer demand ids, then fill from ``fallback``, de-duplicated."""
    capped = max(1, int(limit))
    out: List[int] = []
    seen: set[int] = set()
    for item_id in list(preferred) + list(fallback):
        try:
            cleaned = int(item_id)
        except (TypeError, ValueError):
            continue
        if cleaned <= 0 or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
        if len(out) >= capped:
            break
    return out


def prioritize_enrichment_rows(
    db: Any,
    fallback_rows: Sequence[Any],
    *,
    limit: int,
    include_item_id=None,
) -> List[Any]:
    """Put kinship-miss titles first when they still qualify for the backlog.

    ``include_item_id(db, item_id) -> Optional[row]`` returns a backlog-eligible
    row for a preferred id, or None when that title does not need this task.
    """
    capped = max(1, int(limit))
    prefer_ids = preferred_item_ids(db, limit=capped)
    if not prefer_ids or include_item_id is None:
        return list(fallback_rows)[:capped]

    out: List[Any] = []
    seen: set[int] = set()
    for item_id in prefer_ids:
        row = include_item_id(db, item_id)
        if row is None:
            continue
        try:
            rid = int(row["id"])
        except (TypeError, ValueError, KeyError, IndexError):
            continue
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
        if len(out) >= capped:
            return out

    for row in fallback_rows:
        try:
            rid = int(row["id"])
        except (TypeError, ValueError, KeyError, IndexError):
            continue
        if rid in seen:
            continue
        seen.add(rid)
        out.append(row)
        if len(out) >= capped:
            break
    return out


def public_why_queued(reason: str) -> str:
    """Map stored miss reason onto the CA-02 public why_queued code."""
    cleaned = str(reason or "").strip()
    return PUBLIC_WHY_QUEUED.get(cleaned, "more_like_this_empty")


def why_queued_label(reason: str) -> str:
    code = public_why_queued(reason)
    return WHY_QUEUED_LABELS.get(code, code.replace("_", " "))


def _parse_payload(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _title_href(item: Mapping[str, Any]) -> Optional[str]:
    media = "show" if str(item.get("media_type") or "") == "show" else "movie"
    tmdb = item.get("tmdb_id")
    if tmdb not in (None, ""):
        try:
            return f"/title/{media}/{int(tmdb)}"
        except (TypeError, ValueError):
            pass
    rating_key = str(item.get("rating_key") or "").strip()
    if rating_key:
        return f"/title/{media}/{quote(rating_key, safe='')}?id_type=rating_key"
    tvdb = item.get("tvdb_id")
    if media == "show" and tvdb not in (None, ""):
        try:
            return f"/title/{media}/{int(tvdb)}?id_type=tvdb"
        except (TypeError, ValueError):
            pass
    return None


def opened_explainable_coverage(conn: Any) -> Dict[str, Any]:
    """Named kinship among ``kinship_miss`` keys (opened empty shelves).

    Denominator is distinct miss keys, not the whole library. Percent moves when
    idle ``plot_neighbors`` annotates a missed title as explainable. Zero miss
    keys → 0.0 (hero should fall back to global Named kinship).
    """
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('telemetry_events', 'item_neighbors')"
            )
        }
        if "telemetry_events" not in tables:
            return dict(_EMPTY_OPENED)
        join_explainable = "item_neighbors" in tables
        if join_explainable:
            neighbor_cols = {row[1] for row in conn.execute("PRAGMA table_info(item_neighbors)")}
            if "explainable" not in neighbor_cols:
                join_explainable = False
        if join_explainable:
            row = conn.execute(
                """
                SELECT
                    COUNT(DISTINCT CAST(te.entity_key AS INTEGER)) AS opened,
                    COUNT(
                        DISTINCT CASE
                            WHEN n.item_id IS NOT NULL
                            THEN CAST(te.entity_key AS INTEGER)
                        END
                    ) AS with_explainable
                FROM telemetry_events te
                LEFT JOIN item_neighbors n
                  ON n.item_id = CAST(te.entity_key AS INTEGER)
                 AND COALESCE(n.explainable, 0) = 1
                WHERE te.event_type = ?
                  AND te.entity_type = 'title'
                  AND CAST(te.entity_key AS INTEGER) > 0
                """,
                (EVENT_KINSHIP_MISS,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT CAST(entity_key AS INTEGER)) AS opened,
                       0 AS with_explainable
                FROM telemetry_events
                WHERE event_type = ?
                  AND entity_type = 'title'
                  AND CAST(entity_key AS INTEGER) > 0
                """,
                (EVENT_KINSHIP_MISS,),
            ).fetchone()
        opened = int((row["opened"] if row else 0) or 0)
        with_explainable = int((row["with_explainable"] if row else 0) or 0)
        pct = round((with_explainable / opened) * 100.0, 1) if opened > 0 else 0.0
        return {
            "opened_title_count": opened,
            "opened_with_explainable_count": with_explainable,
            "with_explainable_neighbors_opened_pct": pct,
        }
    except Exception:  # noqa: BLE001 — coverage must never fail the dashboard
        logger.debug("opened kinship coverage failed", exc_info=True)
        return dict(_EMPTY_OPENED)


def list_kinship_miss(db: Any, *, limit: int = 50) -> Dict[str, Any]:
    """Owner-facing demand list: title, why queued, hit_count, last miss.

    Read-only. Does not promote into staged augmentations or trigger repair.
    """
    capped = max(1, min(int(limit or 50), 200))
    items: List[Dict[str, Any]] = []
    try:
        with db.connect() as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name IN ('telemetry_events', 'library_items')"
                )
            }
            if "telemetry_events" not in tables:
                return {"items": [], "count": 0, "note": LIST_NOTE}
            join_items = "library_items" in tables
            if join_items:
                rows = conn.execute(
                    """
                    SELECT
                        te.entity_key,
                        te.hit_count,
                        te.updated_at,
                        te.payload_json,
                        li.id AS item_id,
                        li.title,
                        li.year,
                        li.media_type,
                        li.tmdb_id,
                        li.tvdb_id,
                        li.rating_key,
                        li.poster_url
                    FROM telemetry_events te
                    LEFT JOIN library_items li
                      ON li.id = CAST(te.entity_key AS INTEGER)
                    WHERE te.event_type = ?
                      AND te.entity_type = 'title'
                    ORDER BY te.hit_count DESC, te.updated_at DESC
                    LIMIT ?
                    """,
                    (EVENT_KINSHIP_MISS, capped),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT
                        entity_key,
                        hit_count,
                        updated_at,
                        payload_json,
                        NULL AS item_id,
                        NULL AS title,
                        NULL AS year,
                        NULL AS media_type,
                        NULL AS tmdb_id,
                        NULL AS tvdb_id,
                        NULL AS rating_key,
                        NULL AS poster_url
                    FROM telemetry_events
                    WHERE event_type = ?
                      AND entity_type = 'title'
                    ORDER BY hit_count DESC, updated_at DESC
                    LIMIT ?
                    """,
                    (EVENT_KINSHIP_MISS, capped),
                ).fetchall()
    except Exception:  # noqa: BLE001
        logger.debug("kinship_miss list failed", exc_info=True)
        return {"items": [], "count": 0, "note": LIST_NOTE}

    for row in rows or ():
        mapping = dict(row)
        payload = _parse_payload(mapping.get("payload_json"))
        try:
            item_id = int(mapping.get("item_id") or mapping.get("entity_key") or 0)
        except (TypeError, ValueError):
            continue
        if item_id <= 0:
            continue
        why = public_why_queued(str(payload.get("reason") or ""))
        title = str(mapping.get("title") or "").strip() or f"Title {item_id}"
        item: Dict[str, Any] = {
            "item_id": item_id,
            "title": title,
            "year": mapping.get("year"),
            "media_type": mapping.get("media_type") or "movie",
            "tmdb_id": mapping.get("tmdb_id"),
            "tvdb_id": mapping.get("tvdb_id"),
            "rating_key": mapping.get("rating_key"),
            "poster_url": str(mapping.get("poster_url") or "") or None,
            "reason": str(payload.get("reason") or "more_like_this_empty"),
            "why_queued": why,
            "why_label": why_queued_label(why),
            "hit_count": int(mapping.get("hit_count") or 0),
            "last_miss": mapping.get("updated_at"),
        }
        href = _title_href(item)
        if href:
            item["href"] = href
        items.append(item)
        if len(items) >= capped:
            break
    return {"items": items, "count": len(items), "note": LIST_NOTE}
