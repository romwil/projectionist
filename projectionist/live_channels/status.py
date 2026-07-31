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
            }
        )
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
                from projectionist.live_channels.publish import resolve_media_scope

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
                    snap = build_on_now_snapshot(settings, client=client)
                    airing = airing_rows_from_snapshot(snap)
                except Exception:  # noqa: BLE001
                    airing = []
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
        },
        "channels": channels,
        "channel_count": channel_count,
        "airing": airing,
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
    }
