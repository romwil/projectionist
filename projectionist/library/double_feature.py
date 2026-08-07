"""Tonight's double feature — pair two owned movies with a living-room why."""

from __future__ import annotations

import json
import random
from typing import Any, Dict, List, Mapping, Optional, Sequence

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
    # Soft-prefer an unwatched anchor when the pool has one — keeps "why" honest.
    unwatched = [c for c in candidates if _view_count(c) == 0]
    title_a = unwatched[0] if unwatched else candidates[0]
    genres_a = _genres(title_a)

    title_b = None
    shared_pick: set[str] = set()
    # Prefer a shared-genre partner, then unwatched among those matches.
    shared_candidates: List[Mapping[str, Any]] = []
    for candidate in candidates:
        if candidate is title_a:
            continue
        shared = genres_a & _genres(candidate)
        if shared:
            shared_candidates.append(candidate)
    if shared_candidates:
        shared_candidates.sort(key=lambda row: (0 if _view_count(row) == 0 else 1))
        title_b = shared_candidates[0]
        shared_pick = genres_a & _genres(title_b)
    else:
        rest = [c for c in candidates if c is not title_a]
        rest.sort(key=lambda row: (0 if _view_count(row) == 0 else 1))
        title_b = rest[0]

    genres_b = _genres(title_b)
    shared = shared_pick or (genres_a & genres_b)
    directors_a = _people(title_a, "directors")
    directors_b = _people(title_b, "directors")
    shared_directors = directors_a & directors_b

    runtime_a = _runtime(title_a)
    runtime_b = _runtime(title_b)
    year_a = _year(title_a)
    year_b = _year(title_b)
    year_gap = abs(year_a - year_b) if year_a and year_b else 0

    bridge = build_pairing_why(
        shared_genres=shared,
        shared_directors=shared_directors,
        year_a=year_a,
        year_b=year_b,
        year_gap=year_gap,
        genres_a=genres_a,
        genres_b=genres_b,
        runtime_a=runtime_a,
        runtime_b=runtime_b,
        theme=theme_key,
    )

    item_a = _feed_item(title_a)
    item_b = _feed_item(title_b)
    why_a = build_title_why(
        title_a,
        half="opening",
        shared_genres=shared,
        theme=theme_key,
    )
    why_b = build_title_why(
        title_b,
        half="closing",
        shared_genres=shared,
        theme=theme_key,
    )
    item_a["recommendation_reason"] = why_a
    item_a["why"] = why_a
    item_b["recommendation_reason"] = why_b
    item_b["why"] = why_b
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


def build_pairing_why(
    *,
    shared_genres: set[str],
    shared_directors: set[str] | None = None,
    year_a: int = 0,
    year_b: int = 0,
    year_gap: int = 0,
    genres_a: set[str] | None = None,
    genres_b: set[str] | None = None,
    runtime_a: int = 0,
    runtime_b: int = 0,
    theme: str = "",
) -> str:
    """Explain why these two titles were paired — grounded in the pairing signals."""
    parts: List[str] = []
    directors = {str(d).strip() for d in (shared_directors or set()) if str(d).strip()}
    shared = _sorted_labels(shared_genres)
    theme_key = str(theme or "").strip().lower()

    if directors:
        name = sorted(directors)[0]
        parts.append(f"Same director — {name}")
    if shared:
        genre_bit = _join_labels(shared[:2])
        if year_a and year_b and year_gap > 15:
            parts.append(
                f"shared {genre_bit} · {year_gap} years apart ({year_a} & {year_b})"
            )
        elif year_a and year_b:
            parts.append(f"shared {genre_bit} · close in time ({year_a} & {year_b})")
        else:
            parts.append(f"shared {genre_bit}")
    elif not directors:
        label_a = _join_labels(_sorted_labels(genres_a or set())[:1]) or "one shelf"
        label_b = _join_labels(_sorted_labels(genres_b or set())[:1]) or "another"
        parts.append(f"Contrast pairing — {label_a} with {label_b}")

    if theme_key:
        parts.append(f"tonight’s {theme_key} theme")

    combined = int(runtime_a or 0) + int(runtime_b or 0)
    if combined > 0:
        parts.append(f"{_format_runtime(combined)} night")

    if not parts:
        return "Two owned titles paired from your shelves"
    # First clause capitalized; later clauses stay lowercase after " · ".
    head, *tail = parts
    head = head[:1].upper() + head[1:] if head else head
    return " · ".join([head, *tail])


def build_title_why(
    row: Mapping[str, Any],
    *,
    half: str,
    shared_genres: set[str] | None = None,
    theme: str = "",
) -> str:
    """Explain why this half was selected for the viewer — grounded in row signals."""
    parts: List[str] = []
    views = _view_count(row)
    if views <= 0:
        parts.append("Still unwatched on your shelves")
    elif views == 1:
        parts.append("Ready for a rewatch")
    else:
        parts.append(f"Rewatch-friendly ({views} plays)")

    genres = _genres(row)
    shared = genres & set(shared_genres or set())
    if shared:
        parts.append(f"{_join_labels(_sorted_labels(shared)[:2])} pick")
    elif genres:
        parts.append(f"{_join_labels(_sorted_labels(genres)[:2])} from your library")

    runtime = _runtime(row)
    if runtime > 0:
        parts.append(f"{runtime} min")

    theme_key = str(theme or "").strip().lower()
    if theme_key and any(theme_key in g.lower() for g in genres):
        parts.append(f"fits the {theme_key} theme")

    slot = "opening" if str(half).strip().lower() in {"opening", "a", "first"} else "closing"
    if len(parts) <= 1:
        parts.append(f"{slot} half of tonight’s pair")

    return " · ".join(parts)


def _genres(row: Mapping[str, Any]) -> set[str]:
    return _json_name_set(row.get("genres"))


def _people(row: Mapping[str, Any], key: str) -> set[str]:
    return _json_name_set(row.get(key))


def _json_name_set(raw: Any) -> set[str]:
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


def _view_count(row: Mapping[str, Any]) -> int:
    try:
        return max(0, int(row.get("view_count") or 0))
    except (TypeError, ValueError):
        return 0


def _runtime(row: Mapping[str, Any]) -> int:
    try:
        return max(0, int(row.get("runtime_minutes") or 0))
    except (TypeError, ValueError):
        return 0


def _year(row: Mapping[str, Any]) -> int:
    try:
        return max(0, int(row.get("year") or 0))
    except (TypeError, ValueError):
        return 0


def _sorted_labels(values: set[str] | Sequence[str]) -> List[str]:
    return sorted({str(v).strip() for v in values if str(v).strip()}, key=str.casefold)


def _join_labels(labels: Sequence[str]) -> str:
    cleaned = [str(label).strip().lower() for label in labels if str(label).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    return f"{cleaned[0]} / {cleaned[1]}"


def _format_runtime(minutes: int) -> str:
    total = max(0, int(minutes or 0))
    hours, mins = divmod(total, 60)
    if hours and mins:
        return f"~{hours}h {mins}m"
    if hours:
        return f"~{hours}h"
    return f"~{mins}m"
