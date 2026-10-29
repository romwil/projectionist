"""Catalog match, queue pad, and programming bodies for Live publish."""

from __future__ import annotations

import random
import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.facets import motif_search_expansions
from projectionist.live_channels.recipes import (
    ChannelRecipe,
    MediaScope,
    ProgrammingMode,
    library_type_matches_scope,
    normalize_media_scope,
    normalize_programming_mode,
    program_type_matches_scope,
)

# Historical annotations used this name for the broadcast HTTP client.
TunarrClient = Any

_MIN_PROGRAM_DURATION_MS = 60_000
# Motif / taste / filtered craft soft default (not a hard product ceiling).
_DEFAULT_FILL_LIMIT = 30
_SOFT_FILL_CAP = 80
# Collection / show full-run: fill all ID-resolved episodes (safety cap).
_FULL_RUN_FILL_CAP = 1000
_DEFAULT_PAD_FLEX_MAX_MINUTES = 15


def ensure_media_libraries_enabled(*args: Any, **kwargs: Any) -> Dict[str, Any]:
    """Same-module name for collect_programs; implementation lives on the facade."""
    from projectionist.live_channels.publish import (
        ensure_media_libraries_enabled as _ensure_media_libraries_enabled,
    )

    return _ensure_media_libraries_enabled(*args, **kwargs)


def soft_fill_default() -> int:
    return _DEFAULT_FILL_LIMIT


def soft_fill_cap() -> int:
    return _SOFT_FILL_CAP


def full_run_fill_cap() -> int:
    return _FULL_RUN_FILL_CAP


def craft_fill_mode(*, collection_id: str = "", source: str = "") -> str:
    """Return ``full_run`` for collection/show stations, else ``soft``."""
    src = str(source or "").strip().lower()
    if src == "chaos":
        return "soft"
    if src in {"collection", "show"} or str(collection_id or "").strip():
        return "full_run"
    return "soft"


def craft_soft_cap_honesty(
    *,
    fill_mode: str = "soft",
    matched: int = 0,
    program_count: int = 0,
) -> Dict[str, Any]:
    """Owner-facing soft-cap honesty for Admin craft preview / publish feedback."""
    mode = "full_run" if str(fill_mode or "").strip().lower() == "full_run" else "soft"
    payload: Dict[str, Any] = {
        "fill_mode": mode,
        "soft_default": _DEFAULT_FILL_LIMIT,
        "soft_cap": _SOFT_FILL_CAP,
        "full_run_cap": _FULL_RUN_FILL_CAP,
        "soft_capped": mode == "soft",
    }
    if mode == "full_run":
        payload["note"] = (
            f"Collection/show stations fill the full resolved pool "
            f"(up to {_FULL_RUN_FILL_CAP} programs)."
        )
    else:
        count_bit = ""
        if program_count > 0:
            count_bit = f" This lineup scheduled {int(program_count)} program(s)."
        elif matched > 0:
            count_bit = f" Library matched {int(matched)} title(s)."
        payload["note"] = (
            f"Motif / taste craft samples about {_DEFAULT_FILL_LIMIT}–{_SOFT_FILL_CAP} "
            f"programs (soft cap) — not the full-run {_FULL_RUN_FILL_CAP} used for "
            f"collection/show stations.{count_bit}"
        )
    return payload


def pad_flex_max_ms(settings: Any = None) -> int:
    tunarr = getattr(settings, "tunarr", None) if settings is not None else None
    try:
        minutes = int(
            getattr(tunarr, "pad_flex_max_minutes", _DEFAULT_PAD_FLEX_MAX_MINUTES)
            or _DEFAULT_PAD_FLEX_MAX_MINUTES
        )
    except (TypeError, ValueError):
        minutes = _DEFAULT_PAD_FLEX_MAX_MINUTES
    minutes = max(0, min(minutes, 30))
    return minutes * 60 * 1000


def plex_collection_children(
    settings: Any,
    collection_id: str,
    *,
    limit: int = _FULL_RUN_FILL_CAP,
) -> List[Dict[str, str]]:
    """Plex collection children as ``{rating_key, title, thumb}`` (empty when unavailable)."""
    cid = str(collection_id or "").strip()
    if not cid or not cid.isdigit():
        return []
    plex_url = str(getattr(settings, "plex_url", "") or "").strip()
    plex_token = str(getattr(settings, "plex_token", "") or "").strip()
    if not plex_url or not plex_token:
        return []
    try:
        from projectionist.connectors.plex import PlexClient
        from projectionist.connectors.plex_collections import list_collection_items

        items = list_collection_items(
            PlexClient(plex_url, plex_token, timeout=20),
            cid,
            limit=limit,
        )
        return [
            {
                "rating_key": item.rating_key,
                "title": item.title,
                "thumb": item.thumb,
                "media_type": item.media_type,
            }
            for item in items
        ]
    except Exception:  # noqa: BLE001
        return []


def plex_collection_item_hints(
    settings: Any,
    collection_id: str,
    *,
    limit: int = _FULL_RUN_FILL_CAP,
) -> List[str]:
    """Title hints from a Plex collection rating key (empty when not a Plex id)."""
    return [
        row["title"]
        for row in plex_collection_children(settings, collection_id, limit=limit)
        if row.get("title")
    ]


def plex_collection_rating_keys(
    settings: Any,
    collection_id: str,
    *,
    limit: int = _FULL_RUN_FILL_CAP,
) -> List[str]:
    """Plex ratingKeys for collection children (preferred match path)."""
    return [
        row["rating_key"]
        for row in plex_collection_children(settings, collection_id, limit=limit)
        if row.get("rating_key")
    ]


def _extract_plex_rating_keys(item: Mapping[str, Any]) -> List[str]:
    """Collect Plex ratingKey forms from a Tunarr library-program / program row.

    Tunarr 1.3+ library program payloads often omit legacy ``externalKey`` and
    instead expose the Plex rating key as ``externalId`` and/or
    ``identifiers[{type: plex, id}]``. Nested ``show`` objects use the same
    shape — important so TV craft (library indexes *shows*) intersects episode
    catalog rows.
    """
    prog = item.get("program") if isinstance(item.get("program"), Mapping) else item
    if not isinstance(prog, Mapping):
        prog = item
    keys: List[str] = []

    def _add(raw: Any) -> None:
        text = str(raw or "").strip()
        if not text or text in keys:
            return
        keys.append(text)
        # Tunarr often stores ``plex|{sourceId}|{ratingKey}``.
        if "|" in text:
            tail = text.rsplit("|", 1)[-1].strip()
            if tail and tail not in keys:
                keys.append(tail)

    sources: List[Mapping[str, Any]] = []
    for candidate in (prog, item):
        if isinstance(candidate, Mapping) and candidate not in sources:
            sources.append(candidate)
    # Nested show (episode rows) — library craft matches show ratingKeys.
    for base in list(sources):
        show = base.get("show") if isinstance(base.get("show"), Mapping) else None
        if isinstance(show, Mapping) and show not in sources:
            sources.append(show)

    for source in sources:
        for field in (
            "externalKey",
            "externalId",
            "external_id",
            "plexRatingKey",
            "ratingKey",
        ):
            _add(source.get(field))
        identifiers = source.get("identifiers")
        if not isinstance(identifiers, list):
            continue
        for ident in identifiers:
            if not isinstance(ident, Mapping):
                continue
            itype = str(ident.get("type") or "").strip().lower()
            if itype not in {"plex", "plex-rating-key", "plex_rating_key"}:
                continue
            _add(ident.get("id") or ident.get("key"))
    return keys


def match_feedback_note(
    *,
    matched: int = 0,
    match_total: int = 0,
    program_count: int = 0,
    stations_filled: int = 0,
    full_run: Optional[bool] = None,
    soft_capped: bool = False,
) -> str:
    """Honest owner-facing publish note (matched titles, not 'real titles N stations')."""
    base = ""
    if match_total > 0:
        base = (
            f"Matched {matched}/{match_total} collection titles · "
            f"lineup {program_count} program(s)."
        )
    elif program_count > 0:
        base = f"Lineup {program_count} program(s) across {stations_filled or 1} station(s)."
    honesty = ""
    if soft_capped or full_run is False:
        honesty = craft_soft_cap_honesty(
            fill_mode="soft",
            matched=matched,
            program_count=program_count,
        )["note"]
    if base and honesty:
        return f"{base} {honesty}"
    return base or honesty


def random_slot_schedule_for_programs(
    programs: Sequence[Mapping[str, Any]],
    *,
    max_flex_ms: int = 0,
    max_days: int = 7,
    programming_mode: ProgrammingMode = ProgrammingMode.SHUFFLE,
) -> Dict[str, Any]:
    """Build a Tunarr ``RandomSlotSchedule`` from a resolved program pool.

    Not used when publishing station lineups. One movie slot plus a slot per
    show shares a clock in Tunarr 1.3.9 and the next title can start before
    the previous file ends. ``programming_body_for_recipe`` publishes a manual
    lineup padded to the next quarter hour instead.
    """
    has_movie = False
    show_ids: List[str] = []
    seen_shows: set[str] = set()
    for raw in programs or ():
        if not isinstance(raw, Mapping):
            continue
        ptype = str(raw.get("type") or "").strip().lower()
        if ptype == "movie":
            has_movie = True
        sid = str(raw.get("show_id") or "").strip()
        if sid and sid not in seen_shows:
            seen_shows.add(sid)
            show_ids.append(sid)
        if len(show_ids) >= 24:
            break

    mode = normalize_programming_mode(programming_mode)
    order = "shuffle" if mode == ProgrammingMode.SHUFFLE else "next"
    slots: List[Dict[str, Any]] = []
    if has_movie:
        slots.append(
            {
                "id": str(uuid.uuid4()),
                "type": "movie",
                "order": order,
                "direction": "asc",
                "cooldownMs": 0,
                "weight": 1,
                "durationSpec": {"type": "dynamic", "programCount": 1},
            }
        )
    for sid in show_ids:
        slots.append(
            {
                "id": str(uuid.uuid4()),
                "type": "show",
                "showId": sid,
                "seasonFilter": [],
                "seasonExcludeFilter": [],
                "order": order,
                "direction": "asc",
                "cooldownMs": 0,
                "weight": 1,
                "durationSpec": {"type": "dynamic", "programCount": 1},
            }
        )
    if not slots:
        return {}
    pad_ms = max(0, int(max_flex_ms or 0))
    return {
        "type": "random",
        "flexPreference": "distribute" if pad_ms else "end",
        "maxDays": max(1, min(int(max_days or 7), 14)),
        "padMs": pad_ms,
        "padStyle": "slot",
        "randomDistribution": "uniform",
        "lockWeights": False,
        "slots": slots,
        "timeZoneOffset": 0,
    }


def apply_queue_padding(
    client: TunarrClient,
    recipe: ChannelRecipe,
    programs: Sequence[Mapping[str, Any]],
    *,
    catalog: Optional[Sequence[Mapping[str, Any]]] = None,
    media_scope: str = "",
    settings: Any = None,
    db: Any = None,
    stats: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Fill spare rotation slots from the recipe's queue-pad feed.

    ``playing`` = the titles the channel itself resolved. ``spare =
    max(0, up_to - playing)`` slots are filled from Recently added / Recently
    released, appended *after* the playing block so the rotation does not snap
    back to the start the moment the block ends. Recipes without a queue-pad
    setting are returned unchanged.
    """
    from projectionist.live_channels.queue_padding import (
        feed_candidates,
        normalize_queue_pad,
        order_padded_programs,
        queue_pad_plan,
    )

    base = [dict(p) for p in programs or () if isinstance(p, Mapping)]
    setting = normalize_queue_pad(getattr(recipe, "queue_pad", None))
    if not setting:
        return base
    plan = queue_pad_plan(setting, len(base))
    if stats is not None:
        stats["queue_pad"] = plan
    if plan["pad"] <= 0:
        return base

    if db is None:
        try:
            from projectionist.web.jobs import get_job_manager

            db = get_job_manager().db
        except Exception:  # noqa: BLE001
            db = None
    scope = normalize_media_scope(media_scope or getattr(recipe, "media_scope", None))

    from projectionist.live_channels.filters import exclusion_rating_keys

    skip_keys = set(exclusion_rating_keys(settings) or ())
    primary_ids = {str(p.get("id") or "") for p in base}
    for row in base:
        for key in row.get("plex_keys") or ():
            skip_keys.add(str(key))
    candidates = feed_candidates(
        db,
        setting["feed"],
        count=plan["pad"],
        media_scope=scope,
        exclude_rating_keys=sorted(skip_keys),
    )

    normalized_catalog: List[Dict[str, Any]] = []
    for item in catalog or ():
        if isinstance(item, Mapping):
            row = _normalize_program_row(item, media_scope=scope)
            if row is not None:
                normalized_catalog.append(row)
    by_key = _index_pool_by_plex_key(normalized_catalog)

    from projectionist.live_channels.recipes import (
        apply_youth_gate_to_items,
        recipe_is_youth_safe,
        resolve_recipe_youth_max_rating,
    )

    youth_safe = recipe_is_youth_safe(recipe)
    ceiling = (
        resolve_recipe_youth_max_rating(recipe, settings=settings) if youth_safe else ""
    )

    picked: List[Dict[str, Any]] = []
    for cand in candidates:
        if len(picked) >= plan["pad"]:
            break
        match = by_key.get(str(cand.get("rating_key") or ""))
        if match is None:
            continue
        if str(match.get("type") or "").lower() == "show":
            first: Optional[Dict[str, Any]] = None
            try:
                for ep in client.list_program_descendants(str(match.get("id") or "")):
                    if isinstance(ep, Mapping):
                        first = _normalize_program_row(ep, media_scope=scope)
                        if first is not None:
                            # Episodes inherit the show's rating for youth gates.
                            if not first.get("content_rating"):
                                first["content_rating"] = match.get("content_rating") or ""
                            break
            except Exception:  # noqa: BLE001
                first = None
            match = first
        if not match or not match.get("id") or str(match["id"]) in primary_ids:
            continue
        if youth_safe and not apply_youth_gate_to_items(
            [match], settings=settings, max_rating=ceiling
        ):
            continue
        primary_ids.add(str(match["id"]))
        picked.append(dict(match))

    mode = normalize_programming_mode(recipe.programming_mode)
    if stats is not None:
        plan = dict(plan)
        plan["added"] = len(picked)
        plan["titles"] = [p.get("title") for p in picked]
        stats["queue_pad"] = plan
    if not picked:
        return base
    return order_padded_programs(
        base, picked, shuffle_playing=mode == ProgrammingMode.SHUFFLE
    )


def programming_body_for_recipe(
    recipe: ChannelRecipe,
    *,
    programs: Optional[Sequence[Mapping[str, Any]]] = None,
    pad_lineups: bool = True,
    max_flex_ms: int = _DEFAULT_PAD_FLEX_MAX_MINUTES * 60 * 1000,
    start_time_ms: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    """Best-effort programming payload for ``POST …/programming``.

    Tunarr 1.3.x manual updates require ``lineup`` (array), not ``programs``.
    Every station — including shuffle — is a manual lineup. Shuffle still
    shuffles the resolved pool before this call; the published order is that
    sequence, then it loops. Stacked random slots (one movie slot plus a slot
    per show) let Tunarr start the next library title inside the previous
    file, and the guide draws those intervals on top of each other.

    When ``pad_lineups`` is true, flex fills from each title's end to the next
    quarter hour (:00, :15, :30, :45). The week-long guide
    (``GUIDE_HORIZON_DAYS`` / ``programmingHours`` 168) is unchanged: this does
    not truncate the lineup or restore an end-of-day.
    """
    from projectionist.live_channels.filler import pad_lineup_with_flex

    content_lineup: List[Dict[str, Any]] = []
    for raw in programs or ():
        if not isinstance(raw, Mapping):
            continue
        pid = str(raw.get("id") or raw.get("uuid") or "").strip()
        try:
            duration = int(raw.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        if not pid or duration < _MIN_PROGRAM_DURATION_MS:
            continue
        content_lineup.append({"type": "content", "id": pid, "duration": duration})

    if content_lineup:
        lineup = (
            pad_lineup_with_flex(
                content_lineup,
                max_flex_ms=max_flex_ms,
                start_time_ms=start_time_ms,
            )
            if pad_lineups
            else content_lineup
        )
        return {"type": "manual", "lineup": lineup}

    # Flex shells are duration-only — OpenAPI has no ``title`` on flex items.
    if recipe.item_hints:
        lineup = [
            {"type": "flex", "duration": 300_000}
            for _ in recipe.item_hints[:50]
        ]
        return {"type": "manual", "lineup": lineup}
    return {"type": "manual", "lineup": []}


def _recipe_search_terms(recipe: ChannelRecipe) -> List[str]:
    terms: List[str] = []
    for hint in recipe.item_hints:
        text = str(hint or "").strip()
        if text:
            terms.append(text)
    for extra in (recipe.motif, recipe.cluster_tag, recipe.name, recipe.collection_title):
        text = str(extra or "").strip()
        if text and text.lower() not in {t.lower() for t in terms}:
            terms.append(text)
    # Motif expansions from layered facet taxonomy (no inline dual SoT).
    for word in motif_search_expansions(recipe.name):
        if word.lower() not in {t.lower() for t in terms}:
            terms.append(word)
    return terms


def _normalize_program_row(
    item: Mapping[str, Any],
    *,
    media_scope: str = MediaScope.BOTH.value,
) -> Optional[Dict[str, Any]]:
    """Normalize library-program or search-hit shapes into content lineup fields."""
    prog = item.get("program") if isinstance(item.get("program"), Mapping) else item
    if not isinstance(prog, Mapping):
        return None
    pid = str(
        item.get("id")
        or prog.get("uuid")
        or prog.get("id")
        or ""
    ).strip()
    try:
        duration = int(item.get("duration") or prog.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    if not pid or duration < _MIN_PROGRAM_DURATION_MS:
        return None
    ptype = str(prog.get("type") or item.get("type") or "").strip().lower()
    if ptype and not program_type_matches_scope(ptype, media_scope):
        return None
    title = str(prog.get("title") or item.get("title") or "").strip()
    genres = prog.get("genres") or prog.get("tags") or []
    if not isinstance(genres, list):
        genres = []
    plex_keys = _extract_plex_rating_keys(item)
    year = prog.get("year") or item.get("year") or prog.get("releaseYear")
    try:
        year_i = int(year) if year is not None and str(year).strip() else None
    except (TypeError, ValueError):
        year_i = None
    content_rating = str(
        prog.get("contentRating")
        or prog.get("content_rating")
        or item.get("contentRating")
        or item.get("content_rating")
        or ""
    ).strip()
    show_id = str(
        prog.get("showId")
        or item.get("showId")
        or prog.get("grandparentId")
        or item.get("grandparentId")
        or ""
    ).strip()
    show_obj = prog.get("show") if isinstance(prog.get("show"), Mapping) else None
    if show_obj is None and isinstance(item.get("show"), Mapping):
        show_obj = item.get("show")
    show_title = ""
    if isinstance(show_obj, Mapping):
        show_title = str(show_obj.get("title") or show_obj.get("name") or "").strip()
        if not show_id:
            show_id = str(show_obj.get("uuid") or show_obj.get("id") or "").strip()
        # Episodes often omit contentRating — inherit the show's rating for youth gates.
        if not content_rating:
            content_rating = str(
                show_obj.get("contentRating")
                or show_obj.get("content_rating")
                or ""
            ).strip()
        # Index show-level Plex keys so collection children that are *shows* match.
        plex_keys = list(plex_keys) + [
            k
            for k in _extract_plex_rating_keys(show_obj)
            if k and k not in plex_keys
        ]
    if not show_title:
        show_title = str(
            prog.get("grandparentTitle")
            or item.get("grandparentTitle")
            or prog.get("showTitle")
            or item.get("showTitle")
            or ""
        ).strip()
    return {
        "id": pid,
        "duration": duration,
        "title": title,
        "type": ptype,
        "genres": [str(g) for g in genres if str(g).strip()],
        "plex_keys": plex_keys,
        "year": year_i,
        "content_rating": content_rating,
        "show_id": show_id,
        "show_title": show_title,
    }


def _index_pool_by_plex_key(pool: Sequence[Mapping[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Map Plex ratingKey / externalKey forms → normalized program rows."""
    by_key: Dict[str, Dict[str, Any]] = {}
    for item in pool:
        if not isinstance(item, Mapping):
            continue
        for key in item.get("plex_keys") or ():
            text = str(key or "").strip()
            if text and text not in by_key:
                by_key[text] = dict(item)
    return by_key


def _fill_target_for_recipe(
    recipe: ChannelRecipe,
    *,
    limit: Optional[int] = None,
    full_run: bool = False,
) -> int:
    """Resolve fill target: soft default for motif/taste; full-run for collection/show.

    ``limit=None`` means “use the path default” (full-run cap vs soft default).
    An explicit positive ``limit`` is still clamped to the path’s safety cap.
    """
    del recipe  # reserved for future per-source tuning
    if full_run:
        if limit is None or int(limit) <= 0:
            return _FULL_RUN_FILL_CAP
        return max(1, min(int(limit), _FULL_RUN_FILL_CAP))
    if limit is None or int(limit) <= 0:
        return _DEFAULT_FILL_LIMIT
    return max(1, min(int(limit), _SOFT_FILL_CAP))


def collect_programs_for_recipe(
    client: TunarrClient,
    recipe: ChannelRecipe,
    *,
    limit: Optional[int] = None,
    catalog: Optional[Sequence[Mapping[str, Any]]] = None,
    media_scope: str = "",
    settings: Any = None,
    match_stats: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Pick Tunarr program IDs for a recipe from an indexed catalog / search.

    Collection recipes prefer Plex ``ratingKey`` → Tunarr ``externalKey`` /
    ``plex|{source}|{key}``. Title soft-match is last-resort for unscanned items.
    When ID matches succeed, do **not** pad with random whole-library titles.

    Collection / show stations use a full-run fill (all resolved programs up to
    ``_FULL_RUN_FILL_CAP``). Motif / taste / filtered craft keep a softer default.
    """
    scope = normalize_media_scope(media_scope or getattr(recipe, "media_scope", None))
    rating_keys_early = [
        str(k).strip() for k in (recipe.item_rating_keys or ()) if str(k).strip()
    ]
    is_collection = recipe.source == "collection" or bool(
        recipe.collection_id or rating_keys_early or recipe.item_hints
    )
    # Full-run for collection/show ID pools; soft cap for motif/taste/legacy chaos.
    full_run = is_collection and recipe.source != "chaos"
    target = _fill_target_for_recipe(recipe, limit=limit, full_run=full_run)
    pool: List[Dict[str, Any]] = []
    seen: set[str] = set()

    # Youth gate must be available inside ``_add`` so show-expand / Tunarr search
    # cannot re-introduce TV-MA after the pool was filtered.
    from projectionist.live_channels.recipes import (
        apply_youth_gate_to_items,
        recipe_is_youth_safe,
        resolve_recipe_youth_max_rating,
    )

    youth_safe = recipe_is_youth_safe(recipe)
    youth_ceiling = (
        resolve_recipe_youth_max_rating(recipe, settings=settings) if youth_safe else ""
    )

    def _youth_allows(normalized: Mapping[str, Any]) -> bool:
        if not youth_safe:
            return True
        return bool(
            apply_youth_gate_to_items(
                [normalized], settings=settings, max_rating=youth_ceiling
            )
        )

    def _add(row: Optional[Mapping[str, Any]]) -> None:
        if not row:
            return
        normalized = (
            _normalize_program_row(row, media_scope=scope)
            if "duration" in row or "program" in row
            else None
        )
        if normalized is None and row.get("id") and row.get("duration"):
            try:
                duration = int(row["duration"])
            except (TypeError, ValueError):
                return
            if duration < _MIN_PROGRAM_DURATION_MS:
                return
            ptype = str(row.get("type") or "").strip().lower()
            if ptype and not program_type_matches_scope(ptype, scope):
                return
            plex_keys = list(row.get("plex_keys") or _extract_plex_rating_keys(row))
            content_rating = str(
                row.get("content_rating") or row.get("contentRating") or ""
            ).strip()
            show_obj = row.get("show") if isinstance(row.get("show"), Mapping) else None
            if not content_rating and isinstance(show_obj, Mapping):
                content_rating = str(
                    show_obj.get("contentRating")
                    or show_obj.get("content_rating")
                    or ""
                ).strip()
            normalized = {
                "id": str(row["id"]),
                "duration": duration,
                "title": str(row.get("title") or ""),
                "type": ptype,
                "genres": list(row.get("genres") or []),
                "plex_keys": plex_keys,
                "content_rating": content_rating,
                "year": row.get("year"),
                "show_id": str(row.get("show_id") or row.get("showId") or "").strip(),
                "show_title": str(row.get("show_title") or row.get("showTitle") or "").strip(),
            }
        if not normalized or normalized["id"] in seen:
            return
        if not _youth_allows(normalized):
            return
        seen.add(normalized["id"])
        pool.append(normalized)

    for item in catalog or ():
        if isinstance(item, Mapping):
            _add(item)

    if not pool:
        # Pull from enabled libraries matching media scope when no shared catalog.
        try:
            media_types = (
                ("shows",)
                if scope == MediaScope.TV.value
                else ("movies",)
                if scope == MediaScope.MOVIES.value
                else ("movies", "shows")
            )
            libraries_state = ensure_media_libraries_enabled(
                client, media_types=media_types, scan=False, settings=settings
            )
            for lib in libraries_state.get("enabled") or []:
                if not library_type_matches_scope(lib.get("media_type"), scope):
                    continue
                lid = str(lib.get("id") or "")
                if not lid:
                    continue
                for item in client.list_library_programs(lid):
                    _add(item)
        except Exception:  # noqa: BLE001
            pass

    terms = _recipe_search_terms(recipe)
    mode = normalize_programming_mode(recipe.programming_mode)
    rating_keys = list(rating_keys_early)

    def _record_stats(matched: int, total: int, programs: Sequence[Mapping[str, Any]]) -> None:
        if match_stats is None:
            return
        match_stats["matched"] = int(matched)
        match_stats["match_total"] = int(total)
        match_stats["program_count"] = len(programs)
        match_stats["full_run"] = bool(full_run)
        match_stats["fill_target"] = int(target)

    # Additive craft filters + exclusion collection (NoLive).
    from projectionist.live_channels.filters import (
        apply_craft_filters_to_pool,
        exclusion_rating_keys,
        library_items_matching_filters,
        normalize_craft_filters,
    )

    craft = normalize_craft_filters(getattr(recipe, "craft_filters", None))
    excluded = exclusion_rating_keys(settings)
    allowed_keys: Optional[set[str]] = None

    def _apply_youth_gate(
        items: Sequence[Mapping[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Fail-closed rating filter for youth-safe / source=youth stations."""
        if not youth_safe:
            return [dict(i) for i in items if isinstance(i, Mapping)]
        return apply_youth_gate_to_items(
            items, settings=settings, max_rating=youth_ceiling
        )

    if not craft.is_empty():
        db = None
        try:
            from projectionist.web.jobs import get_job_manager

            db = get_job_manager().db
        except Exception:  # noqa: BLE001
            db = None
        if db is not None:
            lib = library_items_matching_filters(
                db, craft, media_scope=scope, limit=_FULL_RUN_FILL_CAP
            )
            # Empty set means “no library titles match” — do NOT coerce to None
            # (None falls back to Tunarr-side filters against the full pool).
            allowed_keys = {str(k) for k in (lib.get("rating_keys") or []) if str(k)}
        # When library index is unavailable (allowed_keys is None), keep Tunarr-side
        # genre/year filter. An empty allowed set stays empty.
        pool = apply_craft_filters_to_pool(
            pool,
            craft,
            allowed_rating_keys=allowed_keys,
            excluded_rating_keys=excluded,
        )
        if match_stats is not None:
            match_stats["filter_matched"] = len(pool)
            match_stats["filters"] = craft.to_dict()
    elif excluded:
        pool = apply_craft_filters_to_pool(
            pool,
            craft,
            excluded_rating_keys=excluded,
        )

    # Defense in depth: ``_add`` already gates, but craft/exclusion may have
    # reshaped the pool — re-assert the youth ceiling before soft-pad / shuffle.
    if youth_safe:
        pool = _apply_youth_gate(pool)
        if match_stats is not None:
            match_stats["youth_safe"] = True
            match_stats["youth_max_rating"] = youth_ceiling
            match_stats["youth_matched"] = len(pool)

    # Soft-cap motif/taste Shuffle may use more of the filtered pool (still ≤ soft cap).
    if not full_run and mode == ProgrammingMode.SHUFFLE and pool:
        target = max(target, min(_SOFT_FILL_CAP, max(_DEFAULT_FILL_LIMIT, len(pool))))

    # Collection subfilter: intersect ratingKeys with craft filters + exclusion.
    if rating_keys:
        filtered_keys = [
            k for k in rating_keys if k not in excluded and (allowed_keys is None or k in allowed_keys)
        ]
        if allowed_keys is not None or excluded:
            rating_keys = filtered_keys

    # Legacy Chaos stations: Shuffle the media_scope pool (soft cap).
    if recipe.source == "chaos":
        candidates = list(pool)
        random.shuffle(candidates)
        soft = _fill_target_for_recipe(recipe, limit=limit, full_run=False)
        picked = candidates[:soft]
        _record_stats(len(picked), len(pool) if not craft.is_empty() else 0, picked)
        return picked

    def _expand_show_descendants(show_uuid: str) -> List[Dict[str, Any]]:
        """Resolve Tunarr show → episode content rows (collection child was a show)."""
        sid = str(show_uuid or "").strip()
        if not sid:
            return []
        # Show expand is always a full-run path (entire episode pool).
        expand_cap = _fill_target_for_recipe(recipe, limit=limit, full_run=True)
        out: List[Dict[str, Any]] = []
        try:
            descendants = client.list_program_descendants(sid)
        except Exception:  # noqa: BLE001
            return []
        for row in descendants:
            if not isinstance(row, Mapping):
                continue
            _add(row)
            normalized = _normalize_program_row(row, media_scope=scope)
            if normalized is None and row.get("id") and row.get("duration"):
                try:
                    duration = int(row["duration"])
                except (TypeError, ValueError):
                    continue
                if duration < _MIN_PROGRAM_DURATION_MS:
                    continue
                prog = (
                    row.get("program") if isinstance(row.get("program"), Mapping) else {}
                )
                content_rating = str(
                    (prog or {}).get("contentRating")
                    or (prog or {}).get("content_rating")
                    or row.get("contentRating")
                    or row.get("content_rating")
                    or ""
                ).strip()
                normalized = {
                    "id": str(row.get("id") or prog.get("uuid") or ""),
                    "duration": duration,
                    "title": str((prog or {}).get("title") or row.get("title") or ""),
                    "type": str((prog or {}).get("type") or row.get("type") or ""),
                    "genres": [],
                    "plex_keys": _extract_plex_rating_keys(row),
                    "content_rating": content_rating,
                    "show_id": sid,
                    "show_title": "",
                }
            if normalized and normalized["id"] and _youth_allows(normalized):
                out.append(normalized)
            if len(out) >= expand_cap:
                break
        return out

    def _resolve_show_uuid_for_key_or_title(*, key: str = "", title: str = "") -> str:
        """Find a Tunarr show uuid from a Plex ratingKey or show title."""
        wanted_key = str(key or "").strip()
        wanted_title = str(title or "").strip().casefold()
        # Episodes already in the pool may carry show_id + show plex keys.
        for item in pool:
            if wanted_key and wanted_key in (item.get("plex_keys") or ()):
                sid = str(item.get("show_id") or "").strip()
                if sid:
                    return sid
            if wanted_title and str(item.get("show_title") or "").casefold() == wanted_title:
                sid = str(item.get("show_id") or "").strip()
                if sid:
                    return sid
        query = title or key
        if not query:
            return ""
        try:
            payload = client.search_programs(str(query), limit=20)
        except Exception:  # noqa: BLE001
            return ""
        for hit in payload.get("results") or []:
            if not isinstance(hit, Mapping):
                continue
            hit_type = str(hit.get("type") or "").strip().lower()
            hit_title = str(hit.get("title") or "").strip()
            hit_keys = _extract_plex_rating_keys(hit)
            if hit_type == "show":
                if wanted_key and wanted_key in hit_keys:
                    return str(hit.get("uuid") or hit.get("id") or "").strip()
                if wanted_title and hit_title.casefold() == wanted_title:
                    return str(hit.get("uuid") or hit.get("id") or "").strip()
            show = hit.get("show") if isinstance(hit.get("show"), Mapping) else None
            if show is not None:
                show_keys = _extract_plex_rating_keys(show)
                show_title = str(show.get("title") or "").strip()
                if wanted_key and wanted_key in show_keys:
                    return str(show.get("uuid") or show.get("id") or "").strip()
                if wanted_title and show_title.casefold() == wanted_title:
                    return str(show.get("uuid") or show.get("id") or "").strip()
        return ""

    # ID-first collection / keyed pool.
    if rating_keys:
        by_key = _index_pool_by_plex_key(pool)
        ordered: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        matched = 0
        unresolved_keys: List[str] = []
        for key in rating_keys:
            match = by_key.get(key)
            if match is None:
                unresolved_keys.append(key)
                continue
            # Show-level catalog rows: expand to episodes instead of scheduling the show shell.
            if str(match.get("type") or "").lower() == "show":
                expanded = _expand_show_descendants(str(match.get("id") or ""))
                if expanded:
                    matched += 1
                    for ep in expanded:
                        if ep["id"] in seen_ids:
                            continue
                        seen_ids.add(ep["id"])
                        ordered.append(ep)
                        if len(ordered) >= target:
                            break
                    if len(ordered) >= target:
                        break
                    continue
            if match["id"] in seen_ids:
                continue
            seen_ids.add(match["id"])
            ordered.append(match)
            matched += 1
            if len(ordered) >= target:
                break

        # Show ratingKeys often miss episode pools — expand via Tunarr descendants.
        if len(ordered) < target and unresolved_keys:
            for key in unresolved_keys:
                if len(ordered) >= target:
                    break
                hint = ""
                if recipe.item_hints:
                    # Pair by index when lengths align; else try any unused hint later.
                    try:
                        idx = rating_keys.index(key)
                        hint = str(recipe.item_hints[idx]) if idx < len(recipe.item_hints) else ""
                    except ValueError:
                        hint = ""
                show_uuid = _resolve_show_uuid_for_key_or_title(key=key, title=hint)
                if not show_uuid:
                    continue
                expanded = _expand_show_descendants(show_uuid)
                if not expanded:
                    continue
                matched += 1
                for ep in expanded:
                    if ep["id"] in seen_ids:
                        continue
                    seen_ids.add(ep["id"])
                    ordered.append(ep)
                    if len(ordered) >= target:
                        break

        # Last-resort title / show-title match for unresolved keys (unscanned items).
        if len(ordered) < len(rating_keys) and recipe.item_hints and len(ordered) < target:
            by_title = {
                str(item.get("title") or "").strip().casefold(): item
                for item in pool
                if str(item.get("title") or "").strip()
            }
            by_show = {}
            for item in pool:
                st = str(item.get("show_title") or "").strip().casefold()
                if st and st not in by_show:
                    by_show[st] = item
            for hint in recipe.item_hints:
                if len(ordered) >= target:
                    break
                wanted = str(hint or "").strip()
                if not wanted:
                    continue
                match = by_title.get(wanted.casefold())
                if match is None and wanted.casefold() in by_show:
                    # Expand the show rather than scheduling one random episode.
                    show_uuid = str(by_show[wanted.casefold()].get("show_id") or "")
                    expanded = _expand_show_descendants(show_uuid) if show_uuid else []
                    if expanded:
                        matched += 1
                        for ep in expanded:
                            if ep["id"] in seen_ids:
                                continue
                            seen_ids.add(ep["id"])
                            ordered.append(ep)
                            if len(ordered) >= target:
                                break
                        continue
                if match is None:
                    continue
                if match["id"] in seen_ids:
                    continue
                seen_ids.add(match["id"])
                ordered.append(match)
                matched += 1

        if mode == ProgrammingMode.SHUFFLE and ordered:
            random.shuffle(ordered)
        # Sequential = collection order (already). No whole-library pad when IDs resolve.
        if ordered:
            picked = ordered[:target]
            _record_stats(matched, len(rating_keys), picked)
            return picked
        _record_stats(0, len(rating_keys), [])
        # Fall through only when zero ID matches — keyword/search path below.

    # Title-hint ordered path (Projectionist lists without Plex ratingKeys).
    if is_collection and recipe.item_hints and not rating_keys:
        by_title = {
            str(item.get("title") or "").strip().casefold(): item
            for item in pool
            if str(item.get("title") or "").strip()
        }
        ordered = []
        seen_ids = set()
        matched = 0
        for hint in recipe.item_hints:
            wanted = str(hint or "").strip()
            if not wanted:
                continue
            match = by_title.get(wanted.casefold())
            if match is None:
                show_uuid = _resolve_show_uuid_for_key_or_title(title=wanted)
                if show_uuid:
                    expanded = _expand_show_descendants(show_uuid)
                    if expanded:
                        matched += 1
                        for ep in expanded:
                            if ep["id"] in seen_ids:
                                continue
                            seen_ids.add(ep["id"])
                            ordered.append(ep)
                            if len(ordered) >= target:
                                break
                        if len(ordered) >= target:
                            break
                        continue
                try:
                    payload = client.search_programs(wanted, limit=8)
                except Exception:  # noqa: BLE001
                    payload = {}
                for hit in payload.get("results") or []:
                    if not isinstance(hit, Mapping):
                        continue
                    pid = str(hit.get("uuid") or hit.get("id") or "")
                    catalog_hit = next((p for p in pool if p["id"] == pid), None)
                    if catalog_hit:
                        match = catalog_hit
                        break
            if match and match["id"] not in seen_ids:
                seen_ids.add(match["id"])
                ordered.append(match)
                matched += 1
            if len(ordered) >= target:
                break
        if ordered:
            if mode == ProgrammingMode.SHUFFLE:
                random.shuffle(ordered)
            picked = ordered[:target]
            _record_stats(matched, len(recipe.item_hints), picked)
            return picked

    # Named station / show-title path: expand “Gilligan's Island” → episodes before
    # keyword scoring (episode titles rarely contain the show name).
    # Skip when craft filters are active — show expand ignores decade/genre bounds.
    # Skip youth-safe / source=youth — station name “Youth Safe” must never resolve
    # to a show, and youth fill is a rating-gated shuffle of the media_scope pool.
    show_terms = [
        t
        for t in (recipe.collection_title, recipe.name, *recipe.item_hints)
        if str(t or "").strip()
    ]
    if (
        show_terms
        and recipe.source not in {"chaos", "youth"}
        and not youth_safe
        and craft.is_empty()
    ):
        # Show expand always uses the full-run cap (not the motif soft default).
        show_cap = _fill_target_for_recipe(recipe, limit=limit, full_run=True)
        for term in show_terms:
            show_uuid = _resolve_show_uuid_for_key_or_title(title=str(term))
            if not show_uuid:
                continue
            expanded = _expand_show_descendants(show_uuid)
            if not expanded:
                continue
            if mode == ProgrammingMode.SHUFFLE:
                random.shuffle(expanded)
            picked = expanded[:show_cap]
            _record_stats(len(picked), 1, picked)
            return picked

    scored: List[Tuple[int, Dict[str, Any]]] = []
    term_l = [t.lower() for t in terms]
    for item in pool:
        blob = " ".join(
            [
                item.get("title") or "",
                item.get("show_title") or "",
                " ".join(item.get("genres") or []),
            ]
        ).lower()
        score = sum(1 for t in term_l if t and t in blob)
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], pair[1].get("title") or ""))
    picked = [item for _, item in scored[:target]]

    # Supplement via Tunarr search when catalog keyword match is thin.
    if len(picked) < max(8, target // 2):
        for term in terms:
            try:
                payload = client.search_programs(term, limit=40)
            except Exception:  # noqa: BLE001
                continue
            for hit in payload.get("results") or []:
                if not isinstance(hit, Mapping):
                    continue
                # Search hits often omit duration — reuse catalog duration when known.
                dur = 0
                try:
                    dur = int(hit.get("duration") or 0)
                except (TypeError, ValueError):
                    dur = 0
                pid = str(hit.get("uuid") or hit.get("id") or "")
                if not dur and pid:
                    match = next((p for p in pool if p["id"] == pid), None)
                    if match:
                        _add(match)
                        continue
                if dur >= _MIN_PROGRAM_DURATION_MS and pid:
                    _add(
                        {
                            "id": pid,
                            "duration": dur,
                            "title": hit.get("title") or "",
                            "genres": hit.get("genres") or hit.get("tags") or [],
                            "plex_keys": _extract_plex_rating_keys(hit),
                            "show": hit.get("show"),
                            "type": hit.get("type"),
                        }
                    )
            # Tunarr search hits omit year/genre reliability — re-apply craft filters
            # so decade/genre stations never absorb modern catalog noise.
            if not craft.is_empty():
                pool[:] = apply_craft_filters_to_pool(
                    pool,
                    craft,
                    allowed_rating_keys=allowed_keys,
                    excluded_rating_keys=excluded,
                )
            # ``_add`` gates youth at ingest; re-assert after craft reshapes the pool.
            if youth_safe:
                pool[:] = _apply_youth_gate(pool)
            # Rebuild picks after search supplements.
            scored = []
            for item in pool:
                blob = " ".join(
                    [
                        item.get("title") or "",
                        item.get("show_title") or "",
                        " ".join(item.get("genres") or []),
                    ]
                ).lower()
                score = sum(1 for t in term_l if t and t in blob)
                if score:
                    scored.append((score, item))
            scored.sort(key=lambda pair: (-pair[0], pair[1].get("title") or ""))
            picked = [item for _, item in scored[:target]]
            if len(picked) >= target:
                break

    if len(picked) < 8 and pool and not rating_keys and not is_collection:
        # Non-collection fallback only — never pad collection/show stations with
        # off-collection random titles (Gilligan ← Samurai Jack class of bug).
        # Pool is already craft-filtered when decade/genre filters are set.
        extras = [p for p in pool if p["id"] not in {x["id"] for x in picked}]
        random.shuffle(extras)
        picked.extend(extras[: max(0, target - len(picked))])
    if mode == ProgrammingMode.SHUFFLE and picked:
        random.shuffle(picked)
    _record_stats(len(picked), 0, picked)
    return picked[:target]
