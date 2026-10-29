"""Publish starter recipes and collections into Projectionist's lineup store."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from projectionist.live_channels.publish_icons import (
    _DEFAULT_GROUP_TITLE,
    _DEFAULT_GUIDE_MINIMUM_DURATION_MS,
    _DEFAULT_STREAM_MODE,
    _channel_put_body,
    apply_channel_name,
    apply_station_icons,
    channel_icon_body,
    channel_icon_hides_plex_label,
    ensure_channel_labels,
    is_default_tunarr_icon,
    probe_icon_url,
    resolve_channel_icon_url,
    resolve_collection_icon_url,
    unique_station_name,
)
from projectionist.live_channels.publish_playback import (
    align_channel_playhead_to_program_start,
    prepare_channels_for_playback,
    should_align_playhead,
    snap_future_channel_start_time,
    warm_channel_stream,
)
from projectionist.live_channels.publish_programming import (
    _DEFAULT_FILL_LIMIT,
    _FULL_RUN_FILL_CAP,
    _SOFT_FILL_CAP,
    _extract_plex_rating_keys,
    apply_queue_padding,
    collect_programs_for_recipe,
    craft_fill_mode,
    craft_soft_cap_honesty,
    full_run_fill_cap,
    match_feedback_note,
    pad_flex_max_ms,
    plex_collection_children,
    plex_collection_item_hints,
    plex_collection_rating_keys,
    programming_body_for_recipe,
    random_slot_schedule_for_programs,
    soft_fill_cap,
    soft_fill_default,
)
from projectionist.live_channels.recipes import (
    ChannelRecipe,
    MediaScope,
    ProgrammingMode,
    library_type_matches_scope,
    normalize_media_scope,
    normalize_programming_mode,
    program_type_matches_scope,
    recipe_from_mapping,
    replace_recipe,
)

# Historical annotations used this name for the broadcast HTTP client.
TunarrClient = Any

# Prefer these Plex library mediaTypes when enabling Tunarr libraries for fill.
_PREFERRED_LIBRARY_TYPES = frozenset({"movies", "shows"})


def plex_media_source_body(
    *,
    plex_url: str,
    plex_token: str,
    name: str = "Plex",
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    path_replacements: Optional[Sequence[Mapping[str, str]]] = None,
) -> Dict[str, Any]:
    """Build Tunarr ``POST /api/media-sources`` body for ``type=plex``.

    Tunarr 1.3.x OpenAPI requires ``userId``, ``username``, and
    ``pathReplacements`` keys (null / empty string / ``[]`` are valid for Plex
    token auth). Do not put the Plex token in ``userId``.
    """
    return {
        "name": str(name or "Plex").strip() or "Plex",
        "type": "plex",
        "uri": str(plex_url or "").strip().rstrip("/"),
        "accessToken": str(plex_token or "").strip(),
        "userId": user_id,
        "username": username,
        "pathReplacements": [dict(item) for item in (path_replacements or [])],
    }


def _plex_identity_hints(
    plex_url: str, plex_token: str
) -> tuple[Optional[str], Optional[str]]:
    """Best-effort (userId, username) from Plex server identity for Tunarr wire."""
    try:
        from projectionist.connectors.plex import PlexClient

        machine_id, friendly = PlexClient(
            plex_url, plex_token, timeout=5
        ).server_identity()
    except Exception:  # noqa: BLE001
        return None, None
    user_id = str(machine_id or "").strip() or None
    username = str(friendly or "").strip() or None
    return user_id, username


def configured_plex_external_keys(
    settings: Any = None,
    *,
    media_types: Sequence[str] = ("movies", "shows"),
    movie_section: str = "",
    tv_section: str = "",
) -> set[str]:
    """Plex section keys Projectionist is allowed to expose into Tunarr.

    Tunarr libraries carry Plex section ids on ``externalKey``. Only those
    matching ``plex_movie_section`` / ``plex_tv_section`` (filtered by the
    requested media types) should be enabled or scanned.
    """
    movie = str(movie_section or "").strip()
    tv = str(tv_section or "").strip()
    if settings is not None:
        if not movie:
            movie = str(getattr(settings, "plex_movie_section", "") or "").strip()
        if not tv:
            tv = str(getattr(settings, "plex_tv_section", "") or "").strip()
    wanted = {str(t).lower() for t in media_types} or set(_PREFERRED_LIBRARY_TYPES)
    keys: set[str] = set()
    if "movies" in wanted and movie:
        keys.add(movie)
    if "shows" in wanted and tv:
        keys.add(tv)
    return keys


def _tunarr_library_external_key(lib: Mapping[str, Any]) -> str:
    return str(
        lib.get("externalKey")
        or lib.get("external_key")
        or lib.get("key")
        or ""
    ).strip()


def wire_plex_media_source(
    client: TunarrClient,
    *,
    plex_url: str,
    plex_token: str,
    name: str = "Plex",
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    settings: Any = None,
) -> Dict[str, Any]:
    """Ensure a Plex media source exists in Tunarr (idempotent best-effort).

    Only enables libraries that match Projectionist's configured Plex
    sections (``plex_movie_section`` / ``plex_tv_section``).
    """
    url = str(plex_url or "").strip().rstrip("/")
    token = str(plex_token or "").strip()
    if not url or not token:
        return {
            "ok": False,
            "created": False,
            "message": "Plex URL and token are required to wire a media source.",
        }
    # When library binds exist, prefer Tunarr direct file reads over Plex HTTP.
    stream_path = client.ensure_plex_stream_path_direct()
    existing = client.list_media_sources()
    for source in existing:
        stype = str(source.get("type") or source.get("sourceType") or "").lower()
        uri = str(source.get("uri") or source.get("url") or "").rstrip("/")
        if stype == "plex" and (not uri or uri == url):
            msid = str(source.get("id") or source.get("uuid") or "")
            libraries = (
                ensure_media_libraries_enabled(
                    client, media_source_id=msid, settings=settings
                )
                if msid
                else {"ok": False, "enabled": [], "scanned": []}
            )
            return {
                "ok": True,
                "created": False,
                "id": msid or source.get("id") or source.get("uuid"),
                "message": "Plex media source already present in Tunarr.",
                "source": dict(source),
                "libraries": libraries,
                "plex_stream": stream_path,
            }
    resolved_user_id = user_id
    resolved_username = username
    if resolved_user_id is None and resolved_username is None:
        resolved_user_id, resolved_username = _plex_identity_hints(url, token)
    body = plex_media_source_body(
        plex_url=url,
        plex_token=token,
        name=name,
        user_id=resolved_user_id,
        username=resolved_username,
    )
    created = client.create_media_source(body)
    msid = str(created.get("id") or created.get("uuid") or "")
    libraries = (
        ensure_media_libraries_enabled(
            client, media_source_id=msid, settings=settings
        )
        if msid
        else {"ok": False, "enabled": [], "scanned": []}
    )
    return {
        "ok": True,
        "created": True,
        "id": msid,
        "message": "Wired Plex as a Tunarr media source.",
        "source": dict(created),
        "request_body_keys": sorted(body.keys()),
        "libraries": libraries,
        "plex_stream": stream_path,
    }


def ensure_media_libraries_enabled(
    client: TunarrClient,
    *,
    media_source_id: str = "",
    media_types: Sequence[str] = ("movies", "shows"),
    scan: bool = True,
    force_scan: bool = False,
    settings: Any = None,
    movie_section: str = "",
    tv_section: str = "",
) -> Dict[str, Any]:
    """Enable configured Plex libraries in Tunarr and kick scans.

    Tunarr wires a Plex source with libraries ``enabled: false`` by default —
    channels then stay empty (flex-only guide, playback ends immediately).

    Only libraries whose Tunarr ``externalKey`` matches Projectionist's
    ``plex_movie_section`` / ``plex_tv_section`` are enabled. Other discovered
    Plex libraries (e.g. side collections) stay disabled — never deleted.

    When ``scan`` is true, only force-scan libraries that were just enabled
    (or when ``force_scan`` is set). Re-publishing must not stampede Tunarr
    with concurrent ``forceScan`` and trip library locks.

    Channel media scope (``tv`` / ``movies`` / ``both``) further narrows via
    ``media_types`` within that configured set.
    """
    msid = str(media_source_id or "").strip()
    if not msid:
        sources = client.list_media_sources()
        for source in sources:
            stype = str(source.get("type") or source.get("sourceType") or "").lower()
            if stype == "plex":
                msid = str(source.get("id") or source.get("uuid") or "").strip()
                if msid:
                    break
    if not msid:
        return {
            "ok": False,
            "enabled": [],
            "scanned": [],
            "skipped": [],
            "message": "Channel fill uses titles already in the lineup.",
        }

    wanted = {str(t).lower() for t in media_types} or set(_PREFERRED_LIBRARY_TYPES)
    allowed_keys = configured_plex_external_keys(
        settings,
        media_types=tuple(wanted),
        movie_section=movie_section,
        tv_section=tv_section,
    )
    if not allowed_keys:
        return {
            "ok": False,
            "media_source_id": msid,
            "enabled": [],
            "scanned": [],
            "skipped": [],
            "allowed_external_keys": [],
            "message": (
                "Configure Plex library mapping (movie / TV section) in "
                "Projectionist before enabling Tunarr libraries."
            ),
        }

    enabled: List[Dict[str, Any]] = []
    scanned: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    errors: List[str] = []
    try:
        libraries = client.list_media_source_libraries(msid)
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "media_source_id": msid,
            "enabled": [],
            "scanned": [],
            "skipped": [],
            "message": f"Could not list Tunarr libraries: {error}"[:240],
        }

    for lib in libraries:
        media_type = str(lib.get("mediaType") or lib.get("type") or "").lower()
        lid = str(lib.get("id") or "").strip()
        name = str(lib.get("name") or lid or "library")
        external_key = _tunarr_library_external_key(lib)
        if media_type not in wanted or not lid:
            continue
        if external_key not in allowed_keys:
            skipped.append(
                {
                    "id": lid,
                    "name": name,
                    "media_type": media_type,
                    "external_key": external_key,
                    "reason": "not_in_projectionist_plex_sections",
                }
            )
            # Leave out-of-scope libraries disabled (do not delete). If a prior
            # wire already enabled them, turn them back off.
            if bool(lib.get("enabled")):
                try:
                    client.set_library_enabled(msid, lid, enabled=False)
                except Exception as error:  # noqa: BLE001
                    errors.append(f"{name} (disable): {error}"[:160])
            continue
        try:
            just_enabled = False
            if not bool(lib.get("enabled")):
                client.set_library_enabled(msid, lid, enabled=True)
                just_enabled = True
            enabled.append(
                {
                    "id": lid,
                    "name": name,
                    "media_type": media_type,
                    "external_key": external_key,
                }
            )
            if scan and (just_enabled or force_scan):
                client.scan_library(msid, lid, force=True)
                scanned.append({"id": lid, "name": name})
        except Exception as error:  # noqa: BLE001
            errors.append(f"{name}: {error}"[:160])

    return {
        "ok": bool(enabled) and not errors,
        "media_source_id": msid,
        "enabled": enabled,
        "scanned": scanned,
        "skipped": skipped,
        "allowed_external_keys": sorted(allowed_keys),
        "errors": errors,
        "message": (
            f"Enabled {len(enabled)} configured library(ies)"
            + (f"; skipped {len(skipped)} outside Projectionist mapping" if skipped else "")
            + (f"; scanning {len(scanned)}" if scanned else "")
            + ("." if not errors else f" ({len(errors)} error(s)).")
        ),
    }


def resolve_media_scope(
    settings: Any = None,
    *,
    channel_id: str = "",
    recipe: Optional[ChannelRecipe] = None,
    default: str = MediaScope.BOTH.value,
) -> str:
    """Resolve media scope from recipe, then station_meta, then default."""
    if recipe is not None:
        scope = normalize_media_scope(getattr(recipe, "media_scope", None), default="")
        if scope:
            return scope
    row = station_meta_row(settings, channel_id)
    if row:
        scope = normalize_media_scope(row.get("media_scope"), default="")
        if scope:
            return scope
    return normalize_media_scope(default)


def station_meta_row(settings: Any, channel_id: str) -> Dict[str, Any]:
    """Return a copy of ``tunarr.station_meta[channel_id]`` or ``{}``."""
    cid = str(channel_id or "").strip()
    if not cid or settings is None:
        return {}
    tunarr = getattr(settings, "tunarr", None)
    meta = getattr(tunarr, "station_meta", None) if tunarr is not None else None
    if not isinstance(meta, Mapping):
        return {}
    row = meta.get(cid)
    return dict(row) if isinstance(row, Mapping) else {}


def set_station_meta(
    settings: Any,
    channel_id: str,
    *,
    media_scope: str = "",
    collection_id: str = "",
    programming_mode: str = "",
    collection_title: str = "",
    icon_url: str = "",
    source: str = "",
    craft_filters: Optional[Mapping[str, Any]] = None,
    motif: Optional[str] = None,
    cluster_tag: Optional[str] = None,
    subtitles_enabled: Optional[bool] = None,
    youth_safe: Optional[bool] = None,
    item_rating_keys: Optional[Sequence[str]] = None,
    item_hints: Optional[Sequence[str]] = None,
    queue_pad: Optional[Mapping[str, Any]] = None,
) -> None:
    """Persist station recipe fields on ``settings.tunarr.station_meta`` (in-memory).

    ``motif`` / ``cluster_tag`` / ``craft_filters`` / ``item_rating_keys`` /
    ``item_hints``: ``None`` leaves the stored value unchanged; a provided value
    (including empty) replaces it.
    """
    cid = str(channel_id or "").strip()
    if not cid or settings is None:
        return
    tunarr = getattr(settings, "tunarr", None)
    if tunarr is None:
        return
    meta = getattr(tunarr, "station_meta", None)
    if not isinstance(meta, dict):
        meta = {}
        try:
            setattr(tunarr, "station_meta", meta)
        except Exception:  # noqa: BLE001
            return
    row = dict(meta.get(cid) or {}) if isinstance(meta.get(cid), Mapping) else {}
    if media_scope:
        row["media_scope"] = normalize_media_scope(media_scope)
    if collection_id:
        row["collection_id"] = str(collection_id).strip()
    if collection_title:
        row["collection_title"] = str(collection_title).strip()
    if programming_mode:
        row["programming_mode"] = str(programming_mode).strip().lower()
    if icon_url:
        row["icon_url"] = str(icon_url).strip()
    if source:
        row["source"] = str(source).strip()
    if motif is not None:
        row["motif"] = str(motif).strip()
    if cluster_tag is not None:
        row["cluster_tag"] = str(cluster_tag).strip()
    if subtitles_enabled is not None:
        row["subtitles_enabled"] = bool(subtitles_enabled)
    if youth_safe is not None:
        row["youth_safe"] = bool(youth_safe)
    if item_rating_keys is not None:
        row["item_rating_keys"] = [
            str(k).strip() for k in item_rating_keys if str(k).strip()
        ]
    if item_hints is not None:
        row["item_hints"] = [str(h).strip() for h in item_hints if str(h).strip()]
    if craft_filters is not None:
        from projectionist.live_channels.filters import normalize_craft_filters

        row["craft_filters"] = normalize_craft_filters(craft_filters).to_dict()
    if queue_pad is not None:
        from projectionist.live_channels.queue_padding import normalize_queue_pad

        normalized_pad = normalize_queue_pad(queue_pad)
        if normalized_pad:
            row["queue_pad"] = normalized_pad
        else:
            row.pop("queue_pad", None)
    meta[cid] = row


def _stored_queue_pad(row: Mapping[str, Any]) -> Dict[str, Any]:
    from projectionist.live_channels.queue_padding import normalize_queue_pad

    return normalize_queue_pad(row.get("queue_pad"))


def station_craft_snapshot(settings: Any, channel_id: str) -> Dict[str, Any]:
    """Owner-facing craft definition from ``station_meta`` (for Settings / status)."""
    from projectionist.live_channels.filters import normalize_craft_filters

    row = station_meta_row(settings, channel_id)
    craft = normalize_craft_filters(row.get("craft_filters")).to_dict()
    return {
        "source": str(row.get("source") or "").strip(),
        "motif": str(row.get("motif") or "").strip(),
        "cluster_tag": str(row.get("cluster_tag") or "").strip(),
        "collection_id": str(row.get("collection_id") or "").strip(),
        "collection_title": str(row.get("collection_title") or "").strip(),
        "programming_mode": str(row.get("programming_mode") or "").strip(),
        "media_scope": normalize_media_scope(row.get("media_scope")),
        "craft_filters": craft,
        "item_rating_keys": [
            str(k).strip() for k in (row.get("item_rating_keys") or []) if str(k).strip()
        ],
        "item_hints": [
            str(h).strip() for h in (row.get("item_hints") or []) if str(h).strip()
        ],
        "youth_safe": bool(row.get("youth_safe")),
        "subtitles_enabled": (
            bool(row["subtitles_enabled"]) if "subtitles_enabled" in row else None
        ),
        "queue_pad": _stored_queue_pad(row),
    }


def set_station_media_scope(
    settings: Any,
    channel_id: str,
    scope: str,
) -> None:
    """Persist media_scope on settings.tunarr.station_meta[channel_id] (in-memory)."""
    set_station_meta(settings, channel_id, media_scope=scope)


def resolve_subtitles_enabled(
    settings: Any = None,
    *,
    channel_id: str = "",
    default: Optional[bool] = None,
) -> bool:
    """Resolve Tunarr subtitlesEnabled from station_meta, then household default."""
    row = station_meta_row(settings, channel_id) if channel_id else {}
    if "subtitles_enabled" in row:
        return bool(row.get("subtitles_enabled"))
    tunarr = getattr(settings, "tunarr", None) if settings is not None else None
    if tunarr is not None and hasattr(tunarr, "subtitles_enabled_default"):
        return bool(getattr(tunarr, "subtitles_enabled_default", False))
    if default is not None:
        return bool(default)
    return False


def apply_channel_subtitles_enabled(
    client: TunarrClient,
    channel_id: str,
    *,
    enabled: bool,
) -> Dict[str, Any]:
    """PUT Tunarr ``subtitlesEnabled`` for an existing channel (soft-fail on miss)."""
    cid = str(channel_id or "").strip()
    if not cid:
        raise ValueError("channel_id is required")
    channel = client.get_channel(cid)
    body = _channel_put_body(channel, subtitles_enabled=bool(enabled))
    updated = client.update_channel(cid, body)
    return {
        "ok": True,
        "channel_id": cid,
        "subtitles_enabled": bool(
            (updated or {}).get("subtitlesEnabled", enabled)
            if isinstance(updated, Mapping)
            else enabled
        ),
    }


def recipe_from_station_meta(
    settings: Any,
    channel_id: str,
    *,
    name: str = "",
    number: int = 0,
) -> Optional[ChannelRecipe]:
    """Rebuild a ChannelRecipe from persisted station_meta when possible."""
    row = station_meta_row(settings, channel_id)
    if not row:
        return None
    collection_id = str(row.get("collection_id") or "").strip()
    mode_raw = str(row.get("programming_mode") or "").strip().lower()
    source = str(row.get("source") or "").strip()
    if collection_id:
        source = source or "collection"
    rating_keys = tuple(
        str(k).strip() for k in (row.get("item_rating_keys") or []) if str(k).strip()
    )
    item_hints = tuple(
        str(h).strip() for h in (row.get("item_hints") or []) if str(h).strip()
    )
    if rating_keys and not source:
        source = "show"
    from projectionist.live_channels.filters import normalize_craft_filters

    craft_filters = normalize_craft_filters(row.get("craft_filters")).to_dict()
    has_filters = not normalize_craft_filters(craft_filters).is_empty()
    # Decade/genre stations may only have craft_filters + media_scope persisted.
    if (
        not source
        and not mode_raw
        and not collection_id
        and not has_filters
        and not rating_keys
    ):
        return None
    default_mode = (
        ProgrammingMode.SEQUENTIAL
        if source in {"collection", "show"}
        else ProgrammingMode.SHUFFLE
    )
    mode = (
        normalize_programming_mode(mode_raw, default=default_mode)
        if mode_raw
        else default_mode
    )
    return ChannelRecipe(
        name=(str(name or row.get("collection_title") or "Station").strip() or "Station")[
            :48
        ],
        number=int(number or 0) or 100,
        source=source or "motif",
        programming_mode=mode,
        media_scope=normalize_media_scope(row.get("media_scope")),
        cluster_tag=str(row.get("cluster_tag") or "").strip(),
        motif=str(row.get("motif") or "").strip(),
        collection_id=collection_id,
        collection_title=str(row.get("collection_title") or "").strip(),
        summary=f"Refill from stored recipe ({mode.value})",
        craft_filters=craft_filters,
        youth_safe=bool(row.get("youth_safe")),
        item_rating_keys=rating_keys,
        item_hints=item_hints,
        queue_pad=_stored_queue_pad(row),
    )


def merge_refill_recipe_payload(
    recipe_payload: Optional[Mapping[str, Any]],
    *,
    stored: Optional[ChannelRecipe],
    name: str,
    number: int,
    stored_scope: str,
) -> ChannelRecipe:
    """Merge an optional Admin refill overlay onto persisted station_meta.

    Admin Refill historically sent ``{media_scope}`` only. Treating that as a full
    craft payload dropped decade/genre ``craft_filters`` and collection identity,
    then wiped them on persist — modern catalog titles on a 70s station.
    """
    from projectionist.live_channels.craft import recipe_from_craft_payload
    from projectionist.live_channels.filters import normalize_craft_filters

    if not recipe_payload:
        return stored or ChannelRecipe(
            name=(name or "Station")[:48],
            number=int(number or 0) or 100,
            source="chaos",
            programming_mode=ProgrammingMode.SHUFFLE,
            media_scope=stored_scope,
            summary=f"Refill lineup for “{name}”",
        )

    payload = dict(recipe_payload)
    if stored is not None:
        stored_dict = stored.to_dict()
        for key in (
            "source",
            "programming_mode",
            "collection_id",
            "collection_title",
            "motif",
            "cluster_tag",
            "summary",
        ):
            if not str(payload.get(key) or "").strip() and stored_dict.get(key):
                payload[key] = stored_dict[key]
        for key in ("item_hints", "item_rating_keys"):
            if not payload.get(key) and stored_dict.get(key):
                payload[key] = stored_dict[key]
        # Empty / omitted craft_filters means “keep stored”, not “clear filters”.
        incoming = payload.get("craft_filters")
        if incoming is None:
            incoming = payload.get("filters")
        if incoming is None or normalize_craft_filters(incoming).is_empty():
            if stored_dict.get("craft_filters"):
                payload["craft_filters"] = dict(stored_dict["craft_filters"])
        if "youth_safe" not in payload and stored_dict.get("youth_safe"):
            payload["youth_safe"] = stored_dict["youth_safe"]
        if not payload.get("queue_pad") and stored_dict.get("queue_pad"):
            payload["queue_pad"] = dict(stored_dict["queue_pad"])
        if not payload.get("media_scope"):
            payload["media_scope"] = stored_dict.get("media_scope") or stored_scope
    elif not payload.get("media_scope"):
        payload["media_scope"] = stored_scope

    return recipe_from_craft_payload(
        {
            **payload,
            "name": str(payload.get("name") or name),
            "number": int(payload.get("number") or number or 100),
        },
        default_number=number or 100,
    )


def channel_create_body(
    recipe: ChannelRecipe,
    *,
    transcode_config_id: str,
    channel_id: Optional[str] = None,
    start_time_ms: Optional[int] = None,
    group_title: str = _DEFAULT_GROUP_TITLE,
    icon_url: str = "",
    filler_list_id: str = "",
    subtitles_enabled: Optional[bool] = None,
    settings: Any = None,
) -> Dict[str, Any]:
    """Tunarr ``POST /api/channels`` body for ``createChannelV2``.

    Tunarr 1.3.x rejects sparse bodies (HTTP 400). Required fields come from the
    live OpenAPI ``oneOf`` ``type=new`` branch — including a client-generated
    channel UUID and an existing ``transcodeConfigId``.
    """
    from projectionist.live_channels.filler import continuity_channel_fields

    tcid = str(transcode_config_id or "").strip()
    if not tcid:
        raise ValueError("transcode_config_id is required to create a Tunarr channel")
    name = str(recipe.name or "").strip() or f"Channel {int(recipe.number)}"
    if subtitles_enabled is None:
        subtitles_enabled = resolve_subtitles_enabled(settings, default=False)
    channel: Dict[str, Any] = {
        "id": str(channel_id or uuid.uuid4()),
        "name": name[:48],
        "number": int(recipe.number),
        "stealth": False,
        "duration": 0,
        "disableFillerOverlay": False,
        "groupTitle": str(group_title or _DEFAULT_GROUP_TITLE),
        "guideMinimumDuration": _DEFAULT_GUIDE_MINIMUM_DURATION_MS,
        "icon": channel_icon_body(icon_url),
        "offline": {"mode": "pic"},
        "startTime": int(
            start_time_ms if start_time_ms is not None else time.time() * 1000
        ),
        "streamMode": _DEFAULT_STREAM_MODE,
        "transcodeConfigId": tcid,
        "subtitlesEnabled": bool(subtitles_enabled),
    }
    channel.update(
        continuity_channel_fields(
            filler_list_id=filler_list_id,
            station_name=name,
            icon_url=icon_url,
            attach=bool(str(filler_list_id or "").strip()),
        )
    )
    return {"type": "new", "channel": channel}


def publish_recipes(
    client: TunarrClient,
    recipes: Sequence[ChannelRecipe | Mapping[str, Any]],
    *,
    skip_existing_numbers: bool = True,
    fill_programming: bool = True,
    settings: Any = None,
    icon_url: str = "",
    warm_streams: bool = True,
) -> Dict[str, Any]:
    """Create channels (+ programming) for each recipe. Additive; does not wipe.

    Enables Tunarr Plex libraries and fills lineups with scanned program IDs when
    available. ``fill_programming`` (default true) updates existing channels so
    re-publish can recover empty flex-only stations.
    """
    libraries = ensure_media_libraries_enabled(client, scan=True, settings=settings)
    resolved_icon = str(icon_url or "").strip() or resolve_channel_icon_url(settings)

    # Continuity filler list (union of filler paths) — attach when available.
    from projectionist.live_channels.filler import (
        attach_continuity_to_channel,
        ensure_continuity_filler_list,
    )

    filler_state: Dict[str, Any] = {}
    filler_list_id = ""
    try:
        filler_state = ensure_continuity_filler_list(client, settings, shuffle=True)
        filler_list_id = str(filler_state.get("filler_list_id") or "")
    except Exception as error:  # noqa: BLE001
        filler_state = {"ok": False, "message": str(error)[:200]}

    # Load full movie+show catalog (no movies-first early break — media_scope filters).
    catalog: List[Mapping[str, Any]] = []
    for lib in libraries.get("enabled") or []:
        lid = str(lib.get("id") or "")
        if not lid:
            continue
        try:
            catalog.extend(client.list_library_programs(lid))
        except Exception:  # noqa: BLE001
            continue

    existing = client.list_channels()
    by_number = {
        int(ch.get("number") or 0): ch
        for ch in existing
        if ch.get("number") is not None
    }
    by_name = {
        str(ch.get("name") or "").strip().lower(): ch
        for ch in existing
        if str(ch.get("name") or "").strip()
    }

    published: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    programming_updated: List[Dict[str, Any]] = []
    renamed: List[Dict[str, Any]] = []
    content_filled = 0
    total_programs = 0
    total_matched = 0
    total_match_pool = 0
    soft_capped_any = False
    full_run_any = False

    transcode_config_id = ""
    try:
        transcode_config_id = client.default_transcode_config_id()
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "published": [],
            "skipped": [],
            "programming_updated": [],
            "errors": [
                {
                    "name": "",
                    "number": 0,
                    "error": str(error)[:240],
                }
            ],
            "count_published": 0,
            "count_skipped": 0,
            "count_programming_updated": 0,
            "count_errors": 1,
            "count_content_filled": 0,
            "matched": 0,
            "match_total": 0,
            "lineup_programs": 0,
            "libraries": libraries,
            "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": (
                "Could not prepare the lineup; channels were not published."
            ),
        }

    max_flex_ms = pad_flex_max_ms(settings)

    def _scoped_catalog(scope: str) -> List[Mapping[str, Any]]:
        if normalize_media_scope(scope) == MediaScope.BOTH.value:
            return catalog
        out: List[Mapping[str, Any]] = []
        for item in catalog:
            if not isinstance(item, Mapping):
                continue
            prog = item.get("program") if isinstance(item.get("program"), Mapping) else item
            ptype = str((prog or {}).get("type") or item.get("type") or "")
            if program_type_matches_scope(ptype, scope):
                out.append(item)
        return out

    def _persist_recipe(channel_id: str, recipe: ChannelRecipe, *, icon: str = "") -> None:
        if not channel_id or settings is None:
            return
        set_station_meta(
            settings,
            channel_id,
            media_scope=normalize_media_scope(getattr(recipe, "media_scope", None)),
            collection_id=str(recipe.collection_id or ""),
            collection_title=str(recipe.collection_title or ""),
            programming_mode=recipe.programming_mode.value,
            icon_url=icon,
            source=str(recipe.source or ""),
            craft_filters=getattr(recipe, "craft_filters", None) or {},
            motif=str(recipe.motif or ""),
            cluster_tag=str(recipe.cluster_tag or ""),
            subtitles_enabled=resolve_subtitles_enabled(settings, default=False),
            youth_safe=bool(getattr(recipe, "youth_safe", False)),
            item_rating_keys=list(getattr(recipe, "item_rating_keys", ()) or ()),
            item_hints=list(getattr(recipe, "item_hints", ()) or ()),
            queue_pad=dict(getattr(recipe, "queue_pad", None) or {}),
        )

    def _apply_programming(channel_id: str, recipe: ChannelRecipe) -> Dict[str, Any]:
        nonlocal content_filled, total_programs, total_matched, total_match_pool
        nonlocal full_run_any, soft_capped_any
        scope = normalize_media_scope(getattr(recipe, "media_scope", None))
        stats: Dict[str, Any] = {}
        programs = collect_programs_for_recipe(
            client,
            recipe,
            catalog=_scoped_catalog(scope),
            media_scope=scope,
            settings=settings,
            match_stats=stats,
        )
        programs = apply_queue_padding(
            client,
            recipe,
            programs,
            catalog=_scoped_catalog(scope),
            media_scope=scope,
            settings=settings,
            stats=stats,
        )
        prog_body = programming_body_for_recipe(
            recipe,
            programs=programs,
            pad_lineups=True,
            max_flex_ms=max_flex_ms,
        )
        programming = (
            client.set_channel_programming(channel_id, prog_body)
            if prog_body is not None
            else {}
        )
        if programs:
            content_filled += 1
        total_programs += len(programs)
        total_matched += int(stats.get("matched") or 0)
        total_match_pool += int(stats.get("match_total") or 0)
        is_full = bool(stats.get("full_run"))
        if is_full:
            full_run_any = True
        else:
            soft_capped_any = True
        flex_count = sum(
            1
            for row in (prog_body or {}).get("lineup") or []
            if isinstance(row, Mapping) and str(row.get("type") or "") == "flex"
        )
        return {
            "programming": dict(programming) if programming else {},
            "program_count": len(programs),
            "titles": [p.get("title") for p in programs[:8]],
            "media_scope": scope,
            "flex_pads": flex_count,
            "padded": flex_count > 0,
            "matched": int(stats.get("matched") or 0),
            "match_total": int(stats.get("match_total") or 0),
            "full_run": is_full,
            "fill_target": int(stats.get("fill_target") or 0),
            "soft_capped": not is_full,
            "queue_pad": dict(stats.get("queue_pad") or {}),
        }

    for raw in recipes:
        recipe = raw if isinstance(raw, ChannelRecipe) else recipe_from_mapping(raw)
        key_name = recipe.name.strip().lower()
        # Only number collisions are "existing" for skip_existing_numbers.
        # A free number + colliding name used to count as skipped / overwrite the
        # name-matched station (e.g. craft decade publish named "Mystery" via
        # auto motif) — that looked like "skipped 1" for a brand-new station.
        if skip_existing_numbers and recipe.number in by_number:
            match = by_number.get(recipe.number) or {}
            channel_id = str(match.get("id") or match.get("uuid") or "")
            station_icon = resolved_icon
            if recipe.collection_id:
                station_icon = (
                    resolve_collection_icon_url(settings, recipe.collection_id)
                    or resolved_icon
                )
            _persist_recipe(channel_id, recipe, icon=station_icon)
            if filler_list_id and channel_id and isinstance(match, Mapping):
                try:
                    attach_continuity_to_channel(
                        client,
                        match,
                        filler_list_id=filler_list_id,
                        icon_url=station_icon,
                    )
                except Exception:  # noqa: BLE001
                    pass
            if fill_programming and channel_id:
                try:
                    applied = _apply_programming(channel_id, recipe)
                    programming_updated.append(
                        {
                            "name": recipe.name,
                            "number": recipe.number,
                            "channel_id": channel_id,
                            "reason": "number_exists",
                            **applied,
                        }
                    )
                except Exception as prog_error:  # noqa: BLE001
                    errors.append(
                        {
                            "name": recipe.name,
                            "number": recipe.number,
                            "error": f"fill_programming: {str(prog_error)[:220]}",
                        }
                    )
            else:
                skipped.append(
                    {
                        "name": recipe.name,
                        "number": recipe.number,
                        "reason": "number_exists",
                        "channel_id": channel_id or None,
                        "note": (
                            "Channel number already on the dial. "
                            + (
                                "Lineup not updated; re-publish with fill_programming=true "
                                "after Tunarr libraries are enabled and scanned."
                                if not fill_programming
                                else "Could not resolve Tunarr channel id to refresh the lineup."
                            )
                        ),
                    }
                )
            continue
        if key_name and key_name in by_name:
            unique = unique_station_name(recipe.name, by_name)
            if unique != recipe.name:
                renamed.append(
                    {
                        "from": recipe.name,
                        "to": unique,
                        "number": recipe.number,
                        "reason": "name_exists",
                    }
                )
                recipe = replace_recipe(recipe, name=unique)
                key_name = recipe.name.strip().lower()
        try:
            station_icon = resolved_icon
            if recipe.collection_id:
                station_icon = (
                    resolve_collection_icon_url(settings, recipe.collection_id)
                    or resolved_icon
                )
            created = client.create_channel(
                channel_create_body(
                    recipe,
                    transcode_config_id=transcode_config_id,
                    icon_url=station_icon,
                    filler_list_id=filler_list_id,
                    settings=settings,
                )
            )
            channel_id = str(created.get("id") or created.get("uuid") or "")
            _persist_recipe(channel_id, recipe, icon=station_icon)
            programming: Mapping[str, Any] = {}
            program_count = 0
            titles: List[Any] = []
            matched = 0
            match_total = 0
            if channel_id:
                try:
                    applied = _apply_programming(channel_id, recipe)
                    programming = applied.get("programming") or {}
                    program_count = int(applied.get("program_count") or 0)
                    titles = list(applied.get("titles") or [])
                    matched = int(applied.get("matched") or 0)
                    match_total = int(applied.get("match_total") or 0)
                except Exception as prog_error:  # noqa: BLE001
                    programming = {"error": str(prog_error)[:200]}
            published.append(
                {
                    "name": recipe.name,
                    "number": recipe.number,
                    "source": recipe.source,
                    "media_scope": normalize_media_scope(
                        getattr(recipe, "media_scope", None)
                    ),
                    "channel_id": channel_id,
                    "channel": dict(created),
                    "programming": dict(programming) if programming else {},
                    "program_count": program_count,
                    "titles": titles,
                    "matched": matched,
                    "match_total": match_total,
                    "icon_url": station_icon,
                }
            )
            if recipe.number:
                by_number[recipe.number] = created
            if key_name:
                by_name[key_name] = created
        except Exception as error:  # noqa: BLE001
            errors.append(
                {
                    "name": recipe.name,
                    "number": recipe.number,
                    "error": str(error)[:240],
                }
            )

    touched_ids = [
        str(row.get("channel_id") or "")
        for row in (*published, *programming_updated)
        if str(row.get("channel_id") or "").strip()
    ]
    # Prefer preparing every station after publish — idle channels go cold and
    # deep mid-program seeks race Plex ("session has ended").
    prepare = prepare_channels_for_playback(
        client,
        settings=settings,
        channel_ids=touched_ids or None,
        icon_url=resolved_icon,
        align_playhead=True,
        warm_streams=bool(warm_streams),
    )
    labels = prepare.get("labels") if isinstance(prepare.get("labels"), dict) else {}
    warmed = list(prepare.get("warmed") or [])

    ok = bool(published) and not errors
    if published and errors:
        ok = False
    if not published and not errors and (skipped or programming_updated):
        ok = True  # idempotent re-publish / fill

    soft_capped = soft_capped_any and not full_run_any
    if soft_capped_any and full_run_any:
        # Mixed pack: still call out soft-capped stations.
        soft_capped = True
    honesty = craft_soft_cap_honesty(
        fill_mode="soft" if soft_capped_any and not full_run_any else (
            "full_run" if full_run_any and not soft_capped_any else "soft"
        ),
        matched=total_matched,
        program_count=total_programs,
    )
    match_note = match_feedback_note(
        matched=total_matched,
        match_total=total_match_pool,
        program_count=total_programs,
        stations_filled=content_filled,
        full_run=None if soft_capped_any and full_run_any else (
            False if soft_capped_any else (True if full_run_any else None)
        ),
        soft_capped=soft_capped_any and not full_run_any,
    )
    note = (
        "Stations use Tunarr program IDs when Plex libraries are enabled and "
        "scanned; otherwise lineups stay flex/empty and Plex playback ends immediately."
    )
    if match_note:
        note = match_note
    elif content_filled:
        note = (
            f"Filled {content_filled} station lineup(s) · "
            f"{total_programs} program(s) scheduled."
        )
        if soft_capped_any and not full_run_any:
            note = f"{note} {honesty['note']}"
    elif not catalog:
        note = (
            "No Tunarr program IDs yet — libraries were enabled and a scan was started. "
            "Wait for the scan, then publish again with fill lineups."
        )
    if soft_capped_any and full_run_any:
        note += (
            f" Some motif/taste stations use a soft sample "
            f"(~{_DEFAULT_FILL_LIMIT}–{_SOFT_FILL_CAP}); collection/show stations "
            f"fill up to {_FULL_RUN_FILL_CAP}."
        )
    if labels.get("count_updated"):
        note += f" Updated labels/icons on {labels['count_updated']} station(s)."
    if labels.get("count_cleared_stock"):
        note += (
            f" Cleared {labels['count_cleared_stock']} stock Tunarr logo(s) "
            "(no station art yet)."
        )
    if prepare.get("count_aligned"):
        note += (
            f" Start-over on {prepare['count_aligned']} station(s) "
            "(avoids deep mid-program seeks that fail cold Plex tunes)."
        )
    if warmed:
        note += f" Warmed {prepare.get('count_warmed_ok', 0)}/{len(warmed)} stream(s)."
    if filler_list_id and filler_state.get("ready"):
        note += f" Continuity filler list attached ({filler_state.get('program_count', 0)} shorts)."
    elif filler_state.get("message"):
        note += f" Continuity: {filler_state.get('message')}"
    if renamed:
        bits = [f"“{row.get('from')}” → “{row.get('to')}”" for row in renamed[:3]]
        note += (
            f" Renamed {len(renamed)} station(s) to avoid a name clash"
            + (f" ({'; '.join(bits)})" if bits else "")
            + "."
        )
    if skipped:
        reasons = sorted(
            {
                str(row.get("reason") or "skipped")
                for row in skipped
                if str(row.get("reason") or "").strip()
            }
        )
        note += (
            f" Skipped {len(skipped)} existing channel number(s)"
            + (f" ({', '.join(reasons)})" if reasons else "")
            + "."
        )

    icon_probe = probe_icon_url(resolved_icon) if resolved_icon else {
        "ok": False,
        "url": "",
        "message": "No station art URL — Plex will not show a Tunarr stock logo.",
    }

    return {
        "ok": ok or (bool(published) and not errors),
        "published": published,
        "skipped": skipped,
        "programming_updated": programming_updated,
        "renamed": renamed,
        "errors": errors,
        "count_published": len(published),
        "count_skipped": len(skipped),
        "count_programming_updated": len(programming_updated),
        "count_renamed": len(renamed),
        "count_errors": len(errors),
        "count_content_filled": content_filled,
        "matched": total_matched,
        "match_total": total_match_pool,
        "lineup_programs": total_programs,
        "libraries": libraries,
        "catalog_size": len(catalog),
        "labels": labels,
        "warmed": warmed,
        "prepare": prepare,
        "filler": filler_state,
        "icon_probe": icon_probe,
        "fill_mode": honesty["fill_mode"],
        "soft_capped": soft_capped,
        "soft_default": _DEFAULT_FILL_LIMIT,
        "soft_cap": _SOFT_FILL_CAP,
        "full_run_cap": _FULL_RUN_FILL_CAP,
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": note,
    }


def _next_free_channel_number(client: TunarrClient, settings: Any = None) -> int:
    """First free station number (Tunarr lineup ∪ Plex-occupied) from the base."""
    from projectionist.live_channels.craft import next_channel_number

    existing = client.list_channels()
    numbers = [int(ch.get("number") or 0) for ch in existing if ch.get("number") is not None]
    occupied: List[int] = []
    base = 100
    if settings is not None:
        try:
            from projectionist.live_channels.plex_attach import (
                collect_plex_occupied_channel_numbers,
            )

            occupied = collect_plex_occupied_channel_numbers(settings)
        except Exception:  # noqa: BLE001
            occupied = []
        tunarr = getattr(settings, "tunarr", None)
        try:
            base = int(getattr(tunarr, "channel_number_base", 100) or 100)
        except (TypeError, ValueError):
            base = 100
    return next_channel_number(numbers, base=base, occupied=occupied)


def publish_collection_channel(
    client: TunarrClient,
    *,
    collection_id: str = "",
    collection_title: str = "",
    channel_number: int = 0,
    name: str = "",
    programming_mode: str = "",
    craft_filters: Optional[Mapping[str, Any]] = None,
    media_scope: str = "",
    queue_pad: Optional[Mapping[str, Any]] = None,
    settings: Any = None,
) -> Dict[str, Any]:
    """Create a station from a Plex/Projectionist collection (seq / shuffle)."""
    from projectionist.live_channels.filters import normalize_craft_filters
    from projectionist.live_channels.queue_padding import normalize_queue_pad

    title = str(collection_title or name or "Collection").strip() or "Collection"
    number = int(channel_number or 0)
    if number <= 0:
        number = _next_free_channel_number(client, settings)
    mode = normalize_programming_mode(
        programming_mode or ProgrammingMode.SEQUENTIAL.value,
        default=ProgrammingMode.SEQUENTIAL,
    )
    hints: tuple[str, ...] = ()
    rating_keys: tuple[str, ...] = ()
    if settings is not None:
        children = plex_collection_children(
            settings, collection_id, limit=_FULL_RUN_FILL_CAP
        )
        hints = tuple(row["title"] for row in children if row.get("title"))
        rating_keys = tuple(
            row["rating_key"] for row in children if row.get("rating_key")
        )
    mode_label = {
        ProgrammingMode.SEQUENTIAL: "Sequential",
        ProgrammingMode.SHUFFLE: "Shuffle",
    }.get(mode, mode.value)
    recipe = ChannelRecipe(
        name=title[:48],
        number=number,
        source="collection",
        programming_mode=mode,
        media_scope=normalize_media_scope(media_scope or MediaScope.BOTH.value),
        collection_id=str(collection_id or "").strip(),
        collection_title=title,
        summary=f"{mode_label} channel from collection “{title}”",
        item_hints=hints,
        item_rating_keys=rating_keys,
        craft_filters=normalize_craft_filters(craft_filters).to_dict(),
        queue_pad=normalize_queue_pad(queue_pad),
    )
    result = publish_recipes(
        client,
        [recipe],
        skip_existing_numbers=True,
        settings=settings,
    )
    result["recipe"] = recipe.to_dict()
    result["item_hint_count"] = len(hints)
    result["item_rating_key_count"] = len(rating_keys)
    return result


def resolve_show_for_channel(
    *,
    show_rating_key: str = "",
    show_title: str = "",
    show_item_id: int = 0,
    settings: Any = None,
) -> Tuple[str, str]:
    """Resolve a TV show to ``(rating_key, title)`` for a single-show station.

    A library ``show_item_id`` wins when it resolves; otherwise the caller's
    explicit Plex ``ratingKey`` is used. Raises ``ValueError`` when neither
    yields a key, or when the library row is not a TV show.
    """
    del settings  # library rows come from the job-manager DB, not settings
    rating_key = str(show_rating_key or "").strip()
    title = str(show_title or "").strip()
    item_id = int(show_item_id or 0)
    if item_id > 0:
        db = None
        try:
            from projectionist.web.jobs import get_job_manager

            db = get_job_manager().db
        except Exception:  # noqa: BLE001
            db = None
        row = db.library_item_by_id(item_id) if db is not None else None
        if row is None:
            raise ValueError(f"Library item {item_id} was not found")
        media_type = str(row["media_type"] or "").strip().lower()
        if media_type not in {"show", "shows", "tv"}:
            raise ValueError(
                f"Library item {item_id} is a {media_type or 'unknown'}, not a TV show"
            )
        rating_key = str(row["rating_key"] or "").strip() or rating_key
        title = title or str(row["title"] or "").strip()
    if not rating_key:
        raise ValueError("A show ratingKey or library item id is required")
    return rating_key, title or "Show"


def publish_show_channel(
    client: TunarrClient,
    *,
    show_rating_key: str = "",
    show_title: str = "",
    show_item_id: int = 0,
    channel_number: int = 0,
    name: str = "",
    programming_mode: str = "",
    queue_pad: Optional[Mapping[str, Any]] = None,
    settings: Any = None,
) -> Dict[str, Any]:
    """Create a nonstop station from one TV show (seq run / shuffle).

    The show ``ratingKey`` rides ``item_rating_keys``; fill expands it to every
    episode via Tunarr descendants, so the station is a full-run marathon.
    """
    from projectionist.live_channels.queue_padding import normalize_queue_pad

    rating_key, title = resolve_show_for_channel(
        show_rating_key=show_rating_key,
        show_title=show_title,
        show_item_id=show_item_id,
        settings=settings,
    )
    number = int(channel_number or 0)
    if number <= 0:
        number = _next_free_channel_number(client, settings)
    mode = normalize_programming_mode(
        programming_mode or ProgrammingMode.SEQUENTIAL.value,
        default=ProgrammingMode.SEQUENTIAL,
    )
    mode_label = {
        ProgrammingMode.SEQUENTIAL: "Sequential",
        ProgrammingMode.SHUFFLE: "Shuffle",
    }.get(mode, mode.value)
    station_name = str(name or "").strip() or f"{title} Channel"
    recipe = ChannelRecipe(
        name=station_name[:48],
        number=number,
        source="show",
        programming_mode=mode,
        media_scope=MediaScope.TV.value,
        summary=f"{mode_label} channel from the show “{title}”",
        item_hints=(title,),
        item_rating_keys=(rating_key,),
        queue_pad=normalize_queue_pad(queue_pad),
    )
    result = publish_recipes(
        client,
        [recipe],
        skip_existing_numbers=True,
        settings=settings,
    )
    result["recipe"] = recipe.to_dict()
    result["show_rating_key"] = rating_key
    result["show_title"] = title
    result["item_hint_count"] = 1
    result["item_rating_key_count"] = 1
    return result


def publish_custom_channel(
    client: TunarrClient,
    recipe_payload: Mapping[str, Any] | ChannelRecipe,
    *,
    fill_programming: bool = True,
    channel_number_base: int = 100,
    settings: Any = None,
) -> Dict[str, Any]:
    """Publish one craft-form recipe (additive; fills lineup when possible)."""
    from projectionist.live_channels.craft import (
        next_channel_number,
        recipe_from_craft_payload,
    )

    existing = client.list_channels()
    numbers = [int(ch.get("number") or 0) for ch in existing if ch.get("number") is not None]
    occupied: List[int] = []
    if settings is not None:
        try:
            from projectionist.live_channels.plex_attach import (
                collect_plex_occupied_channel_numbers,
            )

            occupied = collect_plex_occupied_channel_numbers(settings)
        except Exception:  # noqa: BLE001
            occupied = []
    default_number = next_channel_number(
        numbers, base=int(channel_number_base or 100), occupied=occupied
    )
    remapped_number_from = 0
    if isinstance(recipe_payload, ChannelRecipe):
        recipe = recipe_payload
        if recipe.number <= 0:
            recipe = replace_recipe(recipe, number=default_number)
    else:
        recipe = recipe_from_craft_payload(
            recipe_payload or {},
            default_number=default_number,
        )
    # Craft "publish new station" must not land on an occupied number — remap
    # instead of counting the recipe as skipped / refreshing the wrong station.
    occupied_numbers = {
        int(ch.get("number") or 0)
        for ch in existing
        if ch.get("number") is not None and int(ch.get("number") or 0) > 0
    }
    if recipe.number in occupied_numbers:
        remapped_number_from = int(recipe.number)
        recipe = replace_recipe(recipe, number=default_number)
    # Enrich collection recipes with Plex children (ratingKeys first).
    if (
        settings is not None
        and recipe.source == "collection"
        and recipe.collection_id
        and not recipe.item_rating_keys
    ):
        children = plex_collection_children(
            settings, recipe.collection_id, limit=_FULL_RUN_FILL_CAP
        )
        hints = tuple(row["title"] for row in children if row.get("title"))
        keys = tuple(row["rating_key"] for row in children if row.get("rating_key"))
        if hints or keys:
            recipe = replace_recipe(
                recipe,
                item_hints=list(hints or recipe.item_hints),
                item_rating_keys=list(keys),
            )
    result = publish_recipes(
        client,
        [recipe],
        skip_existing_numbers=True,
        fill_programming=fill_programming,
        settings=settings,
    )
    result["recipe"] = recipe.to_dict()
    if remapped_number_from:
        result["remapped_number_from"] = remapped_number_from
        result["remapped_number_to"] = int(recipe.number)
        prior = str(result.get("note") or "").strip()
        remap_note = (
            f"Channel number {remapped_number_from} was taken — "
            f"published on {int(recipe.number)} instead."
        )
        result["note"] = f"{prior} {remap_note}".strip() if prior else remap_note
    return result


def refill_channel_lineup(
    client: TunarrClient,
    channel_id: str,
    *,
    recipe_payload: Optional[Mapping[str, Any]] = None,
    settings: Any = None,
    pad_lineups: bool = True,
    attach_continuity: bool = True,
) -> Dict[str, Any]:
    """Re-fill an existing Tunarr station lineup from craft vocabulary / Shuffle."""
    from projectionist.live_channels.filters import normalize_craft_filters
    from projectionist.live_channels.filler import (
        attach_continuity_to_channel,
        ensure_continuity_filler_list,
    )

    cid = str(channel_id or "").strip()
    if not cid:
        raise ValueError("channel_id is required")
    match: Optional[Mapping[str, Any]] = None
    for ch in client.list_channels():
        if not isinstance(ch, Mapping):
            continue
        if str(ch.get("id") or ch.get("uuid") or "") == cid:
            match = ch
            break
    if match is None:
        raise ValueError(f"Channel not found: {cid}")

    number = int(match.get("number") or 0)
    name = str(match.get("name") or "Station").strip() or "Station"
    stored_scope = resolve_media_scope(settings, channel_id=cid, default=MediaScope.BOTH.value)
    # Always start from station_meta; merge partial Admin overlays (media_scope-only).
    stored = recipe_from_station_meta(settings, cid, name=name, number=number or 100)
    recipe = merge_refill_recipe_payload(
        recipe_payload,
        stored=stored,
        name=name,
        number=number or 100,
        stored_scope=stored_scope,
    )

    # Re-load collection ratingKeys so Shuffle reshuffles the same ID pool.
    if (
        settings is not None
        and recipe.source == "collection"
        and recipe.collection_id
        and not recipe.item_rating_keys
    ):
        children = plex_collection_children(
            settings, recipe.collection_id, limit=_FULL_RUN_FILL_CAP
        )
        hints = tuple(row["title"] for row in children if row.get("title"))
        keys = tuple(row["rating_key"] for row in children if row.get("rating_key"))
        if hints or keys:
            recipe = replace_recipe(
                recipe,
                collection_title=recipe.collection_title or name,
                summary=recipe.summary or f"Refill lineup for “{name}”",
                item_hints=list(hints or recipe.item_hints),
                item_rating_keys=list(keys),
            )

    scope = normalize_media_scope(getattr(recipe, "media_scope", None) or stored_scope)
    craft_for_meta = normalize_craft_filters(getattr(recipe, "craft_filters", None))
    if settings is not None:
        set_station_meta(
            settings,
            cid,
            media_scope=scope,
            collection_id=str(recipe.collection_id or ""),
            collection_title=str(recipe.collection_title or ""),
            programming_mode=recipe.programming_mode.value,
            source=str(recipe.source or ""),
            # Never wipe decade/genre filters with an empty overlay from Refill.
            craft_filters=craft_for_meta.to_dict() if not craft_for_meta.is_empty() else None,
            motif=str(recipe.motif or ""),
            cluster_tag=str(recipe.cluster_tag or ""),
            youth_safe=bool(getattr(recipe, "youth_safe", False)),
            item_rating_keys=list(getattr(recipe, "item_rating_keys", ()) or ()),
            item_hints=list(getattr(recipe, "item_hints", ()) or ()),
            queue_pad=dict(getattr(recipe, "queue_pad", None) or {}),
        )

    media_types = (
        ("shows",)
        if scope == MediaScope.TV.value
        else ("movies",)
        if scope == MediaScope.MOVIES.value
        else ("movies", "shows")
    )
    libraries = ensure_media_libraries_enabled(
        client, media_types=media_types, scan=True, settings=settings
    )
    catalog: List[Mapping[str, Any]] = []
    for lib in libraries.get("enabled") or []:
        if not library_type_matches_scope(lib.get("media_type"), scope):
            continue
        lid = str(lib.get("id") or "")
        if not lid:
            continue
        try:
            catalog.extend(client.list_library_programs(lid))
        except Exception:  # noqa: BLE001
            continue

    stats: Dict[str, Any] = {}
    programs = collect_programs_for_recipe(
        client,
        recipe,
        catalog=catalog,
        media_scope=scope,
        settings=settings,
        match_stats=stats,
    )
    programs = apply_queue_padding(
        client,
        recipe,
        programs,
        catalog=catalog,
        media_scope=scope,
        settings=settings,
        stats=stats,
    )
    prog_body = programming_body_for_recipe(
        recipe,
        programs=programs,
        pad_lineups=pad_lineups,
        max_flex_ms=pad_flex_max_ms(settings),
    )
    programming = (
        client.set_channel_programming(cid, prog_body) if prog_body is not None else {}
    )
    flex_count = sum(
        1
        for row in (prog_body or {}).get("lineup") or []
        if isinstance(row, Mapping) and str(row.get("type") or "") == "flex"
    )

    filler_state: Dict[str, Any] = {}
    if attach_continuity:
        try:
            filler_state = ensure_continuity_filler_list(client, settings, shuffle=False)
            fid = str(filler_state.get("filler_list_id") or "")
            if fid:
                attach_continuity_to_channel(
                    client,
                    match,
                    filler_list_id=fid,
                    icon_url=resolve_channel_icon_url(settings),
                )
        except Exception as error:  # noqa: BLE001
            filler_state = {"ok": False, "message": str(error)[:200]}

    matched = int(stats.get("matched") or 0)
    match_total = int(stats.get("match_total") or 0)
    is_full = bool(stats.get("full_run"))
    craft_active = not craft_for_meta.is_empty()
    note = match_feedback_note(
        matched=matched,
        match_total=match_total,
        program_count=len(programs),
        full_run=is_full,
        soft_capped=not is_full,
    )
    if not note:
        if programs:
            note = (
                f"Filled {len(programs)} titles into {name}"
                + (f" ({flex_count} flex pad(s))" if flex_count else "")
                + "."
            )
            if not is_full:
                note = (
                    f"{note} "
                    + craft_soft_cap_honesty(
                        fill_mode="soft",
                        matched=matched,
                        program_count=len(programs),
                    )["note"]
                )
        elif craft_active:
            note = (
                "No titles match this station’s saved filters (decade / genre / theme). "
                "Lineup left empty rather than filling from the whole library."
            )
        else:
            note = (
                "No Tunarr program IDs yet — wait for the library scan, then refill again."
            )
    if normalize_programming_mode(recipe.programming_mode) == ProgrammingMode.SHUFFLE:
        note += " Reshuffled (shuffle)."

    return {
        "ok": bool(programs),
        "channel_id": cid,
        "name": name,
        "number": number,
        "program_count": len(programs),
        "matched": matched,
        "match_total": match_total,
        "full_run": is_full,
        "soft_capped": not is_full,
        "soft_default": _DEFAULT_FILL_LIMIT,
        "soft_cap": _SOFT_FILL_CAP,
        "full_run_cap": _FULL_RUN_FILL_CAP,
        "lineup_programs": len(programs),
        "titles": [p.get("title") for p in programs[:8]],
        "programming": dict(programming) if programming else {},
        "libraries": libraries,
        "catalog_size": len(catalog),
        "recipe": recipe.to_dict(),
        "media_scope": scope,
        "flex_pads": flex_count,
        "padded": flex_count > 0,
        "filler": filler_state,
        "note": note,
    }


def delete_published_channel(client: TunarrClient, channel_id: str) -> Dict[str, Any]:
    """Delete a Tunarr station by id (owner manage path)."""
    cid = str(channel_id or "").strip()
    if not cid:
        raise ValueError("channel_id is required")
    client.delete_channel(cid)
    return {"ok": True, "channel_id": cid, "deleted": True}


def refresh_stations_with_stored_recipes(
    client: TunarrClient,
    *,
    settings: Any = None,
    limit: int = 40,
) -> Dict[str, Any]:
    """Refill stations that have a persisted recipe (post-sync / arrivals).

    Additive — does not delete or create stations. Skips when Live Channels /
    Tunarr URL are unset. Best-effort; individual station errors are collected.
    """
    if settings is None:
        return {"ok": False, "refreshed": [], "errors": [], "note": "No settings."}
    features = getattr(settings, "features", None)
    if not bool(getattr(features, "live_channels_enabled", False)):
        return {"ok": True, "refreshed": [], "errors": [], "skipped": True, "note": "Live Channels off."}
    tunarr = getattr(settings, "tunarr", None)
    if not bool(getattr(tunarr, "auto_refresh_stations_after_sync", True)):
        return {
            "ok": True,
            "refreshed": [],
            "errors": [],
            "skipped": True,
            "note": "Auto-refresh after sync is off.",
        }
    meta = getattr(tunarr, "station_meta", None) if tunarr is not None else None
    if not isinstance(meta, Mapping) or not meta:
        return {"ok": True, "refreshed": [], "errors": [], "note": "No stored station recipes."}

    refreshed: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    for channel_id in list(meta.keys())[: max(1, min(int(limit or 40), 80))]:
        cid = str(channel_id or "").strip()
        if not cid:
            continue
        row = meta.get(cid)
        if not isinstance(row, Mapping):
            continue
        if not (
            row.get("collection_id")
            or row.get("programming_mode")
            or row.get("source")
            or row.get("craft_filters")
        ):
            continue
        try:
            result = refill_channel_lineup(
                client,
                cid,
                settings=settings,
                pad_lineups=True,
                attach_continuity=False,
            )
            refreshed.append(
                {
                    "channel_id": cid,
                    "ok": bool(result.get("ok")),
                    "program_count": int(result.get("program_count") or 0),
                    "note": str(result.get("note") or "")[:160],
                }
            )
        except Exception as error:  # noqa: BLE001
            errors.append({"channel_id": cid, "error": str(error)[:200]})
    return {
        "ok": not errors or bool(refreshed),
        "refreshed": refreshed,
        "errors": errors,
        "count_refreshed": len(refreshed),
        "count_errors": len(errors),
        "note": (
            f"Refreshed {len(refreshed)} station(s) from stored recipes"
            + (f" · {len(errors)} error(s)" if errors else "")
            + "."
        ),
    }


def tunarr_client_from_settings(settings: Any) -> Any:
    """Local lineup store. The name remains so existing call sites keep working."""
    from projectionist.live_channels.lineup_client import LocalLineupClient

    return LocalLineupClient(settings)

# Re-exports for callers that still import from publish (icons / playback / programming).
__all__ = [
    "TunarrClient",
    "align_channel_playhead_to_program_start",
    "apply_channel_name",
    "apply_channel_subtitles_enabled",
    "apply_queue_padding",
    "apply_station_icons",
    "channel_create_body",
    "channel_icon_body",
    "channel_icon_hides_plex_label",
    "collect_programs_for_recipe",
    "configured_plex_external_keys",
    "craft_fill_mode",
    "craft_soft_cap_honesty",
    "delete_published_channel",
    "ensure_channel_labels",
    "ensure_media_libraries_enabled",
    "full_run_fill_cap",
    "is_default_tunarr_icon",
    "match_feedback_note",
    "merge_refill_recipe_payload",
    "pad_flex_max_ms",
    "plex_collection_children",
    "plex_collection_item_hints",
    "plex_collection_rating_keys",
    "plex_media_source_body",
    "prepare_channels_for_playback",
    "probe_icon_url",
    "programming_body_for_recipe",
    "publish_collection_channel",
    "publish_custom_channel",
    "publish_recipes",
    "publish_show_channel",
    "random_slot_schedule_for_programs",
    "recipe_from_station_meta",
    "refill_channel_lineup",
    "refresh_stations_with_stored_recipes",
    "resolve_channel_icon_url",
    "resolve_collection_icon_url",
    "resolve_media_scope",
    "resolve_show_for_channel",
    "resolve_subtitles_enabled",
    "set_station_media_scope",
    "set_station_meta",
    "should_align_playhead",
    "snap_future_channel_start_time",
    "soft_fill_cap",
    "soft_fill_default",
    "station_craft_snapshot",
    "station_meta_row",
    "tunarr_client_from_settings",
    "unique_station_name",
    "warm_channel_stream",
    "wire_plex_media_source",
]
