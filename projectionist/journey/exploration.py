"""Exploration-focused My Journey payload — directors, craft, shelf insights."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.library.db import Database
from projectionist.library.facets import library_facet_catalog
from projectionist.library.query import library_overview
from projectionist.swr_cache import SwrCache

logger = logging.getLogger(__name__)

_PERSON_LIMIT = 12
_INSIGHT_LIMIT = 6


def _find_person_by_name(db: Database, name: str):
    cleaned = str(name or "").strip()
    if not cleaned:
        return None
    with db.connect() as conn:
        # Exact match rides ``idx_people_name``; the leading-wildcard LIKE scan is
        # only a fallback (it walks every person row, once per director).
        exact = conn.execute(
            """
            SELECT id, tmdb_person_id, name, profile_url FROM people
            WHERE name = ?
            LIMIT 1
            """,
            (cleaned,),
        ).fetchone()
        if exact is not None:
            return exact
        pattern = f"%{cleaned.lower()}%"
        return conn.execute(
            """
            SELECT id, tmdb_person_id, name, profile_url FROM people
            WHERE lower(name) LIKE ?
            ORDER BY CASE WHEN lower(name) = ? THEN 0 ELSE 1 END, name
            LIMIT 1
            """,
            (pattern, cleaned.lower()),
        ).fetchone()


def _person_row(
    db: Database,
    *,
    name: str,
    count: int,
    role: str,
) -> Optional[Dict[str, Any]]:
    cleaned = str(name or "").strip()
    if not cleaned:
        return None
    person = _find_person_by_name(db, cleaned)
    tmdb_id = int(person["tmdb_person_id"]) if person and person["tmdb_person_id"] is not None else None
    profile_url = str(person["profile_url"] or "") if person else ""
    display_name = str(person["name"] or cleaned) if person else cleaned
    return {
        "name": display_name,
        "role": role,
        "count": int(count),
        "tmdb_person_id": tmdb_id,
        "profile_url": profile_url or None,
    }


def _directors_from_facets(db: Database, *, limit: int) -> List[Dict[str, Any]]:
    catalog = library_facet_catalog(db, "director", limit=limit)
    people: List[Dict[str, Any]] = []
    for facet in catalog.get("facets") or []:
        row = _person_row(
            db,
            name=str(facet.get("value") or ""),
            count=int(facet.get("count") or 0),
            role="director",
        )
        if row:
            people.append(row)
    return people


def _top_people_by_credit_jobs(
    db: Database,
    *,
    role: str,
    where_sql: str,
    params: Sequence[Any],
    limit: int,
) -> List[Dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                p.tmdb_person_id,
                p.name,
                p.profile_url,
                COUNT(DISTINCT c.item_id) AS cnt
            FROM credits c
            JOIN people p ON p.id = c.person_id
            WHERE {where_sql}
            GROUP BY p.id
            ORDER BY cnt DESC, p.name ASC
            LIMIT ?
            """,
            (*params, limit),
        ).fetchall()
    people: List[Dict[str, Any]] = []
    for row in rows:
        people.append(
            {
                "name": str(row["name"] or ""),
                "role": role,
                "count": int(row["cnt"] or 0),
                "tmdb_person_id": int(row["tmdb_person_id"])
                if row["tmdb_person_id"] is not None
                else None,
                "profile_url": str(row["profile_url"] or "") or None,
            }
        )
    return people


def _cinematographers(db: Database, *, limit: int) -> List[Dict[str, Any]]:
    return _top_people_by_credit_jobs(
        db,
        role="cinematographer",
        where_sql="""
            (
                (c.department = 'Camera' AND c.job IN ('Director of Photography', 'Cinematography'))
                OR c.job LIKE '%Director of Photography%'
                OR c.job LIKE '%Cinematography%'
            )
        """,
        params=(),
        limit=limit,
    )


def _composers(db: Database, *, limit: int) -> List[Dict[str, Any]]:
    return _top_people_by_credit_jobs(
        db,
        role="composer",
        where_sql="""
            (
                c.job LIKE '%Composer%'
                OR c.job LIKE '%Original Music%'
            )
        """,
        params=(),
        limit=limit,
    )


def _insight_cards(overview: Mapping[str, Any], *, limit: int) -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for genre in (overview.get("top_genres") or [])[: limit // 2 or 3]:
        label = str(genre.get("genre") or "").strip()
        count = int(genre.get("count") or 0)
        if not label or count <= 0:
            continue
        cards.append(
            {
                "id": f"genre-{label.lower().replace(' ', '-')}",
                "kind": "genre",
                "label": label,
                "count": count,
                "note": f"{count} titles tagged {label} in your shelf.",
            }
        )
    for decade in (overview.get("decades") or [])[: limit // 2 or 3]:
        label = str(decade.get("decade") or "").strip()
        count = int(decade.get("count") or 0)
        if not label or count <= 0:
            continue
        cards.append(
            {
                "id": f"era-{label}",
                "kind": "era",
                "label": label,
                "count": count,
                "note": f"{count} titles from the {label} in your collection.",
            }
        )
    return cards[:limit]


def _courses_and_explainers(
    db: Database,
    *,
    user_id: str,
    youth_safe_only: bool,
) -> Dict[str, Any]:
    """Courses + explainers for My Journey — **read-only**.

    ``engagement_summary`` also runs ``sync_review_challenges`` (challenge + badge
    *writes*). On the request path those writes queue behind library sync / batch
    jobs on SQLite's single writer (busy timeout 30s), which made My Journey hang.
    Journey shows no gamification, so it only reads what it renders.
    """
    explainers: List[Dict[str, Any]] = []
    courses: List[Dict[str, Any]] = []
    try:
        explainers = db.list_engagement_explainers(youth_safe_only=youth_safe_only)
    except Exception:  # noqa: BLE001
        logger.debug("journey explainers listing failed", exc_info=True)
    try:
        published = db.list_published_lists() if hasattr(db, "list_published_lists") else []
        progress_rows = {p["list_id"]: p for p in db.list_user_course_progress(user_id)}
        for coll in published or []:
            if str(coll.get("list_kind") or "") != "course":
                continue
            prog = progress_rows.get(coll["id"]) or {
                "position": 0,
                "completed_at": None,
                "updated_at": None,
            }
            courses.append(
                {
                    "id": coll["id"],
                    "name": coll.get("name"),
                    "description": coll.get("description") or "",
                    "item_count": coll.get("item_count") or 0,
                    "position": prog.get("position") or 0,
                    "completed_at": prog.get("completed_at"),
                    "updated_at": prog.get("updated_at"),
                }
            )
    except Exception:  # noqa: BLE001
        logger.debug("journey courses listing failed", exc_info=True)
    return {"courses": courses, "explainers": explainers}


def journey_library_rails(
    db: Database,
    *,
    person_limit: int = _PERSON_LIMIT,
    insight_limit: int = _INSIGHT_LIMIT,
) -> Dict[str, Any]:
    """User-independent, library-derived rails (the expensive part)."""
    capped_people = min(max(1, int(person_limit or _PERSON_LIMIT)), 24)
    capped_insights = min(max(1, int(insight_limit or _INSIGHT_LIMIT)), 12)
    overview = library_overview(db)
    return {
        "people": {
            "directors": _directors_from_facets(db, limit=capped_people),
            "cinematographers": _cinematographers(db, limit=capped_people),
            "composers": _composers(db, limit=capped_people),
        },
        "insights": _insight_cards(overview, limit=capped_insights),
        "library_total": int(overview.get("total") or 0),
        "generated_at": int(time.time()),
    }


def journey_exploration(
    db: Database,
    *,
    user_id: str,
    youth_safe_only: bool = False,
    person_limit: int = _PERSON_LIMIT,
    insight_limit: int = _INSIGHT_LIMIT,
) -> Dict[str, Any]:
    """Aggregate cinema-exploration rails for My Journey (synchronous full build)."""
    rails = journey_library_rails(db, person_limit=person_limit, insight_limit=insight_limit)
    engagement_bits = _courses_and_explainers(
        db,
        user_id=user_id,
        youth_safe_only=youth_safe_only,
    )
    return {
        "people": rails["people"],
        "insights": rails["insights"],
        "library_total": rails["library_total"],
        "courses": engagement_bits["courses"],
        "explainers": engagement_bits["explainers"],
    }


# --------------------------------------------------------------------------- SWR
# Library rails scan credits/facets; recompute is minutes-stale-tolerant and must
# never sit on the My Journey request path.
JOURNEY_SOFT_TTL_SECONDS = 300.0
JOURNEY_HARD_TTL_SECONDS = 7 * 24 * 3600.0
JOURNEY_COLD_WAIT_SECONDS = 0.75
_JOURNEY_KEY = f"rails|p={_PERSON_LIMIT}|i={_INSIGHT_LIMIT}"


def _journey_key(db: Database) -> str:
    # Scope by database file so tests / multi-DB tools never share a payload.
    return f"{getattr(db, 'path', '')}|{_JOURNEY_KEY}"

JOURNEY_CACHE = SwrCache(
    "journey_library_rails",
    soft_ttl=JOURNEY_SOFT_TTL_SECONDS,
    hard_ttl=JOURNEY_HARD_TTL_SECONDS,
    durable=True,
)


def invalidate_journey_cache() -> None:
    """Mark Journey rails stale after a library sync (payload is kept for paint)."""
    JOURNEY_CACHE.invalidate()


def _warming_rails() -> Dict[str, Any]:
    return {
        "people": {"directors": [], "cinematographers": [], "composers": []},
        "insights": [],
        "library_total": 0,
    }


def get_journey_exploration(
    db: Database,
    *,
    user_id: str,
    youth_safe_only: bool = False,
    cold_wait: float = JOURNEY_COLD_WAIT_SECONDS,
) -> Dict[str, Any]:
    """My Journey via stale-while-revalidate.

    Library rails come from the SWR cache (memory + durable ``sync_state``); the
    per-user courses/explainers are small read-only queries layered on top.
    """
    result = JOURNEY_CACHE.get(
        _journey_key(db),
        lambda: journey_library_rails(db),
        db=db,
        warming=_warming_rails,
        cold_wait=cold_wait,
    )
    rails = result.payload
    engagement_bits = _courses_and_explainers(
        db,
        user_id=user_id,
        youth_safe_only=youth_safe_only,
    )
    return {
        "people": rails.get("people") or _warming_rails()["people"],
        "insights": rails.get("insights") or [],
        "library_total": int(rails.get("library_total") or 0),
        "courses": engagement_bits["courses"],
        "explainers": engagement_bits["explainers"],
        "cached": result.cached,
        "stale": result.stale,
        "warming": result.warming,
        "generated_at": rails.get("generated_at"),
    }


def prewarm_journey(db: Database) -> None:
    """Build the Journey rails once off the request path (startup / post-sync)."""
    try:
        payload = journey_library_rails(db)
        JOURNEY_CACHE.put(_journey_key(db), payload, db=db)
    except Exception:  # noqa: BLE001
        logger.debug("journey prewarm skipped", exc_info=True)
