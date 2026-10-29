"""Icon resolve/probe/apply and channel labels for Live publish."""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Mapping, Optional, Sequence

# Historical annotations used this name for the broadcast HTTP client.
TunarrClient = Any

# Stock Tunarr mark — never push as a Plex guide logo when station art is missing.
_TUNARR_DEFAULT_ICON_SUFFIX = "/images/tunarr.png"

# Tunarr 1.3.x ``createChannelV2`` requires these channel fields (OpenAPI).
_DEFAULT_GROUP_TITLE = "Projectionist"
_DEFAULT_GUIDE_MINIMUM_DURATION_MS = 30_000
_DEFAULT_STREAM_MODE = "hls"


def is_default_tunarr_icon(url: str = "") -> bool:
    """True when ``url`` is Tunarr's stock mark (or empty)."""
    path = str(url or "").strip().lower()
    if not path:
        return True
    return path.endswith(_TUNARR_DEFAULT_ICON_SUFFIX)


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


def channel_icon_body(icon_url: str = "") -> Dict[str, Any]:
    """Tunarr channel icon object for Plex's guide column.

    Plex draws that column from the XMLTV ``<icon>`` and does not also draw
    the call sign. Tunarr inserts ``/images/tunarr.png`` whenever ``path`` is
    empty unless ``useDefaultIconFallback`` is false. That stock image
    replaces the channel number and name, and Plex often fails to paint it,
    so the column is a blank box. Publish real station art, or no icon.
    """
    path = str(icon_url or "").strip()
    if is_default_tunarr_icon(path):
        path = ""
    return {
        "path": path,
        "width": 256 if path else 0,
        "duration": 0,
        "position": "bottom-right",
        "useDefaultIconFallback": False,
    }


def channel_icon_hides_plex_label(icon: Any) -> bool:
    """True when Tunarr would emit an icon that replaces the Plex call sign."""
    if not isinstance(icon, Mapping):
        return True
    path = str(icon.get("path") or "").strip()
    if path and not is_default_tunarr_icon(path):
        lowered = path.lower()
        if (
            lowered.startswith("http://127.0.0.1")
            or lowered.startswith("http://localhost")
            or lowered.startswith("https://127.0.0.1")
            or lowered.startswith("https://localhost")
            or "host.docker.internal" in lowered
        ):
            return True
        return False
    # Empty or stock path: Tunarr still emits /images/tunarr.png unless opted out.
    return icon.get("useDefaultIconFallback") is not False


def resolve_channel_icon_url(
    settings: Any = None,
    *,
    tunarr_base: str = "",
    preferred_url: str = "",
) -> str:
    """LAN-facing icon URL for channel logos (Plex must be able to fetch it).

    Prefer ``preferred_url`` (collection / title art) when set. Do **not** fall
    back to Tunarr's stock ``/images/tunarr.png``. An empty path still publishes
    that stock logo unless ``useDefaultIconFallback`` is false — see
    ``channel_icon_body``.
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


def apply_channel_name(
    client: TunarrClient,
    channel_id: str,
    *,
    name: str,
) -> Dict[str, Any]:
    """Rename an existing Tunarr station (``PUT`` name + matching guide flex title)."""
    cid = str(channel_id or "").strip()
    new_name = str(name or "").strip()
    if not cid:
        raise ValueError("channel_id is required")
    if not new_name:
        raise ValueError("name is required")
    channel = client.get_channel(cid)
    old_name = str(channel.get("name") or "").strip()
    body = _channel_put_body(channel, name=new_name)
    flex = str(channel.get("guideFlexTitle") or "")
    if old_name and flex.startswith(old_name):
        body["guideFlexTitle"] = new_name + flex[len(old_name) :]
    elif not flex:
        body["guideFlexTitle"] = f"{new_name} · Up next"
    updated = client.update_channel(cid, body)
    resolved = str(
        (updated or {}).get("name", new_name) if isinstance(updated, Mapping) else new_name
    ).strip() or new_name
    return {
        "ok": True,
        "channel_id": cid,
        "name": resolved[:48],
        "previous_name": old_name,
    }


def ensure_channel_labels(
    client: TunarrClient,
    *,
    icon_url: str = "",
    channel_ids: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Ensure Tunarr stations have a name Plex can show in the guide column.

    Real station art is kept. Stock, empty, and loopback icons are cleared
    with ``useDefaultIconFallback`` off so XMLTV omits ``<icon>`` and Plex
    draws the call sign (``100 Mystery``) instead of a blank logo cell.
    """
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
        hides_label = channel_icon_hides_plex_label(current_icon)
        needs_name = not str(ch.get("name") or "").strip()
        if not hides_label and not needs_name:
            continue
        body = _channel_put_body(
            ch,
            name=name,
            icon=dict(icon) if hides_label else dict(current_icon or channel_icon_body("")),
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
