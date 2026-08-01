"""Living-room one-liners for why a station is on the air."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from projectionist.live_channels.publish import station_meta_row


def station_airing_why(
    settings: Any,
    channel_id: str,
    *,
    meta: Optional[Mapping[str, Any]] = None,
) -> str:
    """Recipe/motif one-liner for owner now-playing + household On now.

    Prefer persisted ``station_meta``; never invent Tunarr jargon.
    """
    cid = str(channel_id or "").strip()
    row: Dict[str, Any] = {}
    if isinstance(meta, Mapping) and meta:
        row = dict(meta)
    elif cid and settings is not None:
        row = station_meta_row(settings, cid)
    if not row:
        return ""

    motif = str(row.get("motif") or "").strip()
    cluster = str(row.get("cluster_tag") or "").strip()
    collection = str(row.get("collection_title") or "").strip()
    source = str(row.get("source") or "").strip().lower()
    mode = str(row.get("programming_mode") or "").strip().lower()
    youth_safe = bool(row.get("youth_safe"))

    if motif:
        lead = f"Crafted around “{motif}”"
    elif cluster:
        lead = f"From your “{cluster}” taste cluster"
    elif collection:
        lead = f"From the “{collection}” collection"
    elif source == "youth" or youth_safe:
        lead = "Youth-safe starter station"
    elif source == "motif":
        lead = "Motif station from your library craft"
    elif source == "taste" or source == "cluster":
        lead = "Taste-cluster station"
    elif source == "collection":
        lead = "Collection station"
    elif source:
        lead = f"Crafted as a {source} station"
    else:
        return ""

    if mode == "shuffle":
        lead = f"{lead} · shuffle"
    elif mode == "sequential":
        lead = f"{lead} · in order"
    if youth_safe and "Youth-safe" not in lead:
        lead = f"{lead} · youth-safe"
    return lead[:160]


def enrich_channels_with_airing_why(
    settings: Any,
    channels: list[Mapping[str, Any]] | list,
) -> list[Dict[str, Any]]:
    """Attach ``airing_why`` to channel/on-now rows (copy; never mutate input)."""
    out: list[Dict[str, Any]] = []
    for channel in channels or []:
        if not isinstance(channel, Mapping):
            continue
        row = dict(channel)
        cid = str(row.get("id") or row.get("uuid") or "").strip()
        why = station_airing_why(settings, cid)
        if why:
            row["airing_why"] = why
        out.append(row)
    return out


def pick_youth_safe_live_station(
    settings: Any,
    channels: list[Mapping[str, Any]] | list,
) -> Optional[Dict[str, Any]]:
    """Prefer a youth_safe station_meta row that currently has something on."""
    candidates: list[Dict[str, Any]] = []
    for channel in channels or []:
        if not isinstance(channel, Mapping):
            continue
        cid = str(channel.get("id") or "").strip()
        if not cid:
            continue
        meta = station_meta_row(settings, cid)
        if not (meta.get("youth_safe") or str(meta.get("source") or "").lower() == "youth"):
            continue
        now = channel.get("now") if isinstance(channel.get("now"), Mapping) else None
        title = str((now or {}).get("title") or channel.get("now_title") or "").strip()
        candidates.append(
            {
                "id": cid,
                "name": str(channel.get("name") or "Station").strip() or "Station",
                "number": channel.get("number"),
                "now_title": title or None,
                "airing_why": station_airing_why(settings, cid, meta=meta)
                or "Youth-safe Live station",
            }
        )
    if not candidates:
        return None
    # Prefer something actually airing.
    airing = [c for c in candidates if c.get("now_title")]
    pick = airing[0] if airing else candidates[0]
    return pick
