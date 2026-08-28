"""Exploration-focused My Journey payload — directors, craft, shelf insights."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.library.db import Database
from projectionist.library.facets import library_facet_catalog
from projectionist.library.query import library_overview

_PERSON_LIMIT = 12
_INSIGHT_LIMIT = 6


def _find_person_by_name(db: Database, name: str):
    cleaned = str(name or "").strip()
    if not cleaned:
        return None
    pattern = f"%{cleaned.lower()}%"
    with db.connect() as conn:
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
    from projectionist.engagement import engagement_summary

    summary = engagement_summary(db, user_id=user_id, youth_safe_only=youth_safe_only)
    return {
        "courses": summary.get("courses") or [],
        "explainers": summary.get("explainers") or [],
    }


def journey_exploration(
    db: Database,
    *,
    user_id: str,
    youth_safe_only: bool = False,
    person_limit: int = _PERSON_LIMIT,
    insight_limit: int = _INSIGHT_LIMIT,
) -> Dict[str, Any]:
    """Aggregate cinema-exploration rails for My Journey (no gamification fields)."""
    capped_people = min(max(1, int(person_limit or _PERSON_LIMIT)), 24)
    capped_insights = min(max(1, int(insight_limit or _INSIGHT_LIMIT)), 12)

    overview = library_overview(db)
    engagement_bits = _courses_and_explainers(
        db,
        user_id=user_id,
        youth_safe_only=youth_safe_only,
    )

    return {
        "people": {
            "directors": _directors_from_facets(db, limit=capped_people),
            "cinematographers": _cinematographers(db, limit=capped_people),
            "composers": _composers(db, limit=capped_people),
        },
        "insights": _insight_cards(overview, limit=capped_insights),
        "library_total": int(overview.get("total") or 0),
        "courses": engagement_bits["courses"],
        "explainers": engagement_bits["explainers"],
    }
