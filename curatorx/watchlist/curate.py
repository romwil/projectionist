"""Lightweight watchlist curate + critique helpers for agent tools."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

from curatorx.library.db import Database


def enrich_watchlist_pins(db: Database, pins: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Attach in_library / rating_key / watched flags (and poster/year when known).

    Uses a small number of bulk library lookups so large watchlists stay fast.
    """
    owned_movies = db.owned_tmdb_ids("movie")
    owned_shows_tmdb = db.owned_tmdb_ids("show")
    owned_tvdb = db.owned_tvdb_ids()
    library_by_key = _bulk_library_lookup(db, pins)

    enriched: List[Dict[str, Any]] = []
    for pin in pins:
        item = dict(pin)
        media_type = str(pin.get("media_type") or "movie")
        tmdb_id = pin.get("tmdb_id")
        tvdb_id = pin.get("tvdb_id")
        in_library = False
        if media_type == "movie" and tmdb_id is not None:
            in_library = int(tmdb_id) in owned_movies
        elif media_type == "show":
            if tvdb_id is not None and int(tvdb_id) in owned_tvdb:
                in_library = True
            elif tmdb_id is not None and int(tmdb_id) in owned_shows_tmdb:
                in_library = True
        item["in_library"] = in_library
        view_count = 0
        row = _row_for_pin(library_by_key, media_type=media_type, tmdb_id=tmdb_id, tvdb_id=tvdb_id)
        if row is not None:
            view_count = int(row.get("view_count") or 0)
            if row.get("rating_key"):
                item["rating_key"] = row["rating_key"]
            if not item.get("poster_url") and row.get("poster_url"):
                item["poster_url"] = str(row["poster_url"])
            if item.get("year") is None and row.get("year") is not None:
                item["year"] = int(row["year"])
        item["view_count"] = view_count
        item["watched"] = view_count > 0
        enriched.append(item)
    return enriched


def attach_watchlist_posters(db: Database, items: List[Dict[str, Any]]) -> None:
    """Fill missing poster_url + year from the library index (bulk)."""
    pending = [item for item in items if not (item.get("poster_url") and item.get("year"))]
    if not pending:
        return
    library_by_key = _bulk_library_lookup(db, pending)
    for item in pending:
        row = _row_for_pin(
            library_by_key,
            media_type=str(item.get("media_type") or "movie"),
            tmdb_id=item.get("tmdb_id"),
            tvdb_id=item.get("tvdb_id"),
        )
        if row is None:
            continue
        if not item.get("poster_url") and row.get("poster_url"):
            item["poster_url"] = str(row["poster_url"])
        if item.get("year") is None and row.get("year") is not None:
            item["year"] = int(row["year"])


def _row_for_pin(
    library_by_key: Dict[Tuple[str, str, int], Dict[str, Any]],
    *,
    media_type: str,
    tmdb_id: Optional[int],
    tvdb_id: Optional[int],
) -> Optional[Dict[str, Any]]:
    if media_type == "movie" and tmdb_id is not None:
        return library_by_key.get(("movie", "tmdb", int(tmdb_id)))
    if media_type == "show":
        if tvdb_id is not None:
            hit = library_by_key.get(("show", "tvdb", int(tvdb_id)))
            if hit is not None:
                return hit
        if tmdb_id is not None:
            return library_by_key.get(("show", "tmdb", int(tmdb_id)))
    return None


def _bulk_library_lookup(
    db: Database, pins: List[Mapping[str, Any]]
) -> Dict[Tuple[str, str, int], Dict[str, Any]]:
    movie_tmdbs: List[int] = []
    show_tvdbs: List[int] = []
    show_tmdbs: List[int] = []
    for pin in pins:
        media_type = str(pin.get("media_type") or "movie")
        tmdb_id = pin.get("tmdb_id")
        tvdb_id = pin.get("tvdb_id")
        if media_type == "movie" and tmdb_id is not None:
            movie_tmdbs.append(int(tmdb_id))
        elif media_type == "show":
            if tvdb_id is not None:
                show_tvdbs.append(int(tvdb_id))
            if tmdb_id is not None:
                show_tmdbs.append(int(tmdb_id))

    movie_tmdbs = sorted(set(movie_tmdbs))
    show_tvdbs = sorted(set(show_tvdbs))
    show_tmdbs = sorted(set(show_tmdbs))
    out: Dict[Tuple[str, str, int], Dict[str, Any]] = {}
    if not movie_tmdbs and not show_tvdbs and not show_tmdbs:
        return out

    with db.connect() as conn:
        if movie_tmdbs:
            placeholders = ",".join("?" * len(movie_tmdbs))
            rows = conn.execute(
                f"""
                SELECT media_type, tmdb_id, tvdb_id, rating_key, view_count, poster_url, year
                FROM library_items
                WHERE media_type = 'movie' AND tmdb_id IN ({placeholders})
                """,
                movie_tmdbs,
            ).fetchall()
            for row in rows:
                if row["tmdb_id"] is None:
                    continue
                out[("movie", "tmdb", int(row["tmdb_id"]))] = dict(row)
        if show_tvdbs:
            placeholders = ",".join("?" * len(show_tvdbs))
            rows = conn.execute(
                f"""
                SELECT media_type, tmdb_id, tvdb_id, rating_key, view_count, poster_url, year
                FROM library_items
                WHERE media_type = 'show' AND tvdb_id IN ({placeholders})
                """,
                show_tvdbs,
            ).fetchall()
            for row in rows:
                if row["tvdb_id"] is None:
                    continue
                out[("show", "tvdb", int(row["tvdb_id"]))] = dict(row)
        if show_tmdbs:
            placeholders = ",".join("?" * len(show_tmdbs))
            rows = conn.execute(
                f"""
                SELECT media_type, tmdb_id, tvdb_id, rating_key, view_count, poster_url, year
                FROM library_items
                WHERE media_type = 'show' AND tmdb_id IN ({placeholders})
                """,
                show_tmdbs,
            ).fetchall()
            for row in rows:
                if row["tmdb_id"] is None:
                    continue
                key = ("show", "tmdb", int(row["tmdb_id"]))
                # Prefer a tvdb match already recorded for the same show.
                out.setdefault(key, dict(row))
    return out


def _lookup_library_row(
    db: Database,
    *,
    media_type: str,
    tmdb_id: Optional[int],
    tvdb_id: Optional[int],
):
    """Legacy single-row lookup kept for callers/tests; prefer bulk path above."""
    hits = _bulk_library_lookup(
        db,
        [{"media_type": media_type, "tmdb_id": tmdb_id, "tvdb_id": tvdb_id}],
    )
    return _row_for_pin(hits, media_type=media_type, tmdb_id=tmdb_id, tvdb_id=tvdb_id)


def curate_watchlist(
    db: Database,
    pins: List[Mapping[str, Any]],
    *,
    limit: int = 12,
) -> Dict[str, Any]:
    enriched = enrich_watchlist_pins(db, pins)
    remove_suggestions = [
        {
            "action": "remove",
            "title": item["title"],
            "media_type": item["media_type"],
            "tmdb_id": item.get("tmdb_id"),
            "tvdb_id": item.get("tvdb_id"),
            "pin_id": item.get("id"),
            "reason": "Already watched in your Plex library — safe prune candidate.",
        }
        for item in enriched
        if item.get("watched")
    ][:limit]
    return {
        "remove_suggestions": remove_suggestions,
        "add_suggestions": [],
        "note": (
            "Suggestions only — do not remove pins unless the user confirms. "
            "Add suggestions come from other discovery tools when needed."
        ),
        "count_remove": len(remove_suggestions),
    }


def critique_watchlist(
    pins: List[Mapping[str, Any]],
    *,
    persona: Optional[Mapping[str, Any]] = None,
    focus_title: Optional[str] = None,
) -> Dict[str, Any]:
    snark = float((persona or {}).get("val_dipl_snark") or 0.5)
    warmth = float((persona or {}).get("val_warmth") or (persona or {}).get("val_warm_cool") or 0.5)
    cinephile = float((persona or {}).get("val_highbrow") or (persona or {}).get("val_cinephile") or 0.5)
    enriched_count = len(pins)
    titles = [str(p.get("title") or "Untitled") for p in pins[:8]]
    focus = (focus_title or "").strip()

    if enriched_count == 0:
        if snark >= 0.66:
            text = "Your watchlist is a blank canvas — ambitious, or just avoidance with better lighting?"
        elif warmth >= 0.66:
            text = "Nothing pinned yet. When you're ready, I'll help you stack a list worth finishing."
        else:
            text = "Watchlist is empty. Pin a few titles from recommendations to get started."
        return {"critique": text, "pin_count": 0, "focus_title": focus or None}

    sample = ", ".join(titles[:5])
    if focus:
        target = next((t for t in titles if focus.lower() in t.lower()), focus)
        if snark >= 0.66:
            text = f"Keeping {target} on the list? Bold. Either it's destiny or you're collecting hope."
        elif cinephile >= 0.66:
            text = f"{target} still waits — a deliberate hold, or taste debt you haven't paid yet?"
        else:
            text = f"{target} is still pinned. Watch soon, or demote it when the mood shifts."
    else:
        if snark >= 0.66:
            text = (
                f"{enriched_count} titles queued ({sample}"
                f"{'…' if enriched_count > 5 else ''}). "
                "Half of these will become lore about what you meant to watch."
            )
        elif warmth >= 0.66:
            text = (
                f"You've got {enriched_count} waiting — {sample}"
                f"{'…' if enriched_count > 5 else ''}. Solid stack; prune anything already watched."
            )
        else:
            text = (
                f"Watchlist has {enriched_count} titles ({sample}"
                f"{'…' if enriched_count > 5 else ''}). "
                "I'd start with the ones not already in your library."
            )
    return {
        "critique": text,
        "pin_count": enriched_count,
        "focus_title": focus or None,
        "sample_titles": titles,
    }
