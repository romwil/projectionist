"""Lightweight watchlist curate + critique helpers for agent tools."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from curatorx.library.db import Database


def enrich_watchlist_pins(db: Database, pins: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    owned_movies = db.owned_tmdb_ids("movie")
    owned_shows_tmdb = db.owned_tmdb_ids("show")
    owned_tvdb = db.owned_tvdb_ids()
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
        if in_library:
            row = _lookup_library_row(db, media_type=media_type, tmdb_id=tmdb_id, tvdb_id=tvdb_id)
            if row is not None:
                view_count = int(row["view_count"] or 0)
                item["rating_key"] = row["rating_key"]
        item["view_count"] = view_count
        item["watched"] = view_count > 0
        enriched.append(item)
    return enriched


def _lookup_library_row(
    db: Database,
    *,
    media_type: str,
    tmdb_id: Optional[int],
    tvdb_id: Optional[int],
):
    with db.connect() as conn:
        if media_type == "movie" and tmdb_id is not None:
            return conn.execute(
                """
                SELECT rating_key, view_count FROM library_items
                WHERE media_type = 'movie' AND tmdb_id = ?
                LIMIT 1
                """,
                (int(tmdb_id),),
            ).fetchone()
        if media_type == "show" and tvdb_id is not None:
            return conn.execute(
                """
                SELECT rating_key, view_count FROM library_items
                WHERE media_type = 'show' AND tvdb_id = ?
                LIMIT 1
                """,
                (int(tvdb_id),),
            ).fetchone()
        if media_type == "show" and tmdb_id is not None:
            return conn.execute(
                """
                SELECT rating_key, view_count FROM library_items
                WHERE media_type = 'show' AND tmdb_id = ?
                LIMIT 1
                """,
                (int(tmdb_id),),
            ).fetchone()
    return None


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
