"""Tonight's double feature — pair two owned movies with a living-room why."""

from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Mapping, Optional

from projectionist.library.db import Database
from projectionist.library.feeds import _feed_item


def suggest_tonight_double_feature(
    db: Database,
    *,
    theme: str = "",
    youth_max_rating: Optional[str] = None,
) -> Dict[str, Any]:
    """Pick two complementary owned movies for a Companion/Concierge-style pairing."""
    theme_key = str(theme or "").strip().lower()
    where = ["media_type = 'movie'"]
    params: List[Any] = []
    if theme_key:
        where.append("LOWER(genres) LIKE ?")
        params.append(f"%{theme_key}%")
    if youth_max_rating:
        # Soft age gate — keep rows without a rating when youth browsing.
        where.append(
            "(content_rating IS NULL OR content_rating = '' OR UPPER(content_rating) IN "
            "('G', 'PG', 'TV-Y', 'TV-G', 'TV-PG', 'TV-Y7'))"
        )

    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM library_items
            WHERE {' AND '.join(where)}
            ORDER BY RANDOM()
            LIMIT 24
            """,
            params,
        ).fetchall()

    candidates = [dict(r) for r in rows]
    if len(candidates) < 2:
        return {
            "feed": "tonight-double-feature",
            "title": "Tonight’s double feature",
            "items": [],
            "bridge_text": "",
            "combined_runtime": 0,
            "note": "Need at least two owned movies to pair a double feature.",
        }

    random.shuffle(candidates)
    title_a = candidates[0]
    title_b = None
    genres_a = _genres(title_a)
    for candidate in candidates[1:]:
        shared = genres_a & _genres(candidate)
        if shared:
            title_b = candidate
            break
    if title_b is None:
        title_b = candidates[1]

    genres_b = _genres(title_b)
    shared = genres_a & genres_b
    year_a = int(title_a.get("year") or 0)
    year_b = int(title_b.get("year") or 0)
    year_gap = abs(year_a - year_b)
    if shared and year_gap > 15:
        bridge = (
            f"Both explore {', '.join(sorted(shared)[:2]).lower()} territory, "
            f"but {year_gap} years apart"
        )
    elif shared:
        bridge = f"A {', '.join(sorted(shared)[:2]).lower()} pairing from the same era"
    else:
        bridge = "Two different angles on cinema — contrast and compare"

    runtime_a = int(title_a.get("runtime_minutes") or 0)
    runtime_b = int(title_b.get("runtime_minutes") or 0)
    item_a = _feed_item(title_a)
    item_b = _feed_item(title_b)
    item_a["recommendation_reason"] = "Double feature — first half"
    item_b["recommendation_reason"] = "Double feature — second half"
    return {
        "feed": "tonight-double-feature",
        "title": "Tonight’s double feature",
        "lede": bridge,
        "bridge_text": bridge,
        "combined_runtime": runtime_a + runtime_b,
        "title_a": item_a,
        "title_b": item_b,
        "items": [item_a, item_b],
        "note": "",
    }


def _genres(row: Mapping[str, Any]) -> set[str]:
    raw = row.get("genres")
    if isinstance(raw, list):
        return {str(g).strip() for g in raw if str(g).strip()}
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return {str(g).strip() for g in parsed if str(g).strip()}
        except (TypeError, json.JSONDecodeError):
            return {part.strip() for part in raw.split(",") if part.strip()}
    return set()
