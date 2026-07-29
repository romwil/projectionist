"""Aggregate Live Channels admin status for owner API / health strip."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from projectionist.connectors.tunarr import TunarrClient, tunarr_reachable
from projectionist.live_channels.docker import (
    docker_socket_available,
    lifecycle_from_settings,
    orchestration_enabled,
)
from projectionist.live_channels.guide import build_on_now_snapshot
from projectionist.live_channels.plex_pass import check_plex_pass


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

    reachability: Dict[str, Any]
    channel_count = 0
    channels: List[Dict[str, Any]] = []
    airing: List[Dict[str, Any]] = []
    sessions = summarize_sessions({})
    guide_status: Dict[str, Any] = {}
    client: Optional[TunarrClient] = None
    if url:
        reachability = tunarr_reachable(url)
        if reachability.get("reachable"):
            try:
                client = TunarrClient(url, timeout=8)
                listed = client.list_channels()
                channel_count = len(listed)
                channels = [
                    {
                        "id": ch.get("id") or ch.get("uuid"),
                        "name": ch.get("name"),
                        "number": ch.get("number"),
                    }
                    for ch in listed[:40]
                    if isinstance(ch, dict)
                ]
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
    else:
        reachability = {"reachable": False, "error": "Tunarr URL is not configured"}

    docker = lifecycle_from_settings(settings).status().to_dict()
    plex_pass = check_plex_pass(
        settings=settings,
        owner_confirmed=True if plex_pass_confirmed else None,
    )

    sidecar_up = bool(reachability.get("reachable")) or docker.get("status") == "running"

    return {
        "live_channels_enabled": enabled,
        "broadcast": {
            "sidecar_up": sidecar_up,
            "channel_count": channel_count,
            "last_publish_at": last_publish_at or None,
            "last_error": last_error,
            "airing_count": len(airing),
            "stream_connections": sessions.get("total_connections") or 0,
        },
        "channels": channels,
        "channel_count": channel_count,
        "airing": airing,
        "sessions": sessions,
        "guide_status": guide_status,
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
        },
        "plex_pass": plex_pass,
    }
