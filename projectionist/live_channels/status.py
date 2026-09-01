"""Aggregate Live Channels admin status for owner API / health strip."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.request import Request, urlopen

from projectionist.connectors.tunarr import TunarrClient, tunarr_reachable
from projectionist.live_channels.docker import (
    docker_socket_available,
    lifecycle_from_settings,
    orchestration_enabled,
)
from projectionist.live_channels.guide import build_on_now_snapshot
from projectionist.live_channels.plex_attach import (
    probe_existing_plex_livetv,
    probe_plex_tunarr_mapping,
    resolve_plex_facing_tunarr_base,
    xmltv_url,
)
from projectionist.live_channels.plex_pass import check_plex_pass


def _xmltv_programme_stats(guide_url: str, *, timeout: int = 8) -> Dict[str, Any]:
    """Fetch Tunarr XMLTV and count channels / programmes (owner indexing pulse)."""
    url = str(guide_url or "").strip()
    if not url:
        return {
            "ok": False,
            "channel_count": 0,
            "programme_count": 0,
            "content_programme_count": 0,
            "error": "XMLTV URL not configured",
        }
    try:
        request = Request(url, headers={"Accept": "application/xml,*/*"})
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
        root = ET.fromstring(body)
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "channel_count": 0,
            "programme_count": 0,
            "content_programme_count": 0,
            "error": str(error)[:200],
        }
    channels = list(root.findall("channel"))
    programmes = list(root.findall("programme"))
    # Tunarr flex placeholders often reuse the channel name as the title.
    channel_names = {
        (ch.findtext("display-name") or "").strip().lower()
        for ch in channels
    }
    content = 0
    for prog in programmes:
        title = (prog.findtext("title") or "").strip()
        # display-name is like "100 Mystery" — compare bare name too
        bare = title.lower()
        if not bare:
            continue
        if bare in channel_names or any(
            bare == name.split(" ", 1)[-1] for name in channel_names if name
        ):
            continue
        content += 1
    return {
        "ok": True,
        "channel_count": len(channels),
        "programme_count": len(programmes),
        "content_programme_count": content,
        "error": "",
    }


def _media_library_index(client: TunarrClient) -> Dict[str, Any]:
    """Enabled libraries + scan state for the first Plex media source."""
    try:
        sources = client.list_media_sources()
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "error": str(error)[:200], "libraries": []}
    plex = next(
        (
            s
            for s in sources
            if str(s.get("type") or s.get("sourceType") or "").lower() == "plex"
        ),
        None,
    )
    if plex is None:
        return {
            "ok": False,
            "error": "No Plex media source in Tunarr",
            "libraries": [],
        }
    msid = str(plex.get("id") or plex.get("uuid") or "")
    try:
        libraries = client.list_media_source_libraries(msid) if msid else []
    except Exception as error:  # noqa: BLE001
        return {
            "ok": False,
            "media_source_id": msid,
            "error": str(error)[:200],
            "libraries": [],
        }
    rows: List[Dict[str, Any]] = []
    enabled_count = 0
    scanning = 0
    for lib in libraries:
        lid = str(lib.get("id") or "")
        enabled = bool(lib.get("enabled"))
        if enabled:
            enabled_count += 1
        state = ""
        percent = None
        if msid and lid:
            try:
                status = client.get_library_scan_status(msid, lid)
                state = str(status.get("state") or "")
                percent = status.get("percentComplete")
                if state in {"in_progress", "queued", "running"}:
                    scanning += 1
            except Exception:  # noqa: BLE001
                pass
        rows.append(
            {
                "id": lid,
                "name": str(lib.get("name") or lid),
                "media_type": str(lib.get("mediaType") or ""),
                "enabled": enabled,
                "scan_state": state,
                "scan_percent": percent,
            }
        )
    return {
        "ok": True,
        "media_source_id": msid,
        "enabled_count": enabled_count,
        "scanning_count": scanning,
        "libraries": rows[:20],
        "error": "",
    }


def _lineup_health(client: TunarrClient, channels: Sequence[Mapping[str, Any]] | List) -> Dict[str, Any]:
    """Per-channel Tunarr programming depth (empty → Plex session ends immediately)."""
    rows: List[Dict[str, Any]] = []
    empty = 0
    filled = 0
    for ch in channels[:40]:
        if not isinstance(ch, Mapping):
            continue
        cid = str(ch.get("id") or ch.get("uuid") or "")
        total = 0
        if cid:
            try:
                prog = client.get_channel_programming(cid)
                total = int(prog.get("totalPrograms") or len(prog.get("lineup") or []) or 0)
            except Exception:  # noqa: BLE001
                total = 0
        if total <= 0:
            empty += 1
        else:
            filled += 1
        rows.append(
            {
                "id": cid,
                "name": ch.get("name"),
                "number": ch.get("number"),
                "total_programs": total,
            }
        )
    return {
        "channel_count": len(rows),
        "filled_count": filled,
        "empty_count": empty,
        "channels": rows,
        "playable": empty == 0 and filled > 0,
    }


def summarize_sessions(
    sessions_by_channel: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Flatten Tunarr ``GET /sessions`` into an owner-friendly summary."""
    channels: List[Dict[str, Any]] = []
    total_connections = 0
    if isinstance(sessions_by_channel, Mapping):
        for channel_id, session_list in sessions_by_channel.items():
            if not isinstance(session_list, list):
                continue
            connections = 0
            states: List[str] = []
            types: List[str] = []
            for session in session_list:
                if not isinstance(session, Mapping):
                    continue
                try:
                    connections += int(session.get("numConnections") or 0)
                except (TypeError, ValueError):
                    pass
                state = str(session.get("state") or "").strip()
                if state:
                    states.append(state)
                session_type = str(session.get("type") or "").strip()
                if session_type:
                    types.append(session_type)
            if connections <= 0 and not session_list:
                continue
            total_connections += connections
            channels.append(
                {
                    "channel_id": str(channel_id),
                    "connections": connections,
                    "session_count": len(session_list),
                    "states": states,
                    "types": types,
                }
            )
    channels.sort(key=lambda row: (-int(row.get("connections") or 0), str(row.get("channel_id"))))
    return {
        "active_channels": len(channels),
        "total_connections": total_connections,
        "channels": channels[:40],
    }


def airing_rows_from_snapshot(snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """Extract per-channel airing progress rows from an on-now snapshot."""
    rows: List[Dict[str, Any]] = []
    for channel in snapshot.get("channels") or []:
        if not isinstance(channel, Mapping):
            continue
        now = channel.get("now")
        if not isinstance(now, Mapping):
            continue
        title = str(now.get("title") or "").strip()
        if not title:
            continue
        nxt = channel.get("next") if isinstance(channel.get("next"), Mapping) else None
        next_title = str((nxt or {}).get("title") or "").strip()
        rows.append(
            {
                "id": str(channel.get("id") or ""),
                "name": str(channel.get("name") or "Channel"),
                "number": channel.get("number"),
                "title": title,
                "started_at": now.get("started_at"),
                "ends_at": now.get("ends_at"),
                "seconds_elapsed": now.get("seconds_elapsed"),
                "seconds_remaining": now.get("seconds_remaining"),
                "percent": now.get("percent"),
                "is_paused": bool(now.get("is_paused")),
                "next_title": next_title or None,
                "next_start": (nxt or {}).get("start") if nxt else None,
            }
        )
    return rows


_PLACEHOLDER_TITLES = frozenset({"flex", "filler", "continuity"})


def now_kind_for_title(title: Optional[str]) -> str:
    """Classify a now-title: program, Tunarr flex placeholder, or blank."""
    text = str(title or "").strip()
    if not text:
        return ""
    # Tunarr fills empty lineups with a 6-hour "{Station} · Up next" slot.
    if "· Up next" in text or text.lower() in _PLACEHOLDER_TITLES:
        return "placeholder"
    return "program"


def _station_health_chip(
    *,
    engine_up: bool,
    now: Optional[Mapping[str, Any]],
    lineup_programs: Optional[int],
    now_kind: str = "",
) -> str:
    """Compact owner health token for the now-playing table.

    Order: unreachable → paused → empty lineup → airing → idle.
    Stream/HLS connection count is metadata, not a health override — stream-warm
    keepalive must not make an empty station look like it is streaming.
    """
    if not engine_up:
        return "unreachable"
    if now and bool(now.get("is_paused")):
        return "paused"
    if lineup_programs is not None and int(lineup_programs) <= 0:
        return "empty"
    kind = str(now_kind or "").strip() or now_kind_for_title(
        str((now or {}).get("title") or "")
    )
    if kind == "program":
        return "airing"
    return "idle"


def owner_now_playing_rows(
    snapshot: Mapping[str, Any],
    *,
    channels: Optional[Sequence[Mapping[str, Any]]] = None,
    lineup_health: Optional[Mapping[str, Any]] = None,
    sessions: Optional[Mapping[str, Any]] = None,
    engine_up: bool = False,
    settings: Any = None,
) -> List[Dict[str, Any]]:
    """Ops-grade all-station now-playing table (Admin Overview / Stations).

    Richer than household On now: every station, next wall-clock start, stream /
    lineup health chip, and a soft guide/stream skew warning when ``now.stop``
    overruns the next ``start``.
    """
    from projectionist.live_channels.airing_why import station_airing_why
    snap_by_id: Dict[str, Mapping[str, Any]] = {}
    for channel in snapshot.get("channels") or []:
        if not isinstance(channel, Mapping):
            continue
        cid = str(channel.get("id") or "").strip()
        if cid:
            snap_by_id[cid] = channel

    lineup_by_id: Dict[str, int] = {}
    for row in (lineup_health or {}).get("channels") or []:
        if not isinstance(row, Mapping):
            continue
        cid = str(row.get("id") or "").strip()
        if not cid:
            continue
        try:
            lineup_by_id[cid] = int(row.get("total_programs") or 0)
        except (TypeError, ValueError):
            lineup_by_id[cid] = 0

    sessions_by_id: Dict[str, int] = {}
    for row in (sessions or {}).get("channels") or []:
        if not isinstance(row, Mapping):
            continue
        cid = str(row.get("channel_id") or row.get("id") or "").strip()
        if not cid:
            continue
        try:
            sessions_by_id[cid] = int(row.get("connections") or 0)
        except (TypeError, ValueError):
            sessions_by_id[cid] = 0

    # Prefer the Tunarr station list so idle / empty lineups still appear.
    station_list: List[Mapping[str, Any]] = []
    if channels:
        station_list = [ch for ch in channels if isinstance(ch, Mapping)]
    if not station_list:
        station_list = list(snap_by_id.values())

    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for station in station_list:
        cid = str(station.get("id") or station.get("uuid") or "").strip()
        if not cid or cid in seen:
            continue
        seen.add(cid)
        snap = snap_by_id.get(cid) or {}
        now = snap.get("now") if isinstance(snap.get("now"), Mapping) else None
        nxt = snap.get("next") if isinstance(snap.get("next"), Mapping) else None
        name = str(
            station.get("name") or snap.get("name") or "Channel"
        ).strip() or "Channel"
        number = station.get("number")
        if number is None:
            number = snap.get("number")
        now_title = str((now or {}).get("title") or "").strip()
        now_kind = now_kind_for_title(now_title)
        next_title = str((nxt or {}).get("title") or "").strip()
        next_kind = now_kind_for_title(next_title)
        next_start = (nxt or {}).get("start") if nxt else None
        ends_at = (now or {}).get("ends_at") if now else None
        warning = ""
        try:
            if (
                ends_at is not None
                and next_start is not None
                and float(ends_at) > float(next_start) + 1.0
            ):
                warning = "padded_stop"
        except (TypeError, ValueError):
            warning = ""
        connections = int(sessions_by_id.get(cid) or 0)
        lineup_total = lineup_by_id.get(cid)
        health = _station_health_chip(
            engine_up=engine_up,
            now=now,
            lineup_programs=lineup_total,
            now_kind=now_kind,
        )
        why = station_airing_why(settings, cid) if settings is not None else ""
        rows.append(
            {
                "id": cid,
                "name": name,
                "number": number,
                "now_title": now_title or None,
                "now_kind": now_kind or None,
                "title": now_title or None,  # alias for airing-row consumers
                "percent": (now or {}).get("percent") if now else None,
                "seconds_elapsed": (now or {}).get("seconds_elapsed") if now else None,
                "seconds_remaining": (now or {}).get("seconds_remaining") if now else None,
                "started_at": (now or {}).get("started_at") if now else None,
                "ends_at": ends_at,
                "is_paused": bool((now or {}).get("is_paused")) if now else False,
                "next_title": next_title or None,
                "next_kind": next_kind or None,
                "next_start": next_start,
                "health": health,
                "stream_connections": connections,
                "lineup_programs": lineup_total,
                "warning": warning or None,
                "airing_why": why or None,
            }
        )

    def sort_key(row: Mapping[str, Any]) -> tuple:
        num = row.get("number")
        try:
            num_key = int(num) if num is not None else 10**9
        except (TypeError, ValueError):
            num_key = 10**9
        return (num_key, str(row.get("name") or ""))

    rows.sort(key=sort_key)
    return rows


def build_live_channels_status(settings: Any) -> Dict[str, Any]:
    """Flag + Tunarr reachability + docker/preflight snapshots for the wizard."""
    features = getattr(settings, "features", None)
    enabled = bool(getattr(features, "live_channels_enabled", False))
    tunarr = getattr(settings, "tunarr", None)
    url = str(getattr(tunarr, "url", "") or "").strip() if tunarr else ""
    image_tag = str(getattr(tunarr, "image_tag", "") or "").strip() if tunarr else ""
    last_publish_at = str(getattr(tunarr, "last_publish_at", "") or "") if tunarr else ""
    last_error = str(getattr(tunarr, "last_error", "") or "") if tunarr else ""
    plex_pass_confirmed = bool(getattr(tunarr, "plex_pass_confirmed", False)) if tunarr else False
    last_guide_attach_at = (
        str(getattr(tunarr, "last_guide_attach_at", "") or "") if tunarr else ""
    )
    last_guide_attach_ok = (
        bool(getattr(tunarr, "last_guide_attach_ok", False)) if tunarr else False
    )
    last_guide_attach_message = (
        str(getattr(tunarr, "last_guide_attach_message", "") or "") if tunarr else ""
    )
    last_guide_attach_dvr_key = (
        str(getattr(tunarr, "last_guide_attach_dvr_key", "") or "") if tunarr else ""
    )

    reachability: Dict[str, Any]
    channel_count = 0
    channels: List[Dict[str, Any]] = []
    listed_raw: List[Mapping[str, Any]] = []
    airing: List[Dict[str, Any]] = []
    on_now_snap: Dict[str, Any] = {"channels": []}
    sessions = summarize_sessions({})
    guide_status: Dict[str, Any] = {}
    media_libraries: Dict[str, Any] = {"ok": False, "libraries": []}
    lineup_health: Dict[str, Any] = {
        "channel_count": 0,
        "filled_count": 0,
        "empty_count": 0,
        "channels": [],
        "playable": False,
    }
    client: Optional[TunarrClient] = None
    if url:
        reachability = tunarr_reachable(url)
        if reachability.get("reachable"):
            try:
                client = TunarrClient(url, timeout=8)
                listed = client.list_channels()
                listed_raw = [ch for ch in listed if isinstance(ch, Mapping)]
                channel_count = len(listed_raw)
                from projectionist.live_channels.filler import (
                    channel_has_continuity,
                    enrich_channels_with_filler_collections,
                    find_continuity_filler_list,
                )
                from projectionist.live_channels.publish import (
                    resolve_media_scope,
                    resolve_subtitles_enabled,
                    station_craft_snapshot,
                )

                continuity_fid = str(
                    getattr(tunarr, "continuity_filler_list_id", "") or ""
                )
                enriched = enrich_channels_with_filler_collections(
                    client, listed_raw[:40]
                )
                # Prefer live Continuity list id over a stale settings cache.
                try:
                    live_list = find_continuity_filler_list(client)
                    if live_list and live_list.get("id"):
                        continuity_fid = str(live_list.get("id") or continuity_fid)
                except Exception:  # noqa: BLE001
                    pass

                channels = []
                for ch in enriched:
                    cid = str(ch.get("id") or ch.get("uuid") or "")
                    cols = ch.get("fillerCollections") or []
                    # Prefer live Tunarr flag; fall back to Projectionist station_meta.
                    if "subtitlesEnabled" in ch:
                        subs_on = bool(ch.get("subtitlesEnabled"))
                    else:
                        subs_on = resolve_subtitles_enabled(settings, channel_id=cid)
                    craft = station_craft_snapshot(settings, cid)
                    channels.append(
                        {
                            "id": cid,
                            "name": ch.get("name"),
                            "number": ch.get("number"),
                            "has_continuity": channel_has_continuity(
                                ch, filler_list_id=continuity_fid
                            ),
                            "filler_collections_count": (
                                len(cols) if isinstance(cols, list) else 0
                            ),
                            "guide_flex_title": str(ch.get("guideFlexTitle") or ""),
                            "media_scope": resolve_media_scope(
                                settings, channel_id=cid, default="both"
                            ),
                            "subtitles_enabled": subs_on,
                            "source": craft.get("source") or "",
                            "motif": craft.get("motif") or "",
                            "cluster_tag": craft.get("cluster_tag") or "",
                            "collection_id": craft.get("collection_id") or "",
                            "collection_title": craft.get("collection_title") or "",
                            "programming_mode": craft.get("programming_mode") or "",
                            "craft_filters": dict(craft.get("craft_filters") or {}),
                            "youth_safe": bool(craft.get("youth_safe")),
                        }
                    )
            except Exception:  # noqa: BLE001
                client = None
            if client is not None:
                try:
                    sessions = summarize_sessions(client.list_sessions())
                except Exception:  # noqa: BLE001
                    sessions = summarize_sessions({})
                try:
                    guide_status = dict(client.get_guide_status() or {})
                except Exception:  # noqa: BLE001
                    guide_status = {}
                try:
                    on_now_snap = build_on_now_snapshot(settings, client=client)
                    airing = airing_rows_from_snapshot(on_now_snap)
                except Exception:  # noqa: BLE001
                    airing = []
                    on_now_snap = {"channels": []}
                try:
                    media_libraries = _media_library_index(client)
                except Exception:  # noqa: BLE001
                    media_libraries = {"ok": False, "libraries": []}
                try:
                    lineup_health = _lineup_health(client, listed_raw)
                except Exception:  # noqa: BLE001
                    pass
    else:
        reachability = {"reachable": False, "error": "Tunarr URL is not configured"}

    docker = lifecycle_from_settings(settings).status().to_dict()
    plex_pass = check_plex_pass(
        settings=settings,
        owner_confirmed=True if plex_pass_confirmed else None,
    )

    facing = resolve_plex_facing_tunarr_base(settings)
    guide_url = xmltv_url(str(facing.get("base_url") or ""))
    xmltv = _xmltv_programme_stats(guide_url)
    existing_livetv = probe_existing_plex_livetv(settings)
    plex_mapping: Dict[str, Any] = {
        "ok": False,
        "hdhr_ok": False,
        "device_present": False,
        "mapped": int(getattr(tunarr, "last_plex_mapped", 0) or 0) if tunarr else 0,
        "expected": int(getattr(tunarr, "last_plex_expected", 0) or 0) if tunarr else 0,
        "message": str(getattr(tunarr, "last_plex_sync_message", "") or "") if tunarr else "",
    }
    try:
        plex_mapping = probe_plex_tunarr_mapping(settings)
    except Exception as error:  # noqa: BLE001
        plex_mapping["message"] = str(error)[:200]

    device_status = str(plex_mapping.get("device_status") or "")
    tuner_alive = bool(plex_mapping.get("device_present")) and device_status.lower() != "dead"
    guide_ok = bool(last_guide_attach_ok and xmltv.get("ok"))

    stream_warm: Dict[str, Any] = {"kept_hot": 0, "last_run_at": None, "ok": None, "message": ""}
    try:
        from projectionist.live_channels.stream_warm import get_stream_warm_scheduler

        warm_status = get_stream_warm_scheduler().last_status()
        last_warm = dict(warm_status.get("last_result") or {})
        stream_warm = {
            "kept_hot": int(last_warm.get("count_warmed_ok") or 0),
            "last_run_at": warm_status.get("last_run_at"),
            "ok": last_warm.get("ok"),
            "message": str(last_warm.get("message") or ""),
        }
    except Exception:  # noqa: BLE001
        pass

    guide_index = {
        "xmltv_url": guide_url,
        "xmltv": xmltv,
        "tunarr_guide_status": guide_status,
        "media_libraries": media_libraries,
        "lineup": lineup_health,
        "plex_livetv": {
            "status": existing_livetv.get("status"),
            "message": existing_livetv.get("message") or "",
            "device_count": existing_livetv.get("device_count"),
            "hdhr_ok": plex_mapping.get("hdhr_ok"),
            "device_present": plex_mapping.get("device_present"),
            "mapped": plex_mapping.get("mapped"),
            "expected": plex_mapping.get("expected"),
            "device_status": plex_mapping.get("device_status"),
            "device_title": plex_mapping.get("device_title"),
            "mapping_ok": plex_mapping.get("ok"),
            "mapping_message": plex_mapping.get("message") or "",
            "guide_ok": guide_ok,
            "tuner_alive": tuner_alive,
        },
        "last_attach": {
            "at": last_guide_attach_at or None,
            "ok": last_guide_attach_ok,
            "message": last_guide_attach_message,
            "dvr_key": last_guide_attach_dvr_key or None,
            "mapped": plex_mapping.get("mapped"),
            "expected": plex_mapping.get("expected"),
        },
        "ready_for_plex": bool(
            lineup_health.get("playable")
            and xmltv.get("ok")
            and int(xmltv.get("content_programme_count") or 0) > 0
        ),
        "owner_hint": (
            "Lineups have real titles — open Plex Live TV Guide, or click Attach Tunarr "
            "guide in Plex again if the grid is still empty (reload can take a minute)."
            if lineup_health.get("playable")
            and int(xmltv.get("content_programme_count") or 0) > 0
            else (
                "Stations exist but lineups are empty — Publish starters again (fills "
                "from your Plex library after Tunarr finishes scanning)."
                if channel_count and lineup_health.get("empty_count")
                else (
                    "Enable Live Channels, start the engine, then Propose / Publish "
                    "starter stations."
                    if not channel_count
                    else "Waiting on Tunarr library scan or guide attach."
                )
            )
        ),
    }

    sidecar_up = bool(reachability.get("reachable")) or docker.get("status") == "running"

    continuity: Dict[str, Any] = {
        "ok": False,
        "path_count": 0,
        "checks": [],
    }
    try:
        from projectionist.live_channels.filler import continuity_installation_status

        continuity = continuity_installation_status(client, settings)
    except Exception as error:  # noqa: BLE001
        continuity = {"ok": False, "error": str(error)[:200], "checks": []}

    icon_probe: Dict[str, Any] = {"ok": False, "url": "", "message": ""}
    try:
        from projectionist.live_channels.publish import (
            probe_icon_url,
            resolve_channel_icon_url,
        )

        icon_url = resolve_channel_icon_url(settings)
        icon_probe = probe_icon_url(icon_url) if icon_url else {
            "ok": False,
            "url": "",
            "message": "No plex-facing Tunarr icon base (set tunarr.public_url / HOST_IP).",
        }
    except Exception as error:  # noqa: BLE001
        icon_probe = {"ok": False, "url": "", "message": str(error)[:200]}

    now_playing = owner_now_playing_rows(
        on_now_snap,
        channels=channels or listed_raw,
        lineup_health=lineup_health,
        sessions=sessions,
        engine_up=sidecar_up,
        settings=settings,
    )

    return {
        "live_channels_enabled": enabled,
        "broadcast": {
            "sidecar_up": sidecar_up,
            "channel_count": channel_count,
            "last_publish_at": last_publish_at or None,
            "last_error": last_error,
            "airing_count": len(airing),
            "stream_connections": sessions.get("total_connections") or 0,
            "lineup_playable": bool(lineup_health.get("playable")),
            "xmltv_programme_count": int(xmltv.get("programme_count") or 0),
            "guide_ok": guide_ok,
            "tuner_alive": tuner_alive,
        },
        "channels": channels,
        "channel_count": channel_count,
        "airing": airing,
        "now_playing": now_playing,
        "sessions": sessions,
        "guide_status": guide_status,
        "guide_index": guide_index,
        "continuity": continuity,
        "last_publish_at": last_publish_at or None,
        "last_error": last_error,
        "tunarr": {
            "url": url,
            "url_configured": bool(url),
            "image_tag": image_tag or "chrisbenincasa/tunarr:1.3.9",
            "docker_orchestration": orchestration_enabled(settings),
            "docker_socket_available": docker_socket_available(),
            "reachability": reachability,
            "docker": docker,
            "plex_pass_confirmed": plex_pass_confirmed,
            "volume_path": str(getattr(tunarr, "volume_path", "") or "tunarr") if tunarr else "tunarr",
            "channel_number_base": int(getattr(tunarr, "channel_number_base", 100) or 100)
            if tunarr
            else 100,
            "filler_binds": list(getattr(tunarr, "filler_binds", None) or []) if tunarr else [],
            "media_binds": list(getattr(tunarr, "media_binds", None) or []) if tunarr else [],
            "pad_flex_max_minutes": int(
                getattr(tunarr, "pad_flex_max_minutes", 15) or 15
            )
            if tunarr
            else 15,
            "last_guide_attach_at": last_guide_attach_at or None,
            "last_guide_attach_ok": last_guide_attach_ok,
            "last_guide_attach_message": last_guide_attach_message,
            "last_guide_attach_dvr_key": last_guide_attach_dvr_key or None,
        },
        "icon_probe": icon_probe,
        "plex_pass": plex_pass,
        "stream_warm": stream_warm,
    }
