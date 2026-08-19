"""Publish starter recipes / collections to Tunarr via OpenAPI."""

from __future__ import annotations

import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from projectionist.connectors.tunarr import TunarrClient
from projectionist.facets import motif_search_expansions
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

# Prefer these Plex library mediaTypes when enabling Tunarr libraries for fill.
_PREFERRED_LIBRARY_TYPES = frozenset({"movies", "shows"})
_MIN_PROGRAM_DURATION_MS = 60_000
# Motif / taste / filtered craft soft default (not a hard product ceiling).
_DEFAULT_FILL_LIMIT = 30
_SOFT_FILL_CAP = 80
# Collection / show full-run: fill all ID-resolved episodes (safety cap).
_FULL_RUN_FILL_CAP = 1000
_DEFAULT_PAD_FLEX_MAX_MINUTES = 15
# Stock Tunarr mark — never push as a Plex guide logo when station art is missing.
_TUNARR_DEFAULT_ICON_SUFFIX = "/images/tunarr.png"


def soft_fill_default() -> int:
    return _DEFAULT_FILL_LIMIT


def soft_fill_cap() -> int:
    return _SOFT_FILL_CAP


def full_run_fill_cap() -> int:
    return _FULL_RUN_FILL_CAP


def is_default_tunarr_icon(url: str = "") -> bool:
    """True when ``url`` is Tunarr's stock mark (or empty)."""
    path = str(url or "").strip().lower()
    if not path:
        return True
    return path.endswith(_TUNARR_DEFAULT_ICON_SUFFIX)


def craft_fill_mode(*, collection_id: str = "", source: str = "") -> str:
    """Return ``full_run`` for collection/show stations, else ``soft``."""
    src = str(source or "").strip().lower()
    if src == "chaos":
        return "soft"
    if src == "collection" or str(collection_id or "").strip():
        return "full_run"
    return "soft"


def unique_station_name(
    name: str,
    existing_names: Mapping[str, Any] | Sequence[str] | None = None,
) -> str:
    """Return ``name`` or ``Name 2`` / ``Name 3`` … when the dial already has it.

    Used when a free channel *number* is available but the recipe name collides —
    craft should still create a new station instead of skipping / overwriting.
    """
    base = str(name or "").strip() or "Custom Station"
    base = base[:48]
    if existing_names is None:
        return base
    if isinstance(existing_names, Mapping):
        taken = {str(k).strip().lower() for k in existing_names if str(k).strip()}
    else:
        taken = {str(n).strip().lower() for n in existing_names if str(n).strip()}
    key = base.lower()
    if key not in taken:
        return base
    for index in range(2, 100):
        # Keep within Tunarr's short display budget.
        suffix = f" {index}"
        candidate = f"{base[: max(1, 48 - len(suffix))]}{suffix}"
        if candidate.lower() not in taken:
            return candidate
    return f"{base[:40]} {uuid.uuid4().hex[:6]}"


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

# Tunarr 1.3.x ``createChannelV2`` requires these channel fields (OpenAPI).
_DEFAULT_GROUP_TITLE = "Projectionist"
_DEFAULT_GUIDE_MINIMUM_DURATION_MS = 30_000
_DEFAULT_STREAM_MODE = "hls"

# Cold HDHR tunes that seek deep into a program (or past EOF) lose the race with
# Plex before ffmpeg writes playlist.m3u8 → "Stream not ready yet" / 0-byte .ts
# → Plex "This live TV session has ended." Snap playhead forward when deep/cold.
_ALIGN_MIN_ELAPSED_MS = 5 * 60 * 1000
_WARM_DEFAULT_TIMEOUT_S = 45
_WARM_MIN_TS_BYTES = 200_000
_WARM_POLL_SLEEP_S = 1.5


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
            "message": "No Plex media source in Tunarr yet.",
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


def channel_icon_body(icon_url: str = "") -> Dict[str, Any]:
    """Tunarr channel icon object. Empty path → generic/blank in some Plex clients."""
    path = str(icon_url or "").strip()
    if not path:
        return {
            "path": "",
            "width": 0,
            "duration": 0,
            "position": "bottom-right",
        }
    return {
        "path": path,
        "width": 256,
        "duration": 0,
        "position": "bottom-right",
    }


def resolve_channel_icon_url(
    settings: Any = None,
    *,
    tunarr_base: str = "",
    preferred_url: str = "",
) -> str:
    """LAN-facing icon URL for channel logos (Plex must be able to fetch it).

    Prefer ``preferred_url`` (collection / title art) when set. Do **not** fall
    back to Tunarr's stock ``/images/tunarr.png`` — empty path keeps Plex from
    showing default Tunarr marks when station art is missing.
    """
    _ = (settings, tunarr_base)  # signature kept for callers; stock Tunarr mark unused
    preferred = str(preferred_url or "").strip()
    if preferred and not is_default_tunarr_icon(preferred):
        return preferred
    return ""


def probe_icon_url(url: str, *, timeout: int = 5) -> Dict[str, Any]:
    """Best-effort GET of a channel icon URL (reachable from Projectionist)."""
    target = str(url or "").strip()
    if not target:
        return {"ok": False, "url": "", "message": "No icon URL configured."}
    try:
        from projectionist.connectors.http import request_empty

        request_empty(target, method="GET", timeout=timeout)
        return {"ok": True, "url": target, "message": "Icon URL reachable."}
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "url": target,
            "message": str(error)[:200] or "Icon probe failed.",
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
) -> None:
    """Persist station recipe fields on ``settings.tunarr.station_meta`` (in-memory).

    ``motif`` / ``cluster_tag`` / ``craft_filters``: ``None`` leaves the stored
    value unchanged; a provided value (including empty) replaces it.
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
    if craft_filters is not None:
        from projectionist.live_channels.filters import normalize_craft_filters

        row["craft_filters"] = normalize_craft_filters(craft_filters).to_dict()
    meta[cid] = row


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
        "youth_safe": bool(row.get("youth_safe")),
        "subtitles_enabled": (
            bool(row["subtitles_enabled"]) if "subtitles_enabled" in row else None
        ),
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
    from projectionist.live_channels.filters import normalize_craft_filters

    craft_filters = normalize_craft_filters(row.get("craft_filters")).to_dict()
    has_filters = not normalize_craft_filters(craft_filters).is_empty()
    # Decade/genre stations may only have craft_filters + media_scope persisted.
    if not source and not mode_raw and not collection_id and not has_filters:
        return None
    default_mode = (
        ProgrammingMode.SEQUENTIAL
        if source == "collection"
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


def _channel_put_body(
    ch: Mapping[str, Any],
    *,
    name: str = "",
    icon: Optional[Mapping[str, Any]] = None,
    start_time_ms: Optional[int] = None,
    subtitles_enabled: Optional[bool] = None,
) -> Dict[str, Any]:
    """Trimmed Tunarr ``PUT /channels/{id}`` body from a list/detail channel row."""
    cid = str(ch.get("id") or ch.get("uuid") or "").strip()
    number = int(ch.get("number") or 0)
    resolved_name = str(name or ch.get("name") or "").strip()
    if not resolved_name:
        resolved_name = f"Channel {number}" if number else "Station"
    current_icon = ch.get("icon") if isinstance(ch.get("icon"), Mapping) else {}
    if subtitles_enabled is None:
        subtitles_flag = bool(ch.get("subtitlesEnabled", False))
    else:
        subtitles_flag = bool(subtitles_enabled)
    body: Dict[str, Any] = {
        "id": cid,
        "name": resolved_name[:48],
        "number": number,
        "stealth": bool(ch.get("stealth", False)),
        "duration": int(ch.get("duration") or 0),
        "disableFillerOverlay": bool(ch.get("disableFillerOverlay", False)),
        "groupTitle": str(ch.get("groupTitle") or _DEFAULT_GROUP_TITLE),
        "guideMinimumDuration": int(
            ch.get("guideMinimumDuration") or _DEFAULT_GUIDE_MINIMUM_DURATION_MS
        ),
        "icon": dict(icon) if icon is not None else dict(current_icon or channel_icon_body("")),
        "offline": dict(ch.get("offline") or {"mode": "pic"}),
        "startTime": int(
            start_time_ms
            if start_time_ms is not None
            else (ch.get("startTime") or time.time() * 1000)
        ),
        "streamMode": str(ch.get("streamMode") or _DEFAULT_STREAM_MODE),
        "transcodeConfigId": str(ch.get("transcodeConfigId") or ""),
        "subtitlesEnabled": subtitles_flag,
    }
    if ch.get("fillerCollections") is not None:
        body["fillerCollections"] = list(ch.get("fillerCollections") or [])
    if ch.get("fillerRepeatCooldown") is not None:
        body["fillerRepeatCooldown"] = ch.get("fillerRepeatCooldown")
    if ch.get("guideFlexTitle") is not None:
        body["guideFlexTitle"] = ch.get("guideFlexTitle")
    return body


def ensure_channel_labels(
    client: TunarrClient,
    *,
    icon_url: str = "",
    channel_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Ensure Tunarr stations have a non-empty name + LAN icon for Plex guide labels."""
    wanted = {str(cid).strip() for cid in (channel_ids or ()) if str(cid).strip()}
    updated: List[str] = []
    errors: List[str] = []
    icon = channel_icon_body(icon_url)
    for ch in client.list_channels():
        if not isinstance(ch, Mapping):
            continue
        cid = str(ch.get("id") or ch.get("uuid") or "").strip()
        if not cid:
            continue
        if wanted and cid not in wanted:
            continue
        name = str(ch.get("name") or "").strip()
        number = int(ch.get("number") or 0)
        if not name:
            name = f"Channel {number}" if number else "Station"
        current_icon = ch.get("icon") if isinstance(ch.get("icon"), Mapping) else {}
        current_path = str(current_icon.get("path") or "").strip()
        # Upgrade empty / loopback / generic Tunarr mark when a better LAN path is known.
        generic_mark = current_path.endswith("/images/tunarr.png")
        better = bool(icon.get("path")) and icon.get("path") != current_path and not str(
            icon.get("path") or ""
        ).endswith("/images/tunarr.png")
        needs_icon = bool(icon.get("path")) and (
            not current_path
            or current_path.startswith("http://127.0.0.1")
            or current_path.startswith("http://localhost")
            or (generic_mark and better)
        )
        needs_name = not str(ch.get("name") or "").strip()
        if not needs_icon and not needs_name:
            continue
        body = _channel_put_body(
            ch,
            name=name,
            icon=dict(icon) if needs_icon else dict(current_icon or channel_icon_body("")),
        )
        if not body["transcodeConfigId"]:
            errors.append(f"{cid}: missing transcodeConfigId")
            continue
        try:
            client.update_channel(cid, body)
            updated.append(cid)
        except Exception as error:  # noqa: BLE001
            errors.append(f"{cid}: {str(error)[:120]}")
    return {
        "ok": not errors,
        "updated": updated,
        "count_updated": len(updated),
        "errors": errors,
        "icon_url": str(icon.get("path") or ""),
    }


def _sessions_by_channel(client: TunarrClient) -> Dict[str, Any]:
    try:
        raw = client.list_sessions()
    except Exception:  # noqa: BLE001
        return {}
    return dict(raw) if isinstance(raw, Mapping) else {}


def should_align_playhead(
    *,
    elapsed_ms: int,
    program_duration_ms: int = 0,
    has_session: bool = False,
    min_elapsed_ms: int = _ALIGN_MIN_ELAPSED_MS,
) -> bool:
    """True when a mid-program seek is likely to cold-fail Plex HDHR tunes."""
    elapsed = max(0, int(elapsed_ms or 0))
    duration = max(0, int(program_duration_ms or 0))
    if duration and elapsed > duration:
        return True  # past EOF — ffmpeg seek hangs / empty playlist
    if has_session:
        return False
    return elapsed >= max(0, int(min_elapsed_ms or 0))


def _now_playing_is_flex(playing: Mapping[str, Any]) -> bool:
    """True when Tunarr now_playing is a flex / continuity / offline pad."""
    kind = str(playing.get("type") or playing.get("programType") or "").strip().lower()
    if kind in {"flex", "filler", "continuity", "offline", "commercial"}:
        return True
    title = str(playing.get("title") or "").strip().lower()
    if title.endswith("· up next") or title.endswith("up next"):
        return True
    if title in {"flex", "filler", "continuity"}:
        return True
    return False


def snap_future_channel_start_time(
    client: TunarrClient,
    channel: Mapping[str, Any],
    *,
    now_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """Pull a future ``startTime`` back by whole cycle lengths (preserve playhead).

    When ``startTime`` is ahead of wall-clock, Tunarr synthesizes long flex /
    offline pads until the cycle begins — Continuity filler airs while the
    guide looks empty or misleading. Subtracting ``duration`` keeps the same
    offset into the lineup without wiping the schedule.
    """
    cid = str(channel.get("id") or channel.get("uuid") or "").strip()
    if not cid:
        return {"ok": False, "snapped": False, "error": "channel_id required"}
    ts = int(now_ms if now_ms is not None else time.time() * 1000)
    try:
        start = int(channel.get("startTime") or 0)
    except (TypeError, ValueError):
        start = 0
    try:
        duration = int(channel.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    if start <= ts:
        return {
            "ok": True,
            "snapped": False,
            "channel_id": cid,
            "reason": "already_live",
            "start_time_ms": start,
        }
    if duration <= 0:
        new_start = ts - 60_000
    else:
        new_start = start
        # Bound iterations — pathological durations must not spin.
        for _ in range(10_000):
            if new_start <= ts:
                break
            new_start -= duration
        if new_start > ts:
            new_start = ts - (start - ts) % duration
    body = _channel_put_body(channel, start_time_ms=int(new_start))
    if not body["transcodeConfigId"]:
        return {
            "ok": False,
            "snapped": False,
            "channel_id": cid,
            "error": "missing transcodeConfigId",
        }
    try:
        client.update_channel(cid, body)
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "snapped": False,
            "channel_id": cid,
            "error": str(error)[:200],
        }
    return {
        "ok": True,
        "snapped": True,
        "channel_id": cid,
        "start_time_ms": int(new_start),
        "previous_start_time_ms": start,
        "message": "Snapped future startTime back into the live window.",
    }


def align_channel_playhead_to_program_start(
    client: TunarrClient,
    channel: Mapping[str, Any],
    *,
    has_session: bool = False,
    min_elapsed_ms: int = _ALIGN_MIN_ELAPSED_MS,
    force: bool = False,
) -> Dict[str, Any]:
    """Shift channel ``startTime`` so 'now' is the start of the current program.

    Deep ``-ss`` seeks (or seeks past file EOF) delay HLS readiness past Plex's
    patience. Start-over keeps cold tunes near ``-ss 0``.

    Never start-over on flex/continuity pads — adding flex elapsed to
    ``startTime`` pushes the cycle into the future (Gilligan / Kung Fu drift).
    """
    cid = str(channel.get("id") or channel.get("uuid") or "").strip()
    if not cid:
        return {"ok": False, "aligned": False, "error": "channel_id required"}
    now_ms = int(time.time() * 1000)
    # Repair drifted schedules before consulting now_playing (which is often a
    # synthetic flex window while startTime is still in the future).
    snap = snap_future_channel_start_time(client, channel, now_ms=now_ms)
    if snap.get("snapped"):
        channel = {**dict(channel), "startTime": snap.get("start_time_ms")}
    try:
        playing = client.get_now_playing(cid) or {}
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "aligned": False,
            "channel_id": cid,
            "error": str(error)[:200],
            "snap": snap,
        }
    if not isinstance(playing, Mapping):
        return {
            "ok": True,
            "aligned": bool(snap.get("snapped")),
            "channel_id": cid,
            "reason": "no_now_playing",
            "snap": snap,
        }
    if _now_playing_is_flex(playing) and not force:
        return {
            "ok": True,
            "aligned": bool(snap.get("snapped")),
            "channel_id": cid,
            "reason": "flex_skip",
            "title": str(playing.get("title") or "").strip(),
            "snap": snap,
            "message": snap.get("message") or "Skipped start-over during flex/continuity.",
        }
    prog_start = int(playing.get("start") or 0)
    prog_duration = int(playing.get("duration") or 0)
    title = ""
    program = playing.get("program")
    if isinstance(program, Mapping):
        title = str(program.get("title") or "").strip()
    if not title:
        title = str(playing.get("title") or "").strip()
    elapsed = max(0, now_ms - prog_start) if prog_start else 0
    if not force and not should_align_playhead(
        elapsed_ms=elapsed,
        program_duration_ms=prog_duration,
        has_session=has_session,
        min_elapsed_ms=min_elapsed_ms,
    ):
        return {
            "ok": True,
            "aligned": bool(snap.get("snapped")),
            "channel_id": cid,
            "elapsed_ms": elapsed,
            "title": title,
            "reason": "near_start_or_active",
            "snap": snap,
        }
    channel_start = int(channel.get("startTime") or now_ms)
    new_start = channel_start + elapsed
    # Never push the cycle into the future — that recreates pre-start flex.
    if new_start > now_ms:
        new_start = now_ms
    body = _channel_put_body(channel, start_time_ms=new_start)
    if not body["transcodeConfigId"]:
        return {
            "ok": False,
            "aligned": False,
            "channel_id": cid,
            "error": "missing transcodeConfigId",
        }
    try:
        client.update_channel(cid, body)
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "aligned": False,
            "channel_id": cid,
            "error": str(error)[:200],
        }
    return {
        "ok": True,
        "aligned": True,
        "channel_id": cid,
        "elapsed_ms": elapsed,
        "title": title,
        "start_time_ms": new_start,
        "snap": snap,
        "message": f"Start-over: was {elapsed // 60000}m into {title or 'program'}.",
    }


def warm_channel_stream(
    client: TunarrClient,
    channel_id: str,
    *,
    timeout: int = _WARM_DEFAULT_TIMEOUT_S,
    min_ts_bytes: int = _WARM_MIN_TS_BYTES,
    pull_ts: bool = True,
) -> Dict[str, Any]:
    """Warm HLS until the media playlist has segments, optionally pull MPEG-TS.

    A single GET of the master ``.m3u8`` is not enough — Tunarr often returns the
    master before ``playlist.m3u8`` / segments exist. Plex HDHR uses ``.ts``.

    Background keepalive should pass ``pull_ts=False``: opening ``.ts`` on every
    channel every few minutes keeps six ffmpeg pipelines hot (2000%+ CPU) and
    SIGKILLs mid-watch sessions when they contend for resources.
    """
    from projectionist.circuit_breaker import CircuitOpenError, is_host_circuit_open
    from projectionist.connectors.http import request_bytes

    cid = str(channel_id or "").strip()
    if not cid:
        return {"ok": False, "error": "channel_id required"}
    base = client.base_url.rstrip("/")
    master_url = f"{base}/stream/channels/{cid}.m3u8?mode=hls"
    media_url = f"{base}/stream/channels/{cid}/hls/stream.m3u8"
    ts_url = f"{base}/stream/channels/{cid}.ts"
    deadline = time.time() + max(8, int(timeout or _WARM_DEFAULT_TIMEOUT_S))
    playlist_ready = False
    last_error = ""
    poll_count = 0
    hard_fail = False
    while time.time() < deadline and not hard_fail:
        poll_count += 1
        for url in (media_url, master_url):
            try:
                body = request_bytes(url, timeout=8, max_bytes=8192).decode("utf-8", "replace")
                if "#EXTINF" in body:
                    playlist_ready = True
                    break
                if body.strip():
                    last_error = "playlist returned without segments yet"
            except CircuitOpenError as error:
                last_error = str(error)[:160]
                hard_fail = True
                break
            except Exception as error:  # noqa: BLE001
                last_error = str(error)[:160]
                # Connection refused / DNS / invalid URL — do not burn the full timeout.
                err_l = last_error.lower()
                if any(
                    token in err_l
                    for token in (
                        "connection refused",
                        "nodename nor servname",
                        "name or service not known",
                        "timed out",
                        "unreachable",
                        "invalid url",
                        "unknown url type",
                        "circuit open",
                    )
                ) or is_host_circuit_open(url):
                    hard_fail = True
                    break
        if playlist_ready or hard_fail:
            break
        time.sleep(_WARM_POLL_SLEEP_S)

    ts_bytes = 0
    ts_error = ""
    if pull_ts:
        try:
            ts_bytes = len(
                request_bytes(
                    ts_url,
                    timeout=max(10, int(timeout or _WARM_DEFAULT_TIMEOUT_S)),
                    max_bytes=max(int(min_ts_bytes or 0), _WARM_MIN_TS_BYTES),
                )
            )
        except Exception as error:  # noqa: BLE001
            ts_error = str(error)[:200]

    if pull_ts:
        ok = playlist_ready or ts_bytes >= max(
            1, int(min_ts_bytes or _WARM_MIN_TS_BYTES) // 4
        )
        message = (
            "Stream warmed (playlist + MPEG-TS)."
            if ok
            else "Warm-up incomplete — first Plex tune may still race cold start."
        )
    else:
        ok = playlist_ready
        message = (
            "Playlist keepalive ok."
            if ok
            else "Playlist keepalive incomplete — stream may still be cold."
        )
    return {
        "ok": ok,
        "channel_id": cid,
        "playlist_ready": playlist_ready,
        "ts_bytes": ts_bytes,
        "pull_ts": bool(pull_ts),
        "polls": poll_count,
        "error": "" if ok else (ts_error or last_error or "stream not ready"),
        "message": message,
    }


def apply_station_icons(
    client: TunarrClient,
    settings: Any = None,
    *,
    channel_ids: Optional[Sequence[str]] = None,
    fallback_icon: str = "",
) -> Dict[str, Any]:
    """Prefer per-station art; clear stock Tunarr marks when art is missing."""
    wanted = {str(cid).strip() for cid in (channel_ids or ()) if str(cid).strip()}
    fallback = str(fallback_icon or "").strip()
    if is_default_tunarr_icon(fallback):
        fallback = ""
    meta = {}
    if settings is not None:
        tunarr = getattr(settings, "tunarr", None)
        meta = dict(getattr(tunarr, "station_meta", None) or {})
    updated: List[str] = []
    errors: List[str] = []
    cleared = 0
    for ch in client.list_channels():
        if not isinstance(ch, Mapping):
            continue
        cid = str(ch.get("id") or ch.get("uuid") or "").strip()
        if not cid or (wanted and cid not in wanted):
            continue
        row = meta.get(cid) if isinstance(meta.get(cid), Mapping) else {}
        preferred = str((row or {}).get("icon_url") or "").strip()
        collection_id = str((row or {}).get("collection_id") or "").strip()
        if not preferred and collection_id:
            preferred = resolve_collection_icon_url(settings, collection_id)
        if is_default_tunarr_icon(preferred):
            preferred = ""
        target = preferred or fallback
        current = ch.get("icon") if isinstance(ch.get("icon"), Mapping) else {}
        current_path = str((current or {}).get("path") or "").strip()
        # Strip residual Tunarr stock marks when we have no real art.
        if not target and is_default_tunarr_icon(current_path) and current_path:
            target = ""
            clear_stock = True
        else:
            clear_stock = False
        if not target and not clear_stock:
            continue
        if current_path == target:
            continue
        # Don't overwrite a non-generic custom icon with empty/stock.
        if (
            not target
            and current_path
            and not is_default_tunarr_icon(current_path)
            and not current_path.startswith("http://127.0.0.1")
            and not current_path.startswith("http://localhost")
        ):
            continue
        body = _channel_put_body(
            ch,
            name=str(ch.get("name") or "").strip(),
            icon=channel_icon_body(target),
        )
        if not body.get("transcodeConfigId"):
            errors.append(f"{cid}: missing transcodeConfigId")
            continue
        try:
            client.update_channel(cid, body)
            updated.append(cid)
            if clear_stock or not target:
                cleared += 1
        except Exception as error:  # noqa: BLE001
            errors.append(f"{cid}: {str(error)[:120]}")
    return {
        "ok": not errors,
        "updated": updated,
        "count_updated": len(updated),
        "count_cleared_stock": cleared,
        "errors": errors,
    }


def prepare_channels_for_playback(
    client: TunarrClient,
    *,
    settings: Any = None,
    channel_ids: Optional[Sequence[str]] = None,
    icon_url: str = "",
    align_playhead: bool = True,
    warm_streams: bool = True,
    min_elapsed_ms: int = _ALIGN_MIN_ELAPSED_MS,
    skip_active_sessions: bool = False,
    max_warm_channels: Optional[int] = None,
    pull_ts: bool = True,
) -> Dict[str, Any]:
    """Labels + start-over (when deep/cold) + HLS warm for playback.

    ``skip_active_sessions`` / ``max_warm_channels`` / ``pull_ts=False`` are for
    the background keepalive scheduler — never thrash channels that already have
    viewers, and never keep every station's ffmpeg pipeline hot at once.
    """
    wanted = {str(cid).strip() for cid in (channel_ids or ()) if str(cid).strip()}
    resolved_icon = str(icon_url or "").strip() or resolve_channel_icon_url(settings)
    labels = ensure_channel_labels(
        client, icon_url=resolved_icon, channel_ids=list(wanted) if wanted else None
    )
    try:
        station_icons = apply_station_icons(
            client,
            settings,
            channel_ids=list(wanted) if wanted else None,
            fallback_icon=resolved_icon,
        )
        if station_icons.get("count_updated"):
            labels = {
                **labels,
                "count_updated": int(labels.get("count_updated") or 0)
                + int(station_icons.get("count_updated") or 0),
                "station_icons": station_icons,
            }
    except Exception:  # noqa: BLE001
        pass
    sessions = _sessions_by_channel(client)
    channels = [ch for ch in client.list_channels() if isinstance(ch, Mapping)]
    if wanted:
        channels = [
            ch
            for ch in channels
            if str(ch.get("id") or ch.get("uuid") or "").strip() in wanted
        ]

    aligned: List[Dict[str, Any]] = []
    snapped: List[Dict[str, Any]] = []
    skipped_active = 0
    # Always pull future startTimes back (preserves lineup offset). Safe on
    # channel-surf / background warm — unlike content start-over, which was
    # drifting schedules into flex/Continuity after leave→rejoin.
    repaired_channels: List[Mapping[str, Any]] = []
    for ch in channels:
        cid = str(ch.get("id") or ch.get("uuid") or "").strip()
        if not cid:
            repaired_channels.append(ch)
            continue
        snap = snap_future_channel_start_time(client, ch)
        snapped.append(snap)
        if snap.get("snapped"):
            repaired_channels.append(
                {**dict(ch), "startTime": snap.get("start_time_ms")}
            )
            # Drop stale HLS so warm rebuilds against the repaired schedule
            # instead of keeping a Continuity/flex session under the guide.
            try:
                client.stop_channel_sessions(cid)
            except Exception:  # noqa: BLE001
                pass
            sessions.pop(cid, None)
        else:
            repaired_channels.append(ch)
    channels = repaired_channels

    if align_playhead:
        for ch in channels:
            cid = str(ch.get("id") or ch.get("uuid") or "").strip()
            has_session = bool(sessions.get(cid))
            if skip_active_sessions and has_session:
                skipped_active += 1
                aligned.append(
                    {
                        "ok": True,
                        "aligned": False,
                        "channel_id": cid,
                        "reason": "active_session",
                    }
                )
                continue
            result = align_channel_playhead_to_program_start(
                client,
                ch,
                has_session=has_session,
                min_elapsed_ms=min_elapsed_ms,
            )
            aligned.append(result)
    else:
        # Live-edge tune/warm: still unstick past-EOF playheads (ffmpeg -ss past
        # file end → offline/Continuity while guide keeps the episode title).
        for ch in channels:
            cid = str(ch.get("id") or ch.get("uuid") or "").strip()
            if not cid:
                continue
            try:
                playing = client.get_now_playing(cid) or {}
            except Exception:  # noqa: BLE001
                continue
            if not isinstance(playing, Mapping) or _now_playing_is_flex(playing):
                continue
            try:
                prog_start = int(playing.get("start") or 0)
                prog_duration = int(playing.get("duration") or 0)
                prog_stop = int(playing.get("stop") or 0)
            except (TypeError, ValueError):
                continue
            if not prog_start or not prog_duration:
                continue
            now_ms = int(time.time() * 1000)
            elapsed = max(0, now_ms - prog_start)
            if elapsed <= prog_duration:
                continue
            file_end = prog_start + prog_duration
            overflow = elapsed - prog_duration
            # Tunarr often pads ``stop`` past file EOF while the engine has already
            # rolled into the next lineup item. Shifting startTime by overflow then
            # pulls the playhead BACK into the dead zone and SIGKILLs a healthy
            # next-title transcode (Kung Fu: Samurai → Five Fingers).
            if prog_stop and prog_stop > file_end + 2_000:
                aligned.append(
                    {
                        "ok": True,
                        "aligned": False,
                        "channel_id": cid,
                        "reason": "past_eof_padded_stop_skip",
                        "overflow_ms": overflow,
                        "message": (
                            "now_playing past file EOF with padded stop; "
                            "skip startTime shift to preserve live edge."
                        ),
                    }
                )
                continue
            try:
                channel_start = int(ch.get("startTime") or now_ms)
            except (TypeError, ValueError):
                channel_start = now_ms
            # Advance the cycle just past the ended program into the next item
            # (do not restart the finished episode via classic start-over).
            # Decreasing effective playhead offset by (overflow - 1s) lands ~1s
            # after file end: new_start = channel_start + overflow - 1_000.
            new_start = channel_start + overflow - 1_000
            if new_start > now_ms:
                new_start = now_ms
            body = _channel_put_body(ch, start_time_ms=int(new_start))
            if not body.get("transcodeConfigId"):
                continue
            try:
                client.update_channel(cid, body)
                client.stop_channel_sessions(cid)
            except Exception as error:  # noqa: BLE001
                aligned.append(
                    {
                        "ok": False,
                        "aligned": False,
                        "channel_id": cid,
                        "reason": "past_eof_advance_failed",
                        "error": str(error)[:200],
                    }
                )
                continue
            sessions.pop(cid, None)
            aligned.append(
                {
                    "ok": True,
                    "aligned": True,
                    "channel_id": cid,
                    "reason": "past_eof_advance",
                    "overflow_ms": overflow,
                    "start_time_ms": int(new_start),
                    "message": "Advanced past ended program into the next lineup item.",
                }
            )

    warmed: List[Dict[str, Any]] = []
    if warm_streams:
        warm_budget = max_warm_channels
        if warm_budget is not None:
            try:
                warm_budget = max(0, int(warm_budget))
            except (TypeError, ValueError):
                warm_budget = None
        for ch in channels:
            cid = str(ch.get("id") or ch.get("uuid") or "").strip()
            if not cid:
                continue
            if skip_active_sessions and sessions.get(cid):
                warmed.append(
                    {
                        "ok": True,
                        "channel_id": cid,
                        "skipped": True,
                        "reason": "active_session",
                        "message": "Skipped warm — session already active.",
                    }
                )
                continue
            if warm_budget is not None and warm_budget <= 0:
                warmed.append(
                    {
                        "ok": True,
                        "channel_id": cid,
                        "skipped": True,
                        "reason": "warm_budget",
                        "message": "Skipped warm — background budget exhausted.",
                    }
                )
                continue
            result = warm_channel_stream(client, cid, pull_ts=pull_ts)
            warmed.append(result)
            if warm_budget is not None and not result.get("skipped"):
                warm_budget -= 1

    aligned_count = sum(1 for row in aligned if row.get("aligned"))
    snapped_count = sum(1 for row in snapped if row.get("snapped"))
    warmed_attempted = [row for row in warmed if not row.get("skipped")]
    warmed_ok = sum(1 for row in warmed_attempted if row.get("ok"))
    return {
        "ok": (not labels.get("errors"))
        and (warmed_ok == len(warmed_attempted) if warmed_attempted else True),
        "labels": labels,
        "aligned": aligned,
        "snapped": snapped,
        "count_aligned": aligned_count,
        "count_snapped": snapped_count,
        "warmed": warmed,
        "count_warmed_ok": warmed_ok,
        "count_warmed_skipped": sum(1 for row in warmed if row.get("skipped")),
        "count_skipped_active": skipped_active,
        "count_channels": len(channels),
        "icon_url": resolved_icon,
        "message": (
            f"Prepared {len(channels)} station(s): "
            f"{snapped_count} snapped, {aligned_count} start-over, "
            f"{warmed_ok}/{len(warmed_attempted) or 0} warmed"
            + (
                f", {sum(1 for row in warmed if row.get('skipped'))} skipped."
                if any(row.get("skipped") for row in warmed)
                else "."
            )
        ),
    }


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


def resolve_collection_icon_url(
    settings: Any,
    collection_id: str,
    *,
    children: Optional[Sequence[Mapping[str, Any]]] = None,
) -> str:
    """Prefer collection art, then first child thumb, else empty (caller uses Tunarr mark)."""
    cid = str(collection_id or "").strip()
    plex_url = str(getattr(settings, "plex_url", "") or "").strip() if settings else ""
    plex_token = str(getattr(settings, "plex_token", "") or "").strip() if settings else ""
    if cid and cid.isdigit() and plex_url and plex_token:
        try:
            from projectionist.connectors.plex import PlexClient
            from projectionist.connectors.plex_collections import collection_art_url

            art = collection_art_url(PlexClient(plex_url, plex_token, timeout=10), cid)
            if art:
                return art
        except Exception:  # noqa: BLE001
            pass
    for row in children or ():
        thumb = str(row.get("thumb") or "").strip()
        if not thumb:
            continue
        if thumb.startswith("http://") or thumb.startswith("https://"):
            return thumb
        if plex_url and plex_token:
            from projectionist.connectors.plex_collections import _auth_url
            from projectionist.connectors.plex import PlexClient

            path = thumb if thumb.startswith("/") else f"/{thumb}"
            try:
                return _auth_url(PlexClient(plex_url, plex_token, timeout=5), path)
            except Exception:  # noqa: BLE001
                continue
    return ""


def _extract_plex_rating_keys(item: Mapping[str, Any]) -> List[str]:
    """Collect Plex ratingKey forms from a Tunarr library-program / program row."""
    prog = item.get("program") if isinstance(item.get("program"), Mapping) else item
    if not isinstance(prog, Mapping):
        prog = item
    keys: List[str] = []
    for raw in (
        prog.get("externalKey"),
        item.get("externalKey"),
        prog.get("plexRatingKey"),
        item.get("plexRatingKey"),
        prog.get("ratingKey"),
        item.get("ratingKey"),
    ):
        text = str(raw or "").strip()
        if not text:
            continue
        keys.append(text)
        # Tunarr often stores ``plex|{sourceId}|{ratingKey}``.
        if "|" in text:
            tail = text.rsplit("|", 1)[-1].strip()
            if tail and tail not in keys:
                keys.append(tail)
        # Bare digit also matches ``plex|*|{key}`` tails.
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

    Movie-heavy pools get a movie slot; TV episodes get per-show slots (capped).
    Residual: Tunarr has no generic “shuffle this UUID list” slot — show slots
    need ``showId``. When neither movies nor showIds resolve, callers fall back
    to a shuffled manual lineup.
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
    Shuffle prefers ``type=random`` (RandomSlotSchedule) for continuous
    reshuffle within the resolved pool when Tunarr can schedule the pool;
    otherwise fall back to a shuffled manual lineup.
    When ``pad_lineups`` is true, insert flex (≤ ``max_flex_ms``) toward :00/:30
    on manual lineups (``padMs`` on random schedules).
    """
    from projectionist.live_channels.filler import pad_lineup_with_flex

    content_lineup: List[Dict[str, Any]] = []
    program_ids: List[str] = []
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
        program_ids.append(pid)

    mode = normalize_programming_mode(recipe.programming_mode)
    use_random = mode == ProgrammingMode.SHUFFLE and program_ids
    if use_random:
        schedule = random_slot_schedule_for_programs(
            programs or (),
            max_flex_ms=max_flex_ms if pad_lineups else 0,
            programming_mode=mode,
        )
        if schedule:
            return {
                "type": "random",
                "programs": program_ids,
                "schedule": schedule,
            }

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
                "Could not resolve a Tunarr transcode profile; channels were not published."
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
    settings: Any = None,
) -> Dict[str, Any]:
    """Create a station from a Plex/Projectionist collection (seq / shuffle)."""
    from projectionist.live_channels.filters import normalize_craft_filters

    title = str(collection_title or name or "Collection").strip() or "Collection"
    number = int(channel_number or 0)
    if number <= 0:
        from projectionist.live_channels.craft import next_channel_number

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
        base = 100
        if settings is not None:
            tunarr = getattr(settings, "tunarr", None)
            try:
                base = int(getattr(tunarr, "channel_number_base", 100) or 100)
            except (TypeError, ValueError):
                base = 100
        number = next_channel_number(numbers, base=base, occupied=occupied)
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


def tunarr_client_from_settings(settings: Any) -> TunarrClient:
    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    if not url:
        raise ValueError("Tunarr URL is not configured")
    return TunarrClient(url)
