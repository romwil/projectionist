"""Craft filters + exclusion for Live Channels recipe fill.

Composition model (DNF — disjunctive normal form):
  - One or more **groups**. A title matches if **any** group matches (OR).
  - Inside a group, dimensions combine with **AND** (genre ∩ decade ∩ theme…).
  - Multi-value within one dimension (e.g. two genres) is **OR** within that dim.

Legacy flat ``station_meta.craft_filters`` (no ``groups`` / ``version``) normalizes
to a single AND-group and still round-trips as the flat dict.

Exclusion collection titles (default Plex name ``NoLive``) are skipped during
fill and starters.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from projectionist.live_channels.recipes import MediaScope, normalize_media_scope


@dataclass(frozen=True)
class CraftFilters:
    """Craft filter set: OR of AND-groups (see module docstring).

    Flat fields describe the **primary** group so existing call sites
    (``CraftFilters(genres=("Horror",), decade=1970)``) keep working.
    Additional OR groups live in ``or_groups`` (each a flat filter dict).
    """

    genres: tuple[str, ...] = ()
    decade: Optional[int] = None  # e.g. 1970 for the 1970s
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    motifs: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    content_ratings: tuple[str, ...] = ()
    # Extra AND-groups OR'd with the primary flat fields (version-2 payloads).
    or_groups: tuple[Dict[str, Any], ...] = ()

    def to_dict(self) -> Dict[str, Any]:
        groups = list(self.iter_group_dicts())
        if len(groups) <= 1:
            return groups[0] if groups else _empty_group_dict()
        return {"version": 2, "groups": groups}

    def is_empty(self) -> bool:
        return all(normalize_craft_filters(g).is_empty_primary() for g in self.iter_group_dicts())

    def is_empty_primary(self) -> bool:
        """True when the flat primary fields alone are empty (ignore or_groups)."""
        return not (
            self.genres
            or self.decade is not None
            or self.year_from is not None
            or self.year_to is not None
            or self.motifs
            or self.themes
            or self.content_ratings
        )

    def primary_dict(self) -> Dict[str, Any]:
        return {
            "genres": list(self.genres),
            "decade": self.decade,
            "year_from": self.year_from,
            "year_to": self.year_to,
            "motifs": list(self.motifs),
            "themes": list(self.themes),
            "content_ratings": list(self.content_ratings),
        }

    def iter_group_dicts(self) -> List[Dict[str, Any]]:
        groups: List[Dict[str, Any]] = []
        if not self.is_empty_primary():
            groups.append(self.primary_dict())
        for raw in self.or_groups:
            if isinstance(raw, Mapping) and not _group_mapping_empty(raw):
                groups.append(dict(raw))
        return groups

    def iter_groups(self) -> Tuple["CraftFilters", ...]:
        """Normalized single-group CraftFilters (no nested or_groups) for matching."""
        out: List[CraftFilters] = []
        for raw in self.iter_group_dicts():
            g = _normalize_flat_group(raw)
            if not g.is_empty_primary():
                out.append(g)
        return tuple(out)


def _empty_group_dict() -> Dict[str, Any]:
    return {
        "genres": [],
        "decade": None,
        "year_from": None,
        "year_to": None,
        "motifs": [],
        "themes": [],
        "content_ratings": [],
    }


def _group_mapping_empty(raw: Mapping[str, Any]) -> bool:
    return _normalize_flat_group(raw).is_empty_primary()


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


def _normalize_flat_group(raw: Mapping[str, Any]) -> CraftFilters:
    """Parse one AND-group (never reads version/groups/or_groups)."""
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
        or_groups=(),
    )


def normalize_craft_filters(data: Any = None) -> CraftFilters:
    """Normalize API / station_meta filter payloads (legacy flat or version-2 groups)."""
    if isinstance(data, CraftFilters):
        return data
    raw = data if isinstance(data, Mapping) else {}
    groups_raw = raw.get("groups")
    version = raw.get("version")
    if isinstance(groups_raw, (list, tuple)) and (
        version == 2 or (groups_raw and not _has_flat_filter_keys(raw))
    ):
        parsed = [_normalize_flat_group(g) for g in groups_raw if isinstance(g, Mapping)]
        parsed = [g for g in parsed if not g.is_empty_primary()]
        if not parsed:
            return CraftFilters()
        primary = parsed[0]
        extras = tuple(g.primary_dict() for g in parsed[1:])
        return CraftFilters(
            genres=primary.genres,
            decade=primary.decade,
            year_from=primary.year_from,
            year_to=primary.year_to,
            motifs=primary.motifs,
            themes=primary.themes,
            content_ratings=primary.content_ratings,
            or_groups=extras,
        )
    return _normalize_flat_group(raw)


def _has_flat_filter_keys(raw: Mapping[str, Any]) -> bool:
    return any(
        key in raw
        for key in (
            "genres",
            "decade",
            "year_from",
            "year_to",
            "motifs",
            "motif",
            "themes",
            "theme",
            "content_ratings",
            "content_rating",
        )
    )


def _titleish(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.title() if text.islower() else text


def _group_label(group: CraftFilters) -> str:
    bits: List[str] = []
    if group.motifs:
        bits.append(_titleish(group.motifs[0]))
    if group.genres:
        bits.append(_titleish(group.genres[0]))
    if group.decade is not None:
        bits.append(f"{int(group.decade)}s")
    if group.themes:
        bits.append(_titleish(group.themes[0]))
    if group.content_ratings:
        bits.append(str(group.content_ratings[0]).strip().upper())
    return " ∩ ".join(bits) if bits else ""


def craft_filters_station_name(
    filters: CraftFilters | Mapping[str, Any] | None = None,
    *,
    motif: str = "",
    cluster_tag: str = "",
) -> str:
    """Build a short station label from craft filters (+ optional motif/cluster).

    Additive filters are part of the station identity — a decade-only craft should
    not silently reuse a bare motif name that already exists on the dial.
    """
    craft = (
        filters
        if isinstance(filters, CraftFilters)
        else normalize_craft_filters(filters)
    )
    groups = craft.iter_groups()
    if len(groups) > 1:
        labels = [lab for lab in (_group_label(g) for g in groups) if lab]
        if labels:
            return " / ".join(labels)[:48]
    bits: List[str] = []
    motif_label = _titleish(motif) or (
        _titleish(craft.motifs[0]) if craft.motifs else ""
    )
    cluster_label = _titleish(cluster_tag)
    if motif_label:
        bits.append(motif_label)
    elif cluster_label:
        bits.append(cluster_label)
    if craft.genres:
        bits.append(_titleish(craft.genres[0]))
    if craft.decade is not None:
        bits.append(f"{int(craft.decade)}s")
    if craft.themes:
        bits.append(_titleish(craft.themes[0]))
    if craft.content_ratings:
        bits.append(str(craft.content_ratings[0]).strip().upper())
    # Drop duplicate adjacent tokens (motif "Mystery" + genre "Mystery").
    deduped: List[str] = []
    seen: Set[str] = set()
    for bit in bits:
        key = bit.casefold()
        if not bit or key in seen:
            continue
        seen.add(key)
        deduped.append(bit)
    return " · ".join(deduped)[:48]


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
    """Query Projectionist library for titles matching the filter set (OR of groups)."""
    craft = (
        filters
        if isinstance(filters, CraftFilters)
        else normalize_craft_filters(filters)
    )
    if db is None or craft.is_empty():
        return {"total_matched": 0, "items": [], "rating_keys": []}

    groups = craft.iter_groups()
    if len(groups) <= 1:
        return _library_items_matching_one_group(
            db,
            groups[0] if groups else CraftFilters(),
            media_scope=media_scope,
            limit=limit,
        )

    # Union OR-groups; preserve first-seen order.
    seen: Set[str] = set()
    items: List[Dict[str, Any]] = []
    keys: List[str] = []
    total = 0
    per_group_limit = max(limit, 100)
    for group in groups:
        part = _library_items_matching_one_group(
            db, group, media_scope=media_scope, limit=per_group_limit
        )
        total += int(part.get("total_matched") or 0)
        for item in part.get("items") or []:
            key = str(item.get("rating_key") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            items.append(item)
            keys.append(key)
            if len(keys) >= limit:
                break
        if len(keys) >= limit:
            break
    return {
        "total_matched": max(total, len(keys)),
        "items": items[:limit],
        "rating_keys": keys[:limit],
    }


def _library_items_matching_one_group(
    db: Any,
    filters: CraftFilters,
    *,
    media_scope: str,
    limit: int,
) -> Dict[str, Any]:
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
    group_n = len(craft.iter_groups())
    note = (
        f"Matched {len(keys)} title(s)"
        + (f" across {group_n} pools" if group_n > 1 else "")
        + (f" · skipped {excluded_n} excluded" if excluded_n else "")
        + "."
    )
    return _with_honesty(
        {
            "matched": len(keys),
            "match_total": total,
            "excluded": excluded_n,
            "filters": craft.to_dict(),
            "collection_id": cid or None,
            "rating_keys_sample": keys[:12],
            "note": note,
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


def _program_matches_one_group(item: Mapping[str, Any], filters: CraftFilters) -> bool:
    """Tunarr-row match for a single AND-group (multi-value dims are OR)."""
    if filters.is_empty_primary():
        return True
    if filters.genres:
        blob = " ".join(_genres_from_program(item)).casefold()
        if not any(g.casefold() in blob for g in filters.genres):
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


def program_matches_tunarr_filters(
    item: Mapping[str, Any],
    filters: CraftFilters,
) -> bool:
    """Best-effort Tunarr-row filter when library ratingKeys are unavailable."""
    craft = (
        filters
        if isinstance(filters, CraftFilters)
        else normalize_craft_filters(filters)
    )
    if craft.is_empty():
        return True
    groups = craft.iter_groups()
    if not groups:
        return True
    return any(_program_matches_one_group(item, g) for g in groups)


def apply_craft_filters_to_pool(
    pool: Sequence[Mapping[str, Any]],
    filters: CraftFilters,
    *,
    allowed_rating_keys: Optional[Set[str]] = None,
    excluded_rating_keys: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Filter a Tunarr program pool by craft filters + exclusion keys."""
    craft = (
        filters
        if isinstance(filters, CraftFilters)
        else normalize_craft_filters(filters)
    )
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
        elif not craft.is_empty():
            if not program_matches_tunarr_filters(item, craft):
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


def maintain_live_channel_lineups(
    client: Any,
    settings: Any = None,
    *,
    min_programs: int = 5,
    min_duration_ms: int = 60_000,
    limit: int = 40,
    should_stop: Optional[Any] = None,
) -> Dict[str, Any]:
    """Refill stations whose Tunarr lineups are empty or below threshold.

    Used by the ``live_channels_feed`` idle task so Admin Refill is not a
    daily ritual. Skips when Live Channels / Tunarr are off. Only stations with
    a stored ``station_meta`` recipe are refilled.
    """
    from projectionist.live_channels.publish import (
        recipe_from_station_meta,
        refill_channel_lineup,
    )

    if settings is None or client is None:
        return {
            "ok": False,
            "refilled": [],
            "skipped": [],
            "errors": [],
            "note": "No settings or Tunarr client.",
        }
    features = getattr(settings, "features", None)
    if not bool(getattr(features, "live_channels_enabled", False)):
        return {
            "ok": True,
            "refilled": [],
            "skipped": [],
            "errors": [],
            "skipped_reason": "live_channels_disabled",
            "note": "Live Channels off.",
        }

    listed = [ch for ch in client.list_channels() if isinstance(ch, Mapping)]
    refilled: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    threshold = max(1, int(min_programs or 5))
    min_dur = max(0, int(min_duration_ms or 0))

    for ch in listed[: max(1, min(int(limit or 40), 80))]:
        if should_stop is not None:
            try:
                if should_stop():
                    break
            except Exception:  # noqa: BLE001
                pass
        cid = str(ch.get("id") or ch.get("uuid") or "").strip()
        if not cid:
            continue
        name = str(ch.get("name") or "").strip() or f"Channel {ch.get('number')}"
        try:
            program_count = int(ch.get("programCount") or 0)
        except (TypeError, ValueError):
            program_count = 0
        try:
            duration_ms = int(ch.get("duration") or 0)
        except (TypeError, ValueError):
            duration_ms = 0
        thin = program_count < threshold or (min_dur and duration_ms < min_dur)
        if not thin:
            skipped.append(
                {
                    "channel_id": cid,
                    "name": name,
                    "program_count": program_count,
                    "reason": "healthy",
                }
            )
            continue
        stored = recipe_from_station_meta(
            settings,
            cid,
            name=name,
            number=int(ch.get("number") or 0) or 100,
        )
        if stored is None:
            skipped.append(
                {
                    "channel_id": cid,
                    "name": name,
                    "program_count": program_count,
                    "reason": "no_recipe",
                }
            )
            continue
        try:
            result = refill_channel_lineup(
                client,
                cid,
                settings=settings,
                pad_lineups=True,
                attach_continuity=True,
            )
            refilled.append(
                {
                    "channel_id": cid,
                    "name": name,
                    "previous_program_count": program_count,
                    "program_count": int(result.get("program_count") or 0),
                    "ok": bool(result.get("ok")),
                    "note": str(result.get("note") or "")[:160],
                }
            )
        except Exception as error:  # noqa: BLE001
            errors.append({"channel_id": cid, "name": name, "error": str(error)[:200]})

    return {
        "ok": not errors or bool(refilled),
        "refilled": refilled,
        "skipped": skipped,
        "errors": errors,
        "count_refilled": len(refilled),
        "count_errors": len(errors),
        "note": (
            f"Auto-fed {len(refilled)} thin/empty station(s)"
            + (f" · {len(errors)} error(s)" if errors else "")
            + "."
        ),
    }
