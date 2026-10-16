"""Lineup access for channel publish. Reads and writes ``live_lineup.json``.

This is not an HTTP client. Guide and playback never call out to a broadcast
process; publish stores stations in Projectionist's own file.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Mapping, Optional

from projectionist.live_channels.native_schedule import (
    ensure_schedule,
    load_schedule,
    save_schedule,
)


class LocalLineupClient:
    """Duck-typed stand-in for the removed broadcast HTTP client."""

    def __init__(self, settings: Any = None) -> None:
        self.settings = settings
        self.base_url = ""
        self.timeout = 8

    def _load(self) -> Dict[str, Any]:
        doc = ensure_schedule(self.settings)
        channels = doc.get("channels")
        if not isinstance(channels, dict):
            doc["channels"] = {}
        return doc

    def _save(self, doc: Mapping[str, Any]) -> None:
        save_schedule(doc, self.settings)

    def _row(self, channel: Mapping[str, Any]) -> Dict[str, Any]:
        cid = str(channel.get("id") or "")
        return {
            "id": cid,
            "uuid": cid,
            "name": channel.get("name"),
            "number": channel.get("number"),
            "guideFlexTitle": channel.get("guide_flex_title") or "",
            "icon": {"path": channel.get("icon_url") or ""},
            "startTime": channel.get("start_time_ms"),
        }

    def list_channels(self) -> List[Dict[str, Any]]:
        doc = self._load()
        channels = doc.get("channels") or {}
        return [self._row(ch) for ch in channels.values() if isinstance(ch, Mapping)]

    def get_channel(self, channel_id: str) -> Dict[str, Any]:
        doc = self._load()
        channel = (doc.get("channels") or {}).get(str(channel_id or "").strip())
        if not isinstance(channel, Mapping):
            raise ValueError(f"Channel not found: {channel_id}")
        return self._row(channel)

    def create_channel(self, body: Mapping[str, Any]) -> Dict[str, Any]:
        doc = self._load()
        cid = str(uuid.uuid4())
        name = str(body.get("name") or "Channel").strip() or "Channel"
        try:
            number = int(body.get("number") or 0)
        except (TypeError, ValueError):
            number = 0
        icon = body.get("icon")
        icon_url = ""
        if isinstance(icon, Mapping):
            icon_url = str(icon.get("path") or icon.get("url") or "")
        channel = {
            "id": cid,
            "name": name,
            "number": number or None,
            "guide_flex_title": str(body.get("guideFlexTitle") or f"{name} · Up next"),
            "icon_url": icon_url,
            "start_time_ms": int(time.time() * 1000),
            "items": [],
        }
        doc.setdefault("channels", {})[cid] = channel
        self._save(doc)
        return self._row(channel)

    def update_channel(self, channel_id: str, body: Mapping[str, Any]) -> Dict[str, Any]:
        doc = self._load()
        cid = str(channel_id or "").strip()
        channels = doc.setdefault("channels", {})
        current = channels.get(cid)
        if not isinstance(current, Mapping):
            raise ValueError(f"Channel not found: {cid}")
        updated = dict(current)
        if body.get("name"):
            updated["name"] = str(body.get("name"))
        if body.get("number") is not None:
            try:
                updated["number"] = int(body.get("number") or 0) or updated.get("number")
            except (TypeError, ValueError):
                pass
        if body.get("guideFlexTitle"):
            updated["guide_flex_title"] = str(body.get("guideFlexTitle"))
        icon = body.get("icon")
        if isinstance(icon, Mapping) and (icon.get("path") or icon.get("url")):
            updated["icon_url"] = str(icon.get("path") or icon.get("url") or "")
        channels[cid] = updated
        self._save(doc)
        return self._row(updated)

    def delete_channel(self, channel_id: str) -> Dict[str, Any]:
        doc = load_schedule(self.settings)
        cid = str(channel_id or "").strip()
        channels = dict(doc.get("channels") or {})
        channels.pop(cid, None)
        doc["channels"] = channels
        self._save(doc)
        return {"ok": True, "id": cid}

    def set_channel_programming(self, channel_id: str, body: Mapping[str, Any]) -> Dict[str, Any]:
        doc = self._load()
        cid = str(channel_id or "").strip()
        channels = doc.setdefault("channels", {})
        current = channels.get(cid)
        if not isinstance(current, Mapping):
            raise ValueError(f"Channel not found: {cid}")
        updated = dict(current)
        items: List[Dict[str, Any]] = []
        lineup = body.get("lineup") if isinstance(body, Mapping) else None
        for raw in lineup or []:
            if not isinstance(raw, Mapping):
                continue
            kind = str(raw.get("type") or "").strip().lower()
            try:
                duration = int(raw.get("duration") or raw.get("durationMs") or 0)
            except (TypeError, ValueError):
                duration = 0
            if duration <= 0:
                continue
            if kind in {"flex", "filler", "offline", "continuity", "commercial"} or kind != "content":
                items.append({"type": "flex", "duration_ms": duration})
                continue
            items.append(
                {
                    "type": "content",
                    "duration_ms": duration,
                    "program_id": str(raw.get("id") or ""),
                    "title": str(raw.get("title") or ""),
                    "plex_rating_key": str(
                        raw.get("plex_rating_key")
                        or raw.get("ratingKey")
                        or raw.get("externalKey")
                        or ""
                    ),
                }
            )
        updated["items"] = items
        if not updated.get("start_time_ms"):
            updated["start_time_ms"] = int(time.time() * 1000)
        channels[cid] = updated
        self._save(doc)
        return {"ok": True, "channel_id": cid, "count": len(items)}

    def get_channel_programming(self, channel_id: str) -> Dict[str, Any]:
        doc = self._load()
        channel = (doc.get("channels") or {}).get(str(channel_id or "").strip()) or {}
        lineup = []
        for item in channel.get("items") or []:
            if not isinstance(item, Mapping):
                continue
            if item.get("type") == "flex":
                lineup.append({"type": "flex", "duration": item.get("duration_ms")})
            else:
                lineup.append(
                    {
                        "type": "content",
                        "id": item.get("program_id") or "",
                        "duration": item.get("duration_ms"),
                        "title": item.get("title") or "",
                    }
                )
        return {"type": "manual", "lineup": lineup}

    def default_transcode_config_id(self) -> str:
        return "projectionist"

    def check(self) -> Dict[str, Any]:
        doc = self._load()
        count = len(doc.get("channels") or {})
        return {"ok": True, "channel_count": count}

    def list_sessions(self) -> Dict[str, Any]:
        return {}

    def get_guide_status(self) -> Dict[str, Any]:
        return {"guideTimes": [], "source": "projectionist"}

    def ensure_xmltv_programming_hours(self, hours: int) -> Dict[str, Any]:
        return {"changed": False, "programmingHours": int(hours or 0), "source": "projectionist"}

    def put_xmltv_settings(self, body: Mapping[str, Any]) -> Dict[str, Any]:
        return dict(body or {})

    def get_now_playing(self, channel_id: str) -> Optional[Dict[str, Any]]:
        del channel_id
        return None

    def get_all_channel_guides(self, start: Any, end: Any) -> Dict[str, Any]:
        del start, end
        return {}

    def stop_channel_sessions(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        del args, kwargs
        return {}

    def list_media_sources(self) -> List[Dict[str, Any]]:
        return []

    def list_media_source_libraries(self, media_source_id: str = "") -> List[Dict[str, Any]]:
        del media_source_id
        return []

    def list_library_programs(self, library_id: str = "") -> List[Dict[str, Any]]:
        del library_id
        return []

    def list_program_descendants(self, program_id: str = "") -> List[Dict[str, Any]]:
        del program_id
        return []

    def search_programs(self, *args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
        del args, kwargs
        return []

    def list_filler_lists(self) -> List[Dict[str, Any]]:
        return []

    def create_filler_list(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        del args, kwargs
        return {"id": ""}

    def update_filler_list(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        del args, kwargs
        return {}

    def get_filler_list_programs(self, *args: Any, **kwargs: Any) -> List[Dict[str, Any]]:
        del args, kwargs
        return []

    def set_library_enabled(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        del args, kwargs
        return {}

    def create_media_source(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        del args, kwargs
        return {"id": ""}

    def update_media_source(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        del args, kwargs
        return {}

    def scan_library(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        del args, kwargs
        return {}

    def get_library_scan_status(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        del args, kwargs
        return {"inProgress": False}

    def ensure_plex_stream_path_direct(self, *args: Any, **kwargs: Any) -> Dict[str, Any]:
        del args, kwargs
        return {"ok": True, "skipped": True}

    def fetch_debug_logs(self, *args: Any, **kwargs: Any) -> str:
        del args, kwargs
        return ""

    def version(self) -> Dict[str, Any]:
        return {}

    def health(self) -> Dict[str, Any]:
        return {"ok": True, "source": "projectionist"}
