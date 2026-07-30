"""Publish starter recipes / collections to Tunarr via OpenAPI."""

from __future__ import annotations

import random
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from projectionist.connectors.tunarr import TunarrClient
from projectionist.live_channels.recipes import (
    ChannelRecipe,
    ProgrammingMode,
    recipe_from_mapping,
)

# Prefer these Plex library mediaTypes when enabling Tunarr libraries for fill.
_PREFERRED_LIBRARY_TYPES = frozenset({"movies", "shows"})
_MIN_PROGRAM_DURATION_MS = 60_000
_DEFAULT_FILL_LIMIT = 30

# Tunarr 1.3.x ``createChannelV2`` requires these channel fields (OpenAPI).
_DEFAULT_GROUP_TITLE = "Projectionist"
_DEFAULT_GUIDE_MINIMUM_DURATION_MS = 30_000
_DEFAULT_STREAM_MODE = "hls"


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


def wire_plex_media_source(
    client: TunarrClient,
    *,
    plex_url: str,
    plex_token: str,
    name: str = "Plex",
    user_id: Optional[str] = None,
    username: Optional[str] = None,
) -> Dict[str, Any]:
    """Ensure a Plex media source exists in Tunarr (idempotent best-effort)."""
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
                ensure_media_libraries_enabled(client, media_source_id=msid)
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
        ensure_media_libraries_enabled(client, media_source_id=msid)
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
) -> Dict[str, Any]:
    """Enable preferred Plex libraries in Tunarr and kick scans.

    Tunarr wires a Plex source with libraries ``enabled: false`` by default —
    channels then stay empty (flex-only guide, playback ends immediately).
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
            "message": "No Plex media source in Tunarr yet.",
        }

    wanted = {str(t).lower() for t in media_types} or set(_PREFERRED_LIBRARY_TYPES)
    enabled: List[Dict[str, Any]] = []
    scanned: List[Dict[str, Any]] = []
    errors: List[str] = []
    try:
        libraries = client.list_media_source_libraries(msid)
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "media_source_id": msid,
            "enabled": [],
            "scanned": [],
            "message": f"Could not list Tunarr libraries: {error}"[:240],
        }

    for lib in libraries:
        media_type = str(lib.get("mediaType") or lib.get("type") or "").lower()
        if media_type not in wanted:
            continue
        lid = str(lib.get("id") or "").strip()
        if not lid:
            continue
        name = str(lib.get("name") or lid)
        try:
            if not bool(lib.get("enabled")):
                client.set_library_enabled(msid, lid, enabled=True)
            enabled.append(
                {
                    "id": lid,
                    "name": name,
                    "media_type": media_type,
                }
            )
            if scan:
                client.scan_library(msid, lid, force=True)
                scanned.append({"id": lid, "name": name})
        except Exception as error:  # noqa: BLE001
            errors.append(f"{name}: {error}"[:160])

    return {
        "ok": bool(enabled) and not errors,
        "media_source_id": msid,
        "enabled": enabled,
        "scanned": scanned,
        "errors": errors,
        "message": (
            f"Enabled {len(enabled)} library(ies)"
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


def resolve_channel_icon_url(settings: Any = None, *, tunarr_base: str = "") -> str:
    """LAN-facing Tunarr logo URL for channel icons (Plex can fetch it)."""
    base = str(tunarr_base or "").strip().rstrip("/")
    if not base and settings is not None:
        try:
            from projectionist.live_channels.plex_attach import (
                resolve_plex_facing_tunarr_base,
            )

            facing = resolve_plex_facing_tunarr_base(settings)
            base = str(facing.get("base_url") or "").strip().rstrip("/")
        except Exception:  # noqa: BLE001
            base = ""
        if not base:
            tunarr = getattr(settings, "tunarr", None)
            base = str(getattr(tunarr, "public_url", "") or "").strip().rstrip("/")
    if not base:
        return ""
    return f"{base}/images/tunarr.png"


def channel_create_body(
    recipe: ChannelRecipe,
    *,
    transcode_config_id: str,
    channel_id: Optional[str] = None,
    start_time_ms: Optional[int] = None,
    group_title: str = _DEFAULT_GROUP_TITLE,
    icon_url: str = "",
) -> Dict[str, Any]:
    """Tunarr ``POST /api/channels`` body for ``createChannelV2``.

    Tunarr 1.3.x rejects sparse bodies (HTTP 400). Required fields come from the
    live OpenAPI ``oneOf`` ``type=new`` branch — including a client-generated
    channel UUID and an existing ``transcodeConfigId``.
    """
    tcid = str(transcode_config_id or "").strip()
    if not tcid:
        raise ValueError("transcode_config_id is required to create a Tunarr channel")
    name = str(recipe.name or "").strip() or f"Channel {int(recipe.number)}"
    return {
        "type": "new",
        "channel": {
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
            "subtitlesEnabled": False,
        },
    }


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
        needs_icon = bool(icon.get("path")) and (
            not current_path
            or current_path.startswith("http://127.0.0.1")
            or current_path.startswith("http://localhost")
        )
        needs_name = not str(ch.get("name") or "").strip()
        if not needs_icon and not needs_name:
            continue
        # Prefer a trimmed body — list payloads include sessions/programCount.
        body: Dict[str, Any] = {
            "id": cid,
            "name": name[:48],
            "number": number,
            "stealth": bool(ch.get("stealth", False)),
            "duration": int(ch.get("duration") or 0),
            "disableFillerOverlay": bool(ch.get("disableFillerOverlay", False)),
            "groupTitle": str(ch.get("groupTitle") or _DEFAULT_GROUP_TITLE),
            "guideMinimumDuration": int(
                ch.get("guideMinimumDuration") or _DEFAULT_GUIDE_MINIMUM_DURATION_MS
            ),
            "icon": dict(icon) if needs_icon else dict(current_icon or channel_icon_body("")),
            "offline": dict(ch.get("offline") or {"mode": "pic"}),
            "startTime": int(ch.get("startTime") or time.time() * 1000),
            "streamMode": str(ch.get("streamMode") or _DEFAULT_STREAM_MODE),
            "transcodeConfigId": str(ch.get("transcodeConfigId") or ""),
            "subtitlesEnabled": bool(ch.get("subtitlesEnabled", False)),
        }
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


def warm_channel_stream(
    client: TunarrClient,
    channel_id: str,
    *,
    timeout: int = 12,
) -> Dict[str, Any]:
    """Best-effort HLS warm-up so the first Plex tune is less likely to race cold start."""
    from urllib.request import Request, urlopen

    cid = str(channel_id or "").strip()
    if not cid:
        return {"ok": False, "error": "channel_id required"}
    url = f"{client.base_url.rstrip('/')}/stream/channels/{cid}.m3u8?mode=hls"
    try:
        request = Request(url, method="GET")
        with urlopen(request, timeout=max(3, int(timeout or 12))) as response:
            body = response.read(4096)
        return {
            "ok": bool(body),
            "channel_id": cid,
            "bytes": len(body or b""),
            "message": "Stream playlist warmed.",
        }
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "channel_id": cid,
            "error": str(error)[:200],
            "message": "Warm-up skipped (tune may still work after a short wait).",
        }


def plex_collection_item_hints(
    settings: Any,
    collection_id: str,
    *,
    limit: int = 60,
) -> List[str]:
    """Title hints from a Plex collection rating key (empty when not a Plex id)."""
    cid = str(collection_id or "").strip()
    if not cid or not cid.isdigit():
        return []
    plex_url = str(getattr(settings, "plex_url", "") or "").strip()
    plex_token = str(getattr(settings, "plex_token", "") or "").strip()
    if not plex_url or not plex_token:
        return []
    try:
        from projectionist.connectors.plex import PlexClient
        from projectionist.connectors.plex_collections import list_collection_item_titles

        return list_collection_item_titles(
            PlexClient(plex_url, plex_token, timeout=20),
            cid,
            limit=limit,
        )
    except Exception:  # noqa: BLE001
        return []


def programming_body_for_recipe(
    recipe: ChannelRecipe,
    *,
    programs: Optional[Sequence[Mapping[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """Best-effort programming payload for ``POST …/programming``.

    Tunarr 1.3.x manual updates require ``lineup`` (array), not ``programs``.
    Prefer real ``content`` rows (Tunarr program UUIDs + duration). Fall back to
    flex/empty shells so create+set still succeed before a media-source scan.
    """
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
        return {"type": "manual", "lineup": content_lineup}

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
    # Genre-ish aliases for common starter names when hints are thin.
    name_l = recipe.name.strip().lower()
    aliases = {
        "mystery": ("mystery", "thriller", "crime", "detective"),
        "sci-fi": ("sci-fi", "science fiction", "alien", "space"),
        "scifi": ("sci-fi", "science fiction", "alien", "space"),
    }
    for key, words in aliases.items():
        if key in name_l.replace(" ", "").replace("-", "") or key in name_l:
            for word in words:
                if word.lower() not in {t.lower() for t in terms}:
                    terms.append(word)
    return terms


def _normalize_program_row(item: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
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
    title = str(prog.get("title") or item.get("title") or "").strip()
    genres = prog.get("genres") or prog.get("tags") or []
    if not isinstance(genres, list):
        genres = []
    return {
        "id": pid,
        "duration": duration,
        "title": title,
        "genres": [str(g) for g in genres if str(g).strip()],
    }


def collect_programs_for_recipe(
    client: TunarrClient,
    recipe: ChannelRecipe,
    *,
    limit: int = _DEFAULT_FILL_LIMIT,
    catalog: Optional[Sequence[Mapping[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Pick Tunarr program IDs for a recipe from an indexed catalog / search."""
    target = max(1, min(int(limit or _DEFAULT_FILL_LIMIT), 80))
    pool: List[Dict[str, Any]] = []
    seen: set[str] = set()

    def _add(row: Optional[Mapping[str, Any]]) -> None:
        if not row:
            return
        normalized = _normalize_program_row(row) if "duration" in row or "program" in row else None
        if normalized is None and row.get("id") and row.get("duration"):
            try:
                duration = int(row["duration"])
            except (TypeError, ValueError):
                return
            if duration < _MIN_PROGRAM_DURATION_MS:
                return
            normalized = {
                "id": str(row["id"]),
                "duration": duration,
                "title": str(row.get("title") or ""),
                "genres": list(row.get("genres") or []),
            }
        if not normalized or normalized["id"] in seen:
            return
        seen.add(normalized["id"])
        pool.append(normalized)

    for item in catalog or ():
        if isinstance(item, Mapping):
            _add(item)

    if not pool:
        # Pull from first enabled movie/show library when no shared catalog.
        try:
            libraries_state = ensure_media_libraries_enabled(client, scan=False)
            msid = str(libraries_state.get("media_source_id") or "")
            for lib in libraries_state.get("enabled") or []:
                lid = str(lib.get("id") or "")
                if not lid:
                    continue
                for item in client.list_library_programs(lid):
                    _add(item)
                if msid:
                    break
        except Exception:  # noqa: BLE001
            pass

    terms = _recipe_search_terms(recipe)
    chaos = recipe.source == "chaos" or recipe.programming_mode == ProgrammingMode.CHAOS
    sequential_collection = (
        recipe.source == "collection"
        or recipe.programming_mode == ProgrammingMode.SEQUENTIAL
    ) and bool(recipe.item_hints)

    if chaos:
        candidates = list(pool)
        random.shuffle(candidates)
        return candidates[:target]

    # Collection path: preserve item_hint order with exact/near-exact title matches.
    if sequential_collection:
        by_title = {
            str(item.get("title") or "").strip().casefold(): item
            for item in pool
            if str(item.get("title") or "").strip()
        }
        ordered: List[Dict[str, Any]] = []
        seen_ids: set[str] = set()
        for hint in recipe.item_hints:
            wanted = str(hint or "").strip()
            if not wanted:
                continue
            match = by_title.get(wanted.casefold())
            if match is None:
                # Soft match: title contains hint or hint contains title.
                want_l = wanted.casefold()
                for title_l, item in by_title.items():
                    if want_l in title_l or title_l in want_l:
                        match = item
                        break
            if match is None:
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
            if len(ordered) >= target:
                break
        if ordered:
            if len(ordered) < min(8, target) and pool:
                extras = [p for p in pool if p["id"] not in seen_ids]
                random.shuffle(extras)
                ordered.extend(extras[: max(0, target - len(ordered))])
            return ordered[:target]

    scored: List[Tuple[int, Dict[str, Any]]] = []
    term_l = [t.lower() for t in terms]
    for item in pool:
        blob = " ".join(
            [item.get("title") or "", " ".join(item.get("genres") or [])]
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
                        }
                    )
            # Rebuild picks after search supplements.
            scored = []
            for item in pool:
                blob = " ".join(
                    [item.get("title") or "", " ".join(item.get("genres") or [])]
                ).lower()
                score = sum(1 for t in term_l if t and t in blob)
                if score:
                    scored.append((score, item))
            scored.sort(key=lambda pair: (-pair[0], pair[1].get("title") or ""))
            picked = [item for _, item in scored[:target]]
            if len(picked) >= target:
                break

    if len(picked) < 8 and pool:
        # Honest fallback: fill with random catalog titles so the station streams.
        extras = [p for p in pool if p["id"] not in {x["id"] for x in picked}]
        random.shuffle(extras)
        picked.extend(extras[: max(0, target - len(picked))])
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
    libraries = ensure_media_libraries_enabled(client, scan=True)
    resolved_icon = str(icon_url or "").strip() or resolve_channel_icon_url(settings)

    catalog: List[Mapping[str, Any]] = []
    msid = str(libraries.get("media_source_id") or "")
    for lib in libraries.get("enabled") or []:
        lid = str(lib.get("id") or "")
        if not lid:
            continue
        try:
            catalog.extend(client.list_library_programs(lid))
        except Exception:  # noqa: BLE001
            continue
        # Movies-first is enough for starter fill; TV scan may still be queued.
        if str(lib.get("media_type") or "") == "movies" and catalog:
            break

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
    content_filled = 0

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
            "libraries": libraries,
            "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "note": (
                "Could not resolve a Tunarr transcode profile; channels were not published."
            ),
        }

    def _apply_programming(channel_id: str, recipe: ChannelRecipe) -> Dict[str, Any]:
        nonlocal content_filled
        programs = collect_programs_for_recipe(client, recipe, catalog=catalog)
        prog_body = programming_body_for_recipe(recipe, programs=programs)
        programming = (
            client.set_channel_programming(channel_id, prog_body)
            if prog_body is not None
            else {}
        )
        if programs:
            content_filled += 1
        return {
            "programming": dict(programming) if programming else {},
            "program_count": len(programs),
            "titles": [p.get("title") for p in programs[:8]],
        }

    for raw in recipes:
        recipe = raw if isinstance(raw, ChannelRecipe) else recipe_from_mapping(raw)
        key_name = recipe.name.strip().lower()
        if skip_existing_numbers and (
            recipe.number in by_number or key_name in by_name
        ):
            match = by_number.get(recipe.number) or by_name.get(key_name) or {}
            channel_id = str(match.get("id") or match.get("uuid") or "")
            if fill_programming and channel_id:
                try:
                    applied = _apply_programming(channel_id, recipe)
                    programming_updated.append(
                        {
                            "name": recipe.name,
                            "number": recipe.number,
                            "channel_id": channel_id,
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
                        "reason": "already_exists",
                        "channel_id": channel_id or None,
                        "note": (
                            "Lineup not updated; re-publish with fill_programming=true "
                            "after Tunarr libraries are enabled and scanned."
                        ),
                    }
                )
            continue
        try:
            created = client.create_channel(
                channel_create_body(
                    recipe,
                    transcode_config_id=transcode_config_id,
                    icon_url=resolved_icon,
                )
            )
            channel_id = str(created.get("id") or created.get("uuid") or "")
            programming: Mapping[str, Any] = {}
            program_count = 0
            titles: List[Any] = []
            if channel_id:
                try:
                    applied = _apply_programming(channel_id, recipe)
                    programming = applied.get("programming") or {}
                    program_count = int(applied.get("program_count") or 0)
                    titles = list(applied.get("titles") or [])
                except Exception as prog_error:  # noqa: BLE001
                    programming = {"error": str(prog_error)[:200]}
            published.append(
                {
                    "name": recipe.name,
                    "number": recipe.number,
                    "source": recipe.source,
                    "channel_id": channel_id,
                    "channel": dict(created),
                    "programming": dict(programming) if programming else {},
                    "program_count": program_count,
                    "titles": titles,
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
    labels = ensure_channel_labels(
        client, icon_url=resolved_icon, channel_ids=touched_ids or None
    )
    warmed: List[Dict[str, Any]] = []
    if warm_streams:
        for cid in touched_ids[:4]:
            warmed.append(warm_channel_stream(client, cid))

    ok = bool(published) and not errors
    if published and errors:
        ok = False
    if not published and not errors and (skipped or programming_updated):
        ok = True  # idempotent re-publish / fill

    note = (
        "Stations use real Tunarr program IDs when Plex libraries are enabled and "
        "scanned; otherwise lineups stay flex/empty and Plex playback ends immediately."
    )
    if content_filled:
        note = (
            f"Filled {content_filled} station lineup(s) with scanned library titles. "
            "Re-attach / reload the Plex guide if the grid still looks empty."
        )
    elif not catalog:
        note = (
            "No Tunarr program IDs yet — libraries were enabled and a scan was started. "
            "Wait for the scan, then publish again with fill lineups."
        )
    if labels.get("count_updated"):
        note += f" Updated labels/icons on {labels['count_updated']} station(s)."

    return {
        "ok": ok or (bool(published) and not errors),
        "published": published,
        "skipped": skipped,
        "programming_updated": programming_updated,
        "errors": errors,
        "count_published": len(published),
        "count_skipped": len(skipped),
        "count_programming_updated": len(programming_updated),
        "count_errors": len(errors),
        "count_content_filled": content_filled,
        "libraries": libraries,
        "catalog_size": len(catalog),
        "labels": labels,
        "warmed": warmed,
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
    settings: Any = None,
) -> Dict[str, Any]:
    """Create a sequential station from a Plex/Projectionist collection title."""
    title = str(collection_title or name or "Collection").strip() or "Collection"
    number = int(channel_number or 0)
    if number <= 0:
        existing = client.list_channels()
        numbers = [int(ch.get("number") or 0) for ch in existing]
        number = max(numbers) + 1 if numbers else 100
    hints: tuple[str, ...] = ()
    if settings is not None:
        hints = tuple(
            plex_collection_item_hints(settings, collection_id, limit=60)
        )
    recipe = ChannelRecipe(
        name=title[:48],
        number=number,
        source="collection",
        programming_mode=ProgrammingMode.SEQUENTIAL,
        collection_id=str(collection_id or "").strip(),
        collection_title=title,
        summary=f"Sequential channel from collection “{title}”",
        item_hints=hints,
    )
    result = publish_recipes(
        client,
        [recipe],
        skip_existing_numbers=True,
        settings=settings,
    )
    result["recipe"] = recipe.to_dict()
    result["item_hint_count"] = len(hints)
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
    default_number = next_channel_number(numbers, base=int(channel_number_base or 100))
    if isinstance(recipe_payload, ChannelRecipe):
        recipe = recipe_payload
        if recipe.number <= 0:
            recipe = ChannelRecipe(
                name=recipe.name,
                number=default_number,
                source=recipe.source,
                programming_mode=recipe.programming_mode,
                cluster_tag=recipe.cluster_tag,
                motif=recipe.motif,
                collection_id=recipe.collection_id,
                collection_title=recipe.collection_title,
                youth_safe=recipe.youth_safe,
                summary=recipe.summary,
                item_hints=recipe.item_hints,
            )
    else:
        recipe = recipe_from_craft_payload(
            recipe_payload or {},
            default_number=default_number,
        )
    # Enrich collection recipes with Plex children when hints are empty.
    if (
        settings is not None
        and recipe.source == "collection"
        and recipe.collection_id
        and not recipe.item_hints
    ):
        hints = tuple(
            plex_collection_item_hints(settings, recipe.collection_id, limit=60)
        )
        if hints:
            recipe = ChannelRecipe(
                name=recipe.name,
                number=recipe.number,
                source=recipe.source,
                programming_mode=recipe.programming_mode,
                cluster_tag=recipe.cluster_tag,
                motif=recipe.motif,
                collection_id=recipe.collection_id,
                collection_title=recipe.collection_title,
                youth_safe=recipe.youth_safe,
                summary=recipe.summary,
                item_hints=hints,
            )
    result = publish_recipes(
        client,
        [recipe],
        skip_existing_numbers=True,
        fill_programming=fill_programming,
        settings=settings,
    )
    result["recipe"] = recipe.to_dict()
    return result


def refill_channel_lineup(
    client: TunarrClient,
    channel_id: str,
    *,
    recipe_payload: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Re-fill an existing Tunarr station lineup from craft vocabulary / Chaos."""
    from projectionist.live_channels.craft import recipe_from_craft_payload

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
    if recipe_payload:
        recipe = recipe_from_craft_payload(
            {
                **dict(recipe_payload),
                "name": str(recipe_payload.get("name") or name),
                "number": int(recipe_payload.get("number") or number or 100),
            },
            default_number=number or 100,
        )
    else:
        recipe = ChannelRecipe(
            name=name[:48],
            number=number or 100,
            source="chaos",
            programming_mode=ProgrammingMode.CHAOS,
            summary=f"Refill lineup for “{name}”",
        )

    libraries = ensure_media_libraries_enabled(client, scan=True)
    catalog: List[Mapping[str, Any]] = []
    for lib in libraries.get("enabled") or []:
        lid = str(lib.get("id") or "")
        if not lid:
            continue
        try:
            catalog.extend(client.list_library_programs(lid))
        except Exception:  # noqa: BLE001
            continue
        if str(lib.get("media_type") or "") == "movies" and catalog:
            break

    programs = collect_programs_for_recipe(client, recipe, catalog=catalog)
    prog_body = programming_body_for_recipe(recipe, programs=programs)
    programming = (
        client.set_channel_programming(cid, prog_body) if prog_body is not None else {}
    )
    return {
        "ok": bool(programs),
        "channel_id": cid,
        "name": name,
        "number": number,
        "program_count": len(programs),
        "titles": [p.get("title") for p in programs[:8]],
        "programming": dict(programming) if programming else {},
        "libraries": libraries,
        "catalog_size": len(catalog),
        "recipe": recipe.to_dict(),
        "note": (
            f"Filled {len(programs)} titles into {name}."
            if programs
            else (
                "No Tunarr program IDs yet — wait for the library scan, then refill again."
            )
        ),
    }


def delete_published_channel(client: TunarrClient, channel_id: str) -> Dict[str, Any]:
    """Delete a Tunarr station by id (owner manage path)."""
    cid = str(channel_id or "").strip()
    if not cid:
        raise ValueError("channel_id is required")
    client.delete_channel(cid)
    return {"ok": True, "channel_id": cid, "deleted": True}


def tunarr_client_from_settings(settings: Any) -> TunarrClient:
    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    if not url:
        raise ValueError("Tunarr URL is not configured")
    return TunarrClient(url)
