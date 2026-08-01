"""Additive craft filters + exclusion for Live Channels recipe fill.

AND-stack genres, decade/year, motif/theme, and optional content rating on a
base pool (media_scope / collection / taste). Exclusion collection
titles (default Plex name ``NoLive``) are skipped during fill and starters.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

from projectionist.live_channels.recipes import MediaScope, normalize_media_scope


@dataclass(frozen=True)
class CraftFilters:
    """AND-combined craft filters persisted on ``station_meta`` / recipes."""

    genres: tuple[str, ...] = ()
    decade: Optional[int] = None  # e.g. 1970 for the 1970s
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    motifs: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    content_ratings: tuple[str, ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["genres"] = list(self.genres)
        payload["motifs"] = list(self.motifs)
        payload["themes"] = list(self.themes)
        payload["content_ratings"] = list(self.content_ratings)
        return payload

    def is_empty(self) -> bool:
        return not (
            self.genres
            or self.decade is not None
            or self.year_from is not None
            or self.year_to is not None
            or self.motifs
            or self.themes
            or self.content_ratings
        )


def _parse_str_tuple(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        parts = [p.strip() for p in value.split(",") if p.strip()]
        return tuple(parts)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(v).strip() for v in value if str(v).strip())
    return ()


def _optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip().lower().rstrip("s")
    # Accept "1970s" / "70s"
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except (TypeError, ValueError):
        return None


def normalize_craft_filters(data: Any = None) -> CraftFilters:
    """Normalize API / station_meta filter payloads."""
    raw = data if isinstance(data, Mapping) else {}
    decade = _optional_int(raw.get("decade"))
    if decade is not None:
        # Accept 70 / 1970 / "1970s"
        if decade < 100:
            decade = 1900 + decade if decade >= 70 else 2000 + decade
        decade = (decade // 10) * 10
    year_from = _optional_int(raw.get("year_from"))
    year_to = _optional_int(raw.get("year_to"))
    if decade is not None and year_from is None and year_to is None:
        year_from = decade
        year_to = decade + 9
    return CraftFilters(
        genres=_parse_str_tuple(raw.get("genres")),
        decade=decade,
        year_from=year_from,
        year_to=year_to,
        motifs=_parse_str_tuple(raw.get("motifs") or raw.get("motif")),
        themes=_parse_str_tuple(raw.get("themes") or raw.get("theme")),
        content_ratings=_parse_str_tuple(
            raw.get("content_ratings") or raw.get("content_rating")
        ),
    )


def exclusion_collection_name(settings: Any = None) -> str:
    tunarr = getattr(settings, "tunarr", None) if settings is not None else None
    name = str(getattr(tunarr, "exclusion_collection_name", "") or "").strip()
    return name or "NoLive"


def resolve_exclusion_collection_id(settings: Any = None) -> str:
    """Return configured exclusion collection id, or resolve by name from Plex."""
    tunarr = getattr(settings, "tunarr", None) if settings is not None else None
    configured = str(getattr(tunarr, "exclusion_collection_id", "") or "").strip()
    if configured:
        return configured
    wanted = exclusion_collection_name(settings).casefold()
    if not wanted or settings is None:
        return ""
    try:
        from projectionist.live_channels.craft import _load_plex_collections

        rows, _err = _load_plex_collections(settings)
        for row in rows:
            title = str(row.get("title") or "").strip()
            if title.casefold() == wanted:
                return str(row.get("id") or "").strip()
    except Exception:  # noqa: BLE001
        return ""
    return ""


def exclusion_rating_keys(
    settings: Any = None,
    *,
    limit: int = 500,
) -> Set[str]:
    """Plex ratingKeys in the exclusion collection (empty when unset/missing)."""
    cid = resolve_exclusion_collection_id(settings)
    if not cid:
        return set()
    try:
        from projectionist.live_channels.publish import plex_collection_rating_keys

        return {
            str(k).strip()
            for k in plex_collection_rating_keys(settings, cid, limit=limit)
            if str(k).strip()
        }
    except Exception:  # noqa: BLE001
        return set()


def _media_type_for_scope(scope: str) -> Optional[str]:
    scope_n = normalize_media_scope(scope)
    if scope_n == MediaScope.MOVIES.value:
        return "movie"
    if scope_n == MediaScope.TV.value:
        return "show"
    return None


def library_items_matching_filters(
    db: Any,
    filters: CraftFilters,
    *,
    media_scope: str = MediaScope.BOTH.value,
    limit: int = 500,
) -> Dict[str, Any]:
    """Query Projectionist library for titles matching the AND filter stack."""
    if db is None or filters.is_empty():
        return {"total_matched": 0, "items": [], "rating_keys": []}
    from projectionist.library.query import LibraryFilters, query_library

    media_type = _media_type_for_scope(media_scope)
    lib_filters = LibraryFilters(
        media_type=media_type,
        genres=list(filters.genres),
        motifs=list(filters.motifs),
        themes=list(filters.themes),
        content_ratings=list(filters.content_ratings),
        year_from=filters.year_from,
        year_to=filters.year_to,
        plot_match_mode="motifs" if filters.motifs and not filters.themes else "hybrid",
        limit=min(max(1, int(limit or 500)), 500),
        offset=0,
    )
    try:
        payload = query_library(db, lib_filters)
    except Exception:  # noqa: BLE001
        return {"total_matched": 0, "items": [], "rating_keys": []}
    items = list(payload.get("items") or [])
    keys = [
        str(item.get("rating_key") or "").strip()
        for item in items
        if str(item.get("rating_key") or "").strip()
    ]
    return {
        "total_matched": int(payload.get("total_matched") or len(items)),
        "items": items,
        "rating_keys": keys,
    }


def preview_craft_match_count(
    db: Any,
    *,
    filters: CraftFilters | Mapping[str, Any] | None = None,
    media_scope: str = MediaScope.BOTH.value,
    collection_id: str = "",
    source: str = "",
    settings: Any = None,
    limit: int = 1000,
) -> Dict[str, Any]:
    """Preview how many library titles match filters (+ optional collection ∩)."""
    from projectionist.live_channels.publish import (
        craft_fill_mode,
        craft_soft_cap_honesty,
        plex_collection_rating_keys,
    )

    craft = (
        filters
        if isinstance(filters, CraftFilters)
        else normalize_craft_filters(filters)
    )
    excluded = exclusion_rating_keys(settings)
    excluded_n = 0
    cid = str(collection_id or "").strip()
    fill_mode = craft_fill_mode(collection_id=cid, source=source)

    collection_keys: Optional[Set[str]] = None
    if cid:
        try:
            collection_keys = {
                str(k).strip()
                for k in plex_collection_rating_keys(settings, cid, limit=limit)
                if str(k).strip()
            }
        except Exception:  # noqa: BLE001
            collection_keys = set()

    def _with_honesty(payload: Dict[str, Any], *, matched: int = 0) -> Dict[str, Any]:
        h = craft_soft_cap_honesty(fill_mode=fill_mode, matched=matched)
        payload.update(
            {
                "fill_mode": h["fill_mode"],
                "soft_capped": h["soft_capped"],
                "soft_default": h["soft_default"],
                "soft_cap": h["soft_cap"],
                "full_run_cap": h["full_run_cap"],
            }
        )
        base_note = str(payload.get("note") or "").strip()
        if h["soft_capped"]:
            payload["note"] = f"{base_note} {h['note']}".strip() if base_note else h["note"]
        elif base_note and fill_mode == "full_run":
            payload["note"] = f"{base_note} {h['note']}".strip()
        return payload

    if craft.is_empty() and collection_keys is None:
        # Scope-only preview from library counts is expensive; report unknown.
        return _with_honesty(
            {
                "matched": 0,
                "match_total": 0,
                "excluded": 0,
                "filters": craft.to_dict(),
                "note": "Add filters or a collection to preview a match count.",
            }
        )

    if craft.is_empty() and collection_keys is not None:
        keys = [k for k in collection_keys if k not in excluded]
        excluded_n = len(collection_keys) - len(keys)
        return _with_honesty(
            {
                "matched": len(keys),
                "match_total": len(collection_keys),
                "excluded": excluded_n,
                "filters": craft.to_dict(),
                "collection_id": cid,
                "note": f"{len(keys)} titles in collection after exclusion.",
            },
            matched=len(keys),
        )

    lib = library_items_matching_filters(
        db, craft, media_scope=media_scope, limit=limit
    )
    keys = list(lib.get("rating_keys") or [])
    if collection_keys is not None:
        keys = [k for k in keys if k in collection_keys]
    before_excl = len(keys)
    keys = [k for k in keys if k not in excluded]
    excluded_n = before_excl - len(keys)
    total = int(lib.get("total_matched") or before_excl)
    if collection_keys is not None:
        total = before_excl
    return _with_honesty(
        {
            "matched": len(keys),
            "match_total": total,
            "excluded": excluded_n,
            "filters": craft.to_dict(),
            "collection_id": cid or None,
            "rating_keys_sample": keys[:12],
            "note": (
                f"Matched {len(keys)} title(s)"
                + (f" · skipped {excluded_n} excluded" if excluded_n else "")
                + "."
            ),
        },
        matched=len(keys),
    )


def _year_from_program(item: Mapping[str, Any]) -> Optional[int]:
    for key in ("year", "releaseYear", "originallyAvailableAt"):
        raw = item.get(key)
        if raw is None:
            continue
        if isinstance(raw, int):
            return raw if raw > 1000 else None
        text = str(raw).strip()
        if len(text) >= 4 and text[:4].isdigit():
            return int(text[:4])
    return None


def _genres_from_program(item: Mapping[str, Any]) -> List[str]:
    genres = item.get("genres") or item.get("tags") or []
    if not isinstance(genres, list):
        return []
    return [str(g).strip() for g in genres if str(g).strip()]


def _rating_from_program(item: Mapping[str, Any]) -> str:
    for key in ("content_rating", "contentRating", "rating"):
        text = str(item.get(key) or "").strip()
        if text:
            return text
    return ""


def program_matches_tunarr_filters(
    item: Mapping[str, Any],
    filters: CraftFilters,
) -> bool:
    """Best-effort Tunarr-row filter when library ratingKeys are unavailable."""
    if filters.is_empty():
        return True
    if filters.genres:
        blob = " ".join(_genres_from_program(item)).casefold()
        if not all(g.casefold() in blob for g in filters.genres):
            return False
    year = _year_from_program(item)
    if filters.year_from is not None:
        if year is None or year < filters.year_from:
            return False
    if filters.year_to is not None:
        if year is None or year > filters.year_to:
            return False
    if filters.content_ratings:
        rating = _rating_from_program(item).casefold()
        allowed = {r.casefold() for r in filters.content_ratings}
        if rating not in allowed:
            return False
    # Motif/theme cannot be evaluated from Tunarr rows alone — require key intersect.
    if filters.motifs or filters.themes:
        return False
    return True


def apply_craft_filters_to_pool(
    pool: Sequence[Mapping[str, Any]],
    filters: CraftFilters,
    *,
    allowed_rating_keys: Optional[Set[str]] = None,
    excluded_rating_keys: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Filter a Tunarr program pool by craft filters + exclusion keys."""
    excluded = excluded_rating_keys or set()
    out: List[Dict[str, Any]] = []
    for item in pool:
        if not isinstance(item, Mapping):
            continue
        plex_keys = {
            str(k).strip()
            for k in (item.get("plex_keys") or ())
            if str(k).strip()
        }
        if excluded and plex_keys & excluded:
            continue
        if allowed_rating_keys is not None:
            if not plex_keys or not (plex_keys & allowed_rating_keys):
                continue
        elif not filters.is_empty():
            if not program_matches_tunarr_filters(item, filters):
                continue
        out.append(dict(item))
    return out


def craft_filter_options(db: Any = None) -> Dict[str, Any]:
    """Facet chips for Admin craft UI (reuse Explore/library catalogs)."""
    genres: List[Dict[str, Any]] = []
    decades: List[Dict[str, Any]] = []
    motifs: List[Dict[str, Any]] = []
    themes: List[Dict[str, Any]] = []
    ratings: List[Dict[str, Any]] = []
    if db is None:
        return {
            "genres": genres,
            "decades": decades,
            "motifs": motifs,
            "themes": themes,
            "content_ratings": ratings,
        }
    try:
        from projectionist.library.facets import library_facet_catalog
        from projectionist.library.query import LibraryFilters, aggregate_library

        for row in (library_facet_catalog(db, "motif", limit=24).get("facets") or []):
            value = str(row.get("value") or "").strip()
            if value:
                motifs.append({"value": value, "count": int(row.get("count") or 0), "label": value})
        for row in (library_facet_catalog(db, "theme", limit=24).get("facets") or []):
            value = str(row.get("value") or "").strip()
            if value:
                themes.append({"value": value, "count": int(row.get("count") or 0), "label": value})
        genre_agg = aggregate_library(db, "genre", LibraryFilters(limit=1), top_examples=0)
        for bucket in genre_agg.get("buckets") or []:
            value = str(bucket.get("genre") or bucket.get("value") or "").strip()
            if value:
                genres.append(
                    {
                        "value": value,
                        "count": int(bucket.get("count") or 0),
                        "label": value,
                    }
                )
        genres = genres[:24]
        decade_agg = aggregate_library(db, "decade", LibraryFilters(limit=1), top_examples=0)
        for bucket in decade_agg.get("buckets") or []:
            start = bucket.get("decade_start")
            label = str(bucket.get("decade") or "").strip()
            if start is None:
                continue
            decades.append(
                {
                    "value": int(start),
                    "label": label or f"{int(start)}s",
                    "count": int(bucket.get("count") or 0),
                }
            )
        rating_agg = aggregate_library(
            db, "content_rating", LibraryFilters(limit=1), top_examples=0
        )
        for bucket in rating_agg.get("buckets") or []:
            value = str(
                bucket.get("content_rating") or bucket.get("value") or ""
            ).strip()
            if value:
                ratings.append(
                    {
                        "value": value,
                        "count": int(bucket.get("count") or 0),
                        "label": value,
                    }
                )
        ratings = ratings[:16]
    except Exception:  # noqa: BLE001
        pass
    return {
        "genres": genres,
        "decades": decades,
        "motifs": motifs,
        "themes": themes,
        "content_ratings": ratings,
    }
