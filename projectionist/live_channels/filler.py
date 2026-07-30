"""Continuity filler lists — multi-path union, shuffle, attach, jump-start repair.

Owner configures one or more host folders of short programming. Projectionist
mounts each path into Tunarr, indexes them as a local media source, and maintains
a single ``Projectionist Continuity`` filler list (randomized union). Stations
get ``fillerCollections`` + guide/offline fields so flex gaps bridge titles.
"""

from __future__ import annotations

import logging
import random
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from projectionist.connectors.tunarr import TunarrClient

logger = logging.getLogger(__name__)

CONTINUITY_FILLER_LIST_NAME = "Projectionist Continuity"
LOCAL_FILLER_SOURCE_NAME = "Projectionist Fillers"
DEFAULT_FILLER_WEIGHT = 100
DEFAULT_FILLER_COOLDOWN_SECONDS = 30 * 60  # 30 min between same clip
DEFAULT_FILLER_REPEAT_COOLDOWN_MS = 30 * 60 * 1000
# Prefer shorts that tile a commercial-cut flex window (≤15 min).
_MAX_FILLER_DURATION_MS = 15 * 60 * 1000
_MIN_FILLER_DURATION_MS = 1_000
# Soft-warn when combined unique filler is thinner than this (per several stations).
_THIN_POOL_DURATION_MS = 60 * 60 * 1000  # 60 minutes
_DEFAULT_GUIDE_FLEX_SUFFIX = " · Up next"


def normalize_filler_bind(spec: str, *, index: int = 0) -> str:
    """Normalize a host path or ``host:container[:mode]`` into a Docker bind.

    Bare host paths become ``{host}:/data/filler/{basename}:ro``.
    """
    text = str(spec or "").strip()
    if not text:
        return ""
    parts = text.split(":")
    # host:container or host:container:mode (container paths start with /)
    if len(parts) >= 2 and parts[1].startswith("/"):
        if len(parts) == 2:
            return f"{text}:ro"
        return text
    host = text
    base = Path(host).name or f"filler{index}"
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._") or f"filler{index}"
    return f"{host}:/data/filler/{safe}:ro"


def parse_filler_binds(value: Any) -> List[str]:
    """Parse filler bind specs from a list or comma-separated string."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items = [str(part).strip() for part in value if str(part).strip()]
    else:
        items = [str(value).strip()] if str(value).strip() else []
    out: List[str] = []
    seen: set[str] = set()
    for i, item in enumerate(items):
        bind = normalize_filler_bind(item, index=i)
        if not bind or ":" not in bind:
            continue
        # Dedupe by host:container (ignore mode)
        host, container = bind.split(":", 2)[:2]
        key = f"{host}:{container}"
        if key in seen:
            continue
        seen.add(key)
        out.append(bind)
    return out


def resolve_filler_binds(settings: Any = None) -> List[str]:
    """Filler programming binds for Tunarr (settings nest and/or env)."""
    from projectionist.envcompat import branded_env

    env_raw = branded_env("TUNARR_FILLER_BINDS")
    if env_raw is not None and str(env_raw).strip() != "":
        return parse_filler_binds(env_raw)
    tunarr = getattr(settings, "tunarr", None) if settings is not None else None
    return parse_filler_binds(getattr(tunarr, "filler_binds", None) if tunarr else None)


def filler_container_paths(binds: Sequence[str]) -> List[str]:
    """Container-side paths from binder specs (for Tunarr local media source)."""
    paths: List[str] = []
    seen: set[str] = set()
    for spec in binds:
        parts = str(spec).split(":")
        if len(parts) < 2:
            continue
        container = parts[1].strip()
        if not container or container in seen:
            continue
        seen.add(container)
        paths.append(container)
    return paths


def _offline_body(icon_url: str = "") -> Dict[str, Any]:
    picture = str(icon_url or "").strip()
    body: Dict[str, Any] = {"mode": "pic"}
    if picture:
        body["picture"] = picture
    return body


def continuity_channel_fields(
    *,
    filler_list_id: str = "",
    station_name: str = "",
    icon_url: str = "",
    weight: int = DEFAULT_FILLER_WEIGHT,
    cooldown_seconds: int = DEFAULT_FILLER_COOLDOWN_SECONDS,
    attach: bool = True,
) -> Dict[str, Any]:
    """Channel fields for continuity (create + PUT)."""
    name = str(station_name or "").strip() or "Station"
    fields: Dict[str, Any] = {
        "disableFillerOverlay": False,
        "guideFlexTitle": f"{name}{_DEFAULT_GUIDE_FLEX_SUFFIX}"[:64],
        "offline": _offline_body(icon_url),
        "fillerRepeatCooldown": DEFAULT_FILLER_REPEAT_COOLDOWN_MS,
    }
    fid = str(filler_list_id or "").strip()
    if attach and fid:
        fields["fillerCollections"] = [
            {
                "id": fid,
                "weight": int(weight or DEFAULT_FILLER_WEIGHT),
                "cooldownSeconds": int(cooldown_seconds or DEFAULT_FILLER_COOLDOWN_SECONDS),
            }
        ]
    else:
        fields["fillerCollections"] = []
    return fields


def channel_has_continuity(ch: Mapping[str, Any], *, filler_list_id: str = "") -> bool:
    """True when a Tunarr channel already has a continuity filler collection."""
    cols = ch.get("fillerCollections") or []
    if not isinstance(cols, list) or not cols:
        return False
    fid = str(filler_list_id or "").strip()
    if not fid:
        return True
    for col in cols:
        if isinstance(col, Mapping) and str(col.get("id") or "") == fid:
            return True
    return False


def _program_row_for_filler(item: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a library/search program into a CreateFillerList program row."""
    if not isinstance(item, Mapping):
        return None
    nested = item.get("program") if isinstance(item.get("program"), Mapping) else None
    pid = str(
        item.get("id")
        or item.get("uuid")
        or (nested or {}).get("uuid")
        or (nested or {}).get("id")
        or ""
    ).strip()
    try:
        duration = int(item.get("duration") or (nested or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0
    if not pid or duration < _MIN_FILLER_DURATION_MS:
        return None
    if duration > _MAX_FILLER_DURATION_MS:
        return None
    program = dict(nested) if nested else dict(item)
    # Ensure identity fields Tunarr expects on nested program.
    if "uuid" not in program:
        program["uuid"] = pid
    if "id" not in program and "uuid" in program:
        program.setdefault("id", pid)
    return {
        "type": "content",
        "id": pid,
        "duration": duration,
        "program": program,
    }


def collect_short_programs(
    client: TunarrClient,
    *,
    library_ids: Sequence[str] = (),
    max_items: int = 400,
) -> List[Dict[str, Any]]:
    """Collect short-duration content rows from Tunarr libraries (deduped)."""
    pool: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for lid in library_ids:
        if not str(lid).strip():
            continue
        try:
            items = client.list_library_programs(str(lid))
        except Exception as error:  # noqa: BLE001
            logger.debug("list_library_programs %s failed: %s", lid, error)
            continue
        for raw in items:
            row = _program_row_for_filler(raw)
            if not row or row["id"] in seen:
                continue
            seen.add(row["id"])
            pool.append(row)
            if len(pool) >= max_items:
                return pool
    return pool


def ensure_local_filler_source(
    client: TunarrClient,
    *,
    container_paths: Sequence[str],
    scan: bool = True,
) -> Dict[str, Any]:
    """Ensure a Tunarr ``local`` media source covering filler container paths."""
    paths = [str(p).strip() for p in container_paths if str(p).strip()]
    if not paths:
        return {
            "ok": False,
            "created": False,
            "library_ids": [],
            "message": "No filler container paths configured.",
        }
    existing = client.list_media_sources()
    match: Optional[Mapping[str, Any]] = None
    for source in existing:
        if str(source.get("type") or "").lower() != "local":
            continue
        name = str(source.get("name") or "")
        if name == LOCAL_FILLER_SOURCE_NAME or name.lower().startswith("projectionist filler"):
            match = source
            break
    body = {
        "name": LOCAL_FILLER_SOURCE_NAME,
        "type": "local",
        "mediaType": "other_videos",
        "paths": paths,
        "pathReplacements": [],
    }
    created = False
    if match is None:
        try:
            created_payload = client.create_media_source(body)
        except Exception as error:  # noqa: BLE001
            return {
                "ok": False,
                "created": False,
                "library_ids": [],
                "message": f"Could not create local filler source: {error}"[:240],
            }
        msid = str(created_payload.get("id") or created_payload.get("uuid") or "")
        created = True
    else:
        msid = str(match.get("id") or match.get("uuid") or "")
        # Update paths when the owner added/removed filler folders.
        try:
            client.update_media_source(msid, body)
        except Exception:  # noqa: BLE001 — some Tunarr builds reject partial updates
            pass

    if not msid:
        return {
            "ok": False,
            "created": created,
            "library_ids": [],
            "message": "Local filler source missing id.",
        }

    library_ids: List[str] = []
    errors: List[str] = []
    try:
        libraries = client.list_media_source_libraries(msid)
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "created": created,
            "media_source_id": msid,
            "library_ids": [],
            "message": f"Could not list filler libraries: {error}"[:240],
        }
    for lib in libraries:
        lid = str(lib.get("id") or "").strip()
        if not lid:
            continue
        library_ids.append(lid)
        try:
            if not bool(lib.get("enabled")):
                client.set_library_enabled(msid, lid, enabled=True)
            if scan:
                client.scan_library(msid, lid, force=True)
        except Exception as error:  # noqa: BLE001
            errors.append(str(error)[:120])

    return {
        "ok": bool(library_ids) and not errors,
        "created": created,
        "media_source_id": msid,
        "library_ids": library_ids,
        "paths": paths,
        "errors": errors,
        "message": (
            f"Local filler source ready ({len(library_ids)} library(ies))."
            if library_ids
            else "Local filler source has no libraries yet — wait for Tunarr to index paths."
        ),
    }


def find_continuity_filler_list(
    client: TunarrClient,
) -> Optional[Mapping[str, Any]]:
    for item in client.list_filler_lists():
        if str(item.get("name") or "").strip() == CONTINUITY_FILLER_LIST_NAME:
            return item
    return None


def ensure_continuity_filler_list(
    client: TunarrClient,
    settings: Any = None,
    *,
    shuffle: bool = True,
    rng: Optional[random.Random] = None,
    scan: bool = True,
) -> Dict[str, Any]:
    """Build/update the shared continuity filler list (union of all filler paths).

    Randomizes membership order on each rebuild. Returns status including
    ``thin_pool`` when combined duration is short relative to pad appetite.
    """
    binds = resolve_filler_binds(settings)
    container_paths = filler_container_paths(binds)
    if not container_paths:
        existing = find_continuity_filler_list(client)
        return {
            "ok": False,
            "ready": False,
            "filler_list_id": str((existing or {}).get("id") or ""),
            "program_count": int((existing or {}).get("contentCount") or 0),
            "total_duration_ms": 0,
            "thin_pool": True,
            "binds": [],
            "paths": [],
            "message": (
                "No filler programming paths configured. Add one or more host folders "
                "under Installation → Filler programming paths."
            ),
        }

    source_state = ensure_local_filler_source(
        client, container_paths=container_paths, scan=scan
    )
    library_ids = list(source_state.get("library_ids") or [])
    programs = collect_short_programs(client, library_ids=library_ids)
    if shuffle and programs:
        (rng or random).shuffle(programs)

    total_duration_ms = sum(int(p.get("duration") or 0) for p in programs)
    thin_pool = total_duration_ms < _THIN_POOL_DURATION_MS

    existing = find_continuity_filler_list(client)
    filler_list_id = str((existing or {}).get("id") or "")
    try:
        if filler_list_id:
            client.update_filler_list(
                filler_list_id,
                {"name": CONTINUITY_FILLER_LIST_NAME, "programs": programs},
            )
            action = "updated"
        else:
            created = client.create_filler_list(
                {"name": CONTINUITY_FILLER_LIST_NAME, "programs": programs}
            )
            filler_list_id = str(created.get("id") or "")
            action = "created"
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "ready": False,
            "filler_list_id": filler_list_id,
            "program_count": len(programs),
            "total_duration_ms": total_duration_ms,
            "thin_pool": thin_pool,
            "binds": binds,
            "paths": container_paths,
            "source": source_state,
            "message": f"Could not write continuity filler list: {error}"[:240],
        }

    ready = bool(filler_list_id) and bool(programs)
    message = (
        f"{action.capitalize()} continuity filler list with {len(programs)} short(s) "
        f"from {len(container_paths)} path(s)."
        if ready
        else (
            "Filler paths are mounted but no short clips are indexed yet. "
            "Wait for the local library scan, then Rescan filler."
        )
    )
    if ready and thin_pool:
        message += (
            " Combined filler pool is thin for commercial-cut gaps (often up to 15 "
            "minutes between episodes) — add more bumpers/trailers to avoid repeats."
        )

    # Cache id on settings when provided (caller persists).
    if settings is not None and filler_list_id:
        tunarr = getattr(settings, "tunarr", None)
        if tunarr is not None:
            try:
                setattr(tunarr, "continuity_filler_list_id", filler_list_id)
            except Exception:  # noqa: BLE001
                pass

    return {
        "ok": ready,
        "ready": ready,
        "action": action,
        "filler_list_id": filler_list_id,
        "program_count": len(programs),
        "total_duration_ms": total_duration_ms,
        "thin_pool": thin_pool,
        "binds": binds,
        "paths": container_paths,
        "source": source_state,
        "message": message,
    }


def attach_continuity_to_channel(
    client: TunarrClient,
    channel: Mapping[str, Any],
    *,
    filler_list_id: str,
    icon_url: str = "",
    force: bool = False,
) -> Dict[str, Any]:
    """PUT continuity fields onto an existing Tunarr channel (idempotent)."""
    from projectionist.live_channels.publish import _channel_put_body

    cid = str(channel.get("id") or channel.get("uuid") or "").strip()
    if not cid:
        return {"ok": False, "changed": False, "error": "missing channel id"}
    fid = str(filler_list_id or "").strip()
    if not fid:
        return {"ok": False, "changed": False, "error": "missing filler list id"}
    if not force and channel_has_continuity(channel, filler_list_id=fid):
        guide = str(channel.get("guideFlexTitle") or "").strip()
        offline = channel.get("offline") if isinstance(channel.get("offline"), Mapping) else {}
        if guide and offline.get("mode"):
            return {"ok": True, "changed": False, "channel_id": cid}

    name = str(channel.get("name") or "").strip()
    continuity = continuity_channel_fields(
        filler_list_id=fid,
        station_name=name,
        icon_url=icon_url
        or str((channel.get("icon") or {}).get("path") or "")
        if isinstance(channel.get("icon"), Mapping)
        else icon_url,
    )
    body = _channel_put_body(channel, name=name)
    body.update(continuity)
    if not body.get("transcodeConfigId"):
        return {"ok": False, "changed": False, "channel_id": cid, "error": "missing transcodeConfigId"}
    try:
        client.update_channel(cid, body)
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "changed": False, "channel_id": cid, "error": str(error)[:200]}
    return {"ok": True, "changed": True, "channel_id": cid}


def pad_lineup_with_flex(
    lineup: Sequence[Mapping[str, Any]],
    *,
    max_flex_ms: int = 15 * 60 * 1000,
    start_time_ms: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Insert flex pads (≤ max_flex_ms) so content lands on :00 / :30 boundaries.

    Flex duration owns the clock — filler clip lengths do not push the next title.
    """
    cap = max(0, int(max_flex_ms or 0))
    if cap <= 0:
        return [dict(item) for item in lineup if isinstance(item, Mapping)]

    half_hour_ms = 30 * 60 * 1000
    cursor = int(start_time_ms if start_time_ms is not None else time.time() * 1000)
    out: List[Dict[str, Any]] = []

    def _gap_to_boundary(end_ms: int) -> int:
        # Distance forward to next :00 or :30 wall-clock mark.
        rem = end_ms % half_hour_ms
        if rem == 0:
            return 0
        return half_hour_ms - rem

    for raw in lineup:
        if not isinstance(raw, Mapping):
            continue
        item = dict(raw)
        item_type = str(item.get("type") or "").lower()
        try:
            duration = int(item.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        if item_type == "flex":
            # Keep existing flex but clamp to pad budget.
            if duration > 0:
                clamped = min(duration, cap)
                out.append({"type": "flex", "duration": clamped})
                cursor += clamped
            continue
        if duration <= 0:
            continue
        out.append(item)
        cursor += duration
        gap = _gap_to_boundary(cursor)
        if 0 < gap <= cap:
            out.append({"type": "flex", "duration": gap})
            cursor += gap
    return out


def filler_pool_status(
    *,
    program_count: int,
    total_duration_ms: int,
    station_count: int = 0,
) -> Dict[str, Any]:
    """Installation status helper for thin-pool warnings."""
    thin = int(total_duration_ms or 0) < _THIN_POOL_DURATION_MS
    return {
        "program_count": int(program_count or 0),
        "total_duration_ms": int(total_duration_ms or 0),
        "thin_pool": thin,
        "station_count": int(station_count or 0),
        "pad_flex_max_minutes": 15,
        "message": (
            "Commercial-cut shows often need up to 15 minutes of filler between "
            "episodes. Add more short bumpers/trailers when this check is not green."
            if thin
            else "Filler pool looks deep enough for typical commercial-cut gaps."
        ),
    }


def repair_jumpstart_stations(
    client: TunarrClient,
    settings: Any = None,
    *,
    icon_url: str = "",
    refill_lineups: bool = True,
    pad_lineups: bool = True,
    prepare: bool = True,
    channel_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Attach continuity + pad/refill under-defined stations (idempotent).

    Defaults media_scope to ``both`` for legacy jump-starts lacking stored scope.
    """
    from projectionist.live_channels.publish import (
        prepare_channels_for_playback,
        programming_body_for_recipe,
        refill_channel_lineup,
        resolve_channel_icon_url,
        resolve_media_scope,
        set_station_media_scope,
    )
    from projectionist.live_channels.recipes import ChannelRecipe, ProgrammingMode

    filler = ensure_continuity_filler_list(client, settings, shuffle=True, scan=True)
    fid = str(filler.get("filler_list_id") or "")
    resolved_icon = str(icon_url or "").strip() or resolve_channel_icon_url(settings)

    wanted = {str(c).strip() for c in (channel_ids or ()) if str(c).strip()}
    channels = [
        ch
        for ch in client.list_channels()
        if isinstance(ch, Mapping)
        and (
            not wanted
            or str(ch.get("id") or ch.get("uuid") or "").strip() in wanted
        )
    ]

    attached: List[Dict[str, Any]] = []
    padded: List[Dict[str, Any]] = []
    refilled: List[Dict[str, Any]] = []
    scopes_set: List[str] = []
    errors: List[str] = []
    already_ok: List[str] = []

    for ch in channels:
        cid = str(ch.get("id") or ch.get("uuid") or "").strip()
        if not cid:
            continue
        name = str(ch.get("name") or "").strip() or f"Channel {ch.get('number')}"
        # Persist default media scope for legacy jump-starts.
        try:
            scope = resolve_media_scope(settings, channel_id=cid, default="both")
            if settings is not None:
                set_station_media_scope(settings, cid, scope)
                scopes_set.append(cid)
        except Exception as error:  # noqa: BLE001
            errors.append(f"{name}: scope {error}"[:160])

        if fid:
            result = attach_continuity_to_channel(
                client, ch, filler_list_id=fid, icon_url=resolved_icon
            )
            if result.get("ok") and result.get("changed"):
                attached.append({"channel_id": cid, "name": name})
            elif result.get("ok") and not result.get("changed"):
                already_ok.append(cid)
            elif not result.get("ok"):
                errors.append(f"{name}: {result.get('error') or 'attach failed'}"[:160])
        else:
            # Still set guide/offline identity even when filler paths are empty.
            try:
                from projectionist.live_channels.publish import _channel_put_body

                continuity = continuity_channel_fields(
                    filler_list_id="",
                    station_name=name,
                    icon_url=resolved_icon,
                    attach=False,
                )
                needs = not str(ch.get("guideFlexTitle") or "").strip()
                if needs or resolved_icon:
                    body = _channel_put_body(ch, name=name)
                    body.update(continuity)
                    if body.get("transcodeConfigId"):
                        client.update_channel(cid, body)
            except Exception as error:  # noqa: BLE001
                errors.append(f"{name}: guide/offline {error}"[:160])

        if refill_lineups:
            try:
                recipe = ChannelRecipe(
                    name=name[:48],
                    number=int(ch.get("number") or 0) or 100,
                    source="chaos",
                    programming_mode=ProgrammingMode.CHAOS,
                    media_scope=resolve_media_scope(settings, channel_id=cid, default="both"),
                    summary=f"Repair refill for “{name}”",
                )
                refill = refill_channel_lineup(
                    client,
                    cid,
                    recipe_payload=recipe.to_dict(),
                    settings=settings,
                    pad_lineups=pad_lineups,
                    attach_continuity=bool(fid),
                )
                if refill.get("ok"):
                    refilled.append(
                        {
                            "channel_id": cid,
                            "name": name,
                            "program_count": refill.get("program_count"),
                        }
                    )
                if refill.get("padded"):
                    padded.append({"channel_id": cid, "name": name})
            except Exception as error:  # noqa: BLE001
                errors.append(f"{name}: refill {error}"[:160])

    prepare_result: Dict[str, Any] = {}
    if prepare:
        try:
            prepare_result = prepare_channels_for_playback(
                client,
                settings=settings,
                channel_ids=[str(ch.get("id") or "") for ch in channels],
                icon_url=resolved_icon,
            )
        except Exception as error:  # noqa: BLE001
            errors.append(f"prepare: {error}"[:160])

    ok = bool(fid) and not errors
    if not fid:
        ok = False
    note = filler.get("message") or ""
    if attached:
        note = (
            f"Attached continuity to {len(attached)} station(s). "
            + (note or "")
        ).strip()
    elif already_ok and fid:
        note = (
            f"All {len(already_ok)} station(s) already have continuity attached. "
            + (note or "")
        ).strip()

    return {
        "ok": ok or (bool(attached or refilled or already_ok) and not errors),
        "filler": filler,
        "attached": attached,
        "already_ok": already_ok,
        "refilled": refilled,
        "padded": padded,
        "scopes_set": scopes_set,
        "errors": errors,
        "count_attached": len(attached),
        "count_refilled": len(refilled),
        "count_errors": len(errors),
        "prepare": prepare_result,
        "message": note
        or (
            "Repair finished."
            if not errors
            else f"Repair finished with {len(errors)} error(s)."
        ),
    }


def continuity_installation_status(
    client: Optional[TunarrClient],
    settings: Any = None,
) -> Dict[str, Any]:
    """Green-check payload for Installation / Stations continuity strip."""
    binds = resolve_filler_binds(settings)
    paths = filler_container_paths(binds)
    station_count = 0
    attached_count = 0
    filler_list_id = ""
    program_count = 0
    total_duration_ms = 0
    reachable = client is not None
    if client is not None:
        try:
            existing = find_continuity_filler_list(client)
            if existing:
                filler_list_id = str(existing.get("id") or "")
                program_count = int(existing.get("contentCount") or 0)
            channels = client.list_channels()
            station_count = len(channels)
            for ch in channels:
                if channel_has_continuity(ch, filler_list_id=filler_list_id):
                    attached_count += 1
            if filler_list_id:
                try:
                    progs = client.get_filler_list_programs(filler_list_id)
                    total_duration_ms = sum(
                        int(p.get("duration") or 0)
                        for p in progs
                        if isinstance(p, Mapping)
                    )
                    program_count = len(progs) or program_count
                except Exception:  # noqa: BLE001
                    pass
        except Exception as error:  # noqa: BLE001
            return {
                "ok": False,
                "reachable": False,
                "binds": binds,
                "path_count": len(paths),
                "error": str(error)[:200],
                "checks": [],
            }

    pool = filler_pool_status(
        program_count=program_count,
        total_duration_ms=total_duration_ms,
        station_count=station_count,
    )
    list_ready = bool(filler_list_id) and program_count > 0
    stations_attached = station_count > 0 and attached_count >= station_count
    jumpstarts_ok = stations_attached  # same bar for v1
    checks = [
        {
            "id": "filler_paths_mounted",
            "ok": bool(binds),
            "soft": not binds,
            "label": f"Filler paths mounted ({len(binds)})",
            "message": (
                f"{len(binds)} path(s) configured"
                if binds
                else "Add filler programming folders under Installation"
            ),
        },
        {
            "id": "filler_list_populated",
            "ok": list_ready,
            "soft": bool(binds) and not list_ready,
            "label": "Combined filler list populated",
            "message": (
                f"{program_count} short(s) in Projectionist Continuity"
                if list_ready
                else "Rescan filler after paths are indexed"
            ),
        },
        {
            "id": "stations_continuity",
            "ok": stations_attached,
            "soft": station_count == 0 or (list_ready and not stations_attached),
            "label": "Stations have continuity attached",
            "message": (
                f"{attached_count}/{station_count} station(s)"
                if station_count
                else "No stations yet"
            ),
        },
        {
            "id": "jumpstart_repaired",
            "ok": jumpstarts_ok,
            "soft": station_count > 0 and not jumpstarts_ok,
            "label": "Jump-start stations repaired",
            "message": (
                "Mystery / Sci-Fi / Chaos have fillerCollections"
                if jumpstarts_ok
                else "Run Repair continuity on all stations"
            ),
        },
        {
            "id": "filler_pool_depth",
            "ok": list_ready and not pool["thin_pool"],
            "soft": list_ready and pool["thin_pool"],
            "label": "Filler pool deep enough for ~15 min gaps",
            "message": pool["message"],
        },
    ]
    return {
        "ok": list_ready and stations_attached,
        "reachable": reachable,
        "binds": binds,
        "path_count": len(paths),
        "paths": paths,
        "filler_list_id": filler_list_id,
        "program_count": program_count,
        "total_duration_ms": total_duration_ms,
        "thin_pool": pool["thin_pool"],
        "station_count": station_count,
        "attached_count": attached_count,
        "checks": checks,
        "pool": pool,
    }
