"""Tunarr OpenAPI client (Live Channels broadcast engine).

Projectionist is the sole management plane — Tunarr UI is not a supported
workflow. This client maps Coax-style channel-config vocabulary onto Tunarr's
REST API under ``{base}/api``:

| Coax / product vocabulary | Tunarr API |
|---------------------------|------------|
| Library / media server wire | ``GET/POST /media-sources`` |
| Station / channel | ``GET/POST /channels``, ``PUT/DELETE /channels/{id}`` |
| Lineup / programming | ``GET/POST /channels/{id}/programming`` |
| Shuffle / Chaos schedule | ``POST /channels/{id}/schedule-slots`` |
| Gap fillers / commercials | ``GET/POST /filler-lists`` |
| Now playing / guide | ``GET /channels/{id}/now_playing``, ``GET /guide/channels`` |
| Stream sessions | ``GET /sessions``, ``GET /channels/{id}/sessions`` |
| Guide cache status | ``GET /guide/status`` |
| Health / version | ``GET /system/health``, ``GET /version`` |

Airing progress is **derived** from ``TvGuideProgram`` ``start`` / ``stop`` /
``duration`` (ms) — Tunarr has no dedicated percent field. Media-source scan
progress is internal (events), not a stable public poll API.

No Tunarr admin auth today — keep the admin UI off the LAN; call only from
Projectionist on the trusted host network.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Union
from urllib.parse import urlencode

from projectionist.connectors.http import request_json
from projectionist.logging_config import sanitize_url


def _iso_utc(value: Union[datetime, float, int, str]) -> str:
    """Normalize a timestamp-ish value to an ISO-8601 UTC string for Tunarr guide queries."""
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, (int, float)):
        ts = float(value)
        # Tunarr / JS often use milliseconds.
        if ts > 1e12:
            ts = ts / 1000.0
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    text = str(value or "").strip()
    if not text:
        raise ValueError("timestamp is required")
    return text


class TunarrClient:
    """Thin HTTP client for Tunarr 1.3.x OpenAPI routes."""

    def __init__(self, base_url: str, *, timeout: int = 30) -> None:
        cleaned = str(base_url or "").strip().rstrip("/")
        if not cleaned:
            raise ValueError("Tunarr base URL is required")
        self.base_url = cleaned
        self.timeout = timeout

    def _api_url(self, path: str) -> str:
        cleaned = path if path.startswith("/") else f"/{path}"
        return f"{self.base_url}/api{cleaned}"

    def health(self) -> Mapping[str, Any]:
        """Return Tunarr system health map (``GET /api/system/health``)."""
        payload = request_json(
            self._api_url("/system/health"),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Tunarr /system/health")
        return payload

    def version(self) -> Mapping[str, Any]:
        """Return Tunarr / ffmpeg / node version info."""
        payload = request_json(self._api_url("/version"), timeout=self.timeout)
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Tunarr /version")
        return payload

    def check(self) -> Mapping[str, Any]:
        """Connectivity probe used by admin status / wizard preflight."""
        health = self.health()
        version: Mapping[str, Any] = {}
        try:
            version = self.version()
        except Exception:  # noqa: BLE001
            version = {}
        return {
            "ok": True,
            "health": health,
            "version": version,
            "tunarr_version": str(version.get("tunarr") or ""),
        }

    def list_media_sources(self) -> List[Mapping[str, Any]]:
        payload = request_json(self._api_url("/media-sources"), timeout=self.timeout)
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, Mapping)]

    def create_media_source(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        """Create a media source (Plex/Jellyfin/Emby/local). Body is Tunarr schema."""
        payload = request_json(
            self._api_url("/media-sources"),
            method="POST",
            body=dict(body),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Tunarr create media-source")
        return payload

    def update_media_source(
        self, media_source_id: str, body: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Update a media source (``PUT /api/media-sources/{id}``)."""
        msid = str(media_source_id or "").strip()
        if not msid:
            raise ValueError("media_source_id is required")
        payload = request_json(
            self._api_url(f"/media-sources/{msid}"),
            method="PUT",
            body=dict(body),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Tunarr update media-source")
        return payload

    def list_media_source_libraries(self, media_source_id: str) -> List[Mapping[str, Any]]:
        """List libraries for a media source (``GET /media-sources/{id}/libraries``)."""
        msid = str(media_source_id or "").strip()
        if not msid:
            raise ValueError("media_source_id is required")
        payload = request_json(
            self._api_url(f"/media-sources/{msid}/libraries"),
            timeout=self.timeout,
        )
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, Mapping)]

    def set_library_enabled(
        self, media_source_id: str, library_id: str, *, enabled: bool = True
    ) -> Mapping[str, Any]:
        """Enable/disable a Tunarr media library (required before scan/programming)."""
        msid = str(media_source_id or "").strip()
        lid = str(library_id or "").strip()
        if not msid or not lid:
            raise ValueError("media_source_id and library_id are required")
        payload = request_json(
            self._api_url(f"/media-sources/{msid}/libraries/{lid}"),
            method="PUT",
            body={"enabled": bool(enabled)},
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Tunarr set library enabled")
        return payload

    def scan_library(
        self,
        media_source_id: str,
        library_id: str,
        *,
        force: bool = True,
    ) -> Mapping[str, Any]:
        """Kick a library scan (``POST …/libraries/{id}/scan``). Returns quickly (202)."""
        msid = str(media_source_id or "").strip()
        lid = str(library_id or "").strip()
        if not msid or not lid:
            raise ValueError("media_source_id and library_id are required")
        query = urlencode({"forceScan": "true" if force else "false"})
        payload = request_json(
            f"{self._api_url(f'/media-sources/{msid}/libraries/{lid}/scan')}?{query}",
            method="POST",
            timeout=self.timeout,
        )
        return payload if isinstance(payload, dict) else {}

    def get_library_scan_status(
        self, media_source_id: str, library_id: str
    ) -> Mapping[str, Any]:
        """Poll scan progress (``GET /media-sources/{ms}/{lib}/status``)."""
        msid = str(media_source_id or "").strip()
        lid = str(library_id or "").strip()
        if not msid or not lid:
            raise ValueError("media_source_id and library_id are required")
        payload = request_json(
            self._api_url(f"/media-sources/{msid}/{lid}/status"),
            timeout=self.timeout,
        )
        return payload if isinstance(payload, dict) else {}

    def list_library_programs(self, library_id: str) -> List[Mapping[str, Any]]:
        """Programs already indexed for a library (``GET /media-libraries/{id}/programs``)."""
        lid = str(library_id or "").strip()
        if not lid:
            raise ValueError("library_id is required")
        payload = request_json(
            self._api_url(f"/media-libraries/{lid}/programs"),
            timeout=max(self.timeout, 60),
        )
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, Mapping)]

    def search_programs(
        self,
        query: str = "",
        *,
        limit: int = 40,
        page: int = 1,
        media_source_id: str = "",
        library_id: str = "",
    ) -> Mapping[str, Any]:
        """Search Tunarr's program index (``POST /programs/search``)."""
        body: Dict[str, Any] = {
            "query": {"query": str(query or "")},
            "limit": max(1, min(int(limit or 40), 200)),
            "page": max(1, int(page or 1)),
        }
        if media_source_id:
            body["mediaSourceId"] = str(media_source_id).strip()
        if library_id:
            body["libraryId"] = str(library_id).strip()
        payload = request_json(
            self._api_url("/programs/search"),
            method="POST",
            body=body,
            timeout=self.timeout,
        )
        return payload if isinstance(payload, dict) else {"results": [], "totalHits": 0}

    def list_channels(self) -> List[Mapping[str, Any]]:
        payload = request_json(self._api_url("/channels"), timeout=self.timeout)
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, Mapping)]

    def list_transcode_configs(self) -> List[Mapping[str, Any]]:
        """Return Tunarr transcode profiles (``GET /api/transcode_configs``)."""
        payload = request_json(
            self._api_url("/transcode_configs"), timeout=self.timeout
        )
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, Mapping)]

    def default_transcode_config_id(self) -> str:
        """Prefer the profile marked ``isDefault``, else the first config id."""
        configs = self.list_transcode_configs()
        for item in configs:
            if item.get("isDefault"):
                cid = str(item.get("id") or "").strip()
                if cid:
                    return cid
        for item in configs:
            cid = str(item.get("id") or "").strip()
            if cid:
                return cid
        raise RuntimeError(
            "Tunarr has no transcode configs; cannot create channels until one exists"
        )

    def fetch_debug_logs(self, *, line_limit: int = 200) -> str:
        """Download recent Tunarr logs (``GET /api/system/debug/logs?download=true``).

        Without ``download=true`` Tunarr streams SSE indefinitely; the download
        variant returns a finite ``text/plain`` attachment.
        """
        limit = max(1, min(int(line_limit or 200), 2000))
        query = urlencode({"download": "true", "lineLimit": limit})
        url = f"{self._api_url('/system/debug/logs')}?{query}"
        safe_url = sanitize_url(url)
        request = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")[:240]
            raise RuntimeError(
                f"HTTP {error.code} from {safe_url}: {detail}"
            ) from error
        except Exception as error:  # noqa: BLE001
            raise RuntimeError(f"Tunarr logs request failed: {error}") from error
        lines = raw.splitlines()
        if len(lines) > limit:
            lines = lines[-limit:]
        return "\n".join(lines)

    def create_channel(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        """Create a channel. Prefer ``{"type": "new", "channel": {...}}`` shape."""
        payload = request_json(
            self._api_url("/channels"),
            method="POST",
            body=dict(body),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Tunarr create channel")
        return payload

    def update_channel(self, channel_id: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        """Update channel metadata (``PUT /api/channels/{id}``)."""
        cid = str(channel_id or "").strip()
        if not cid:
            raise ValueError("channel_id is required")
        payload = request_json(
            self._api_url(f"/channels/{cid}"),
            method="PUT",
            body=dict(body),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Tunarr update channel")
        return payload

    def delete_channel(self, channel_id: str) -> None:
        """Delete a channel (``DELETE /api/channels/{id}``). Empty 200 body is OK."""
        cid = str(channel_id or "").strip()
        if not cid:
            raise ValueError("channel_id is required")
        request_json(
            self._api_url(f"/channels/{cid}"),
            method="DELETE",
            timeout=self.timeout,
        )

    def get_channel_programming(self, channel_id: str) -> Mapping[str, Any]:
        cid = str(channel_id or "").strip()
        if not cid:
            raise ValueError("channel_id is required")
        payload = request_json(
            self._api_url(f"/channels/{cid}/programming"),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Tunarr get programming")
        return payload

    def set_channel_programming(
        self, channel_id: str, body: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Replace a channel lineup (lineup / collection-channel publish)."""
        cid = str(channel_id or "").strip()
        if not cid:
            raise ValueError("channel_id is required")
        payload = request_json(
            self._api_url(f"/channels/{cid}/programming"),
            method="POST",
            body=dict(body),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Tunarr set programming")
        return payload

    def list_filler_lists(self) -> List[Mapping[str, Any]]:
        payload = request_json(self._api_url("/filler-lists"), timeout=self.timeout)
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, Mapping)]

    def get_filler_list(self, filler_list_id: str) -> Mapping[str, Any]:
        """Fetch one filler list (``GET /api/filler-lists/{id}``)."""
        fid = str(filler_list_id or "").strip()
        if not fid:
            raise ValueError("filler_list_id is required")
        payload = request_json(
            self._api_url(f"/filler-lists/{fid}"),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Tunarr get filler-list")
        return payload

    def get_filler_list_programs(self, filler_list_id: str) -> List[Mapping[str, Any]]:
        """Programs in a filler list (``GET /api/filler-lists/{id}/programs``)."""
        fid = str(filler_list_id or "").strip()
        if not fid:
            raise ValueError("filler_list_id is required")
        payload = request_json(
            self._api_url(f"/filler-lists/{fid}/programs"),
            timeout=self.timeout,
        )
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, Mapping)]

    def create_filler_list(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        """Create a filler list (gap fillers / trailers). Stub-friendly."""
        payload = request_json(
            self._api_url("/filler-lists"),
            method="POST",
            body=dict(body),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Tunarr create filler-list")
        return payload

    def update_filler_list(
        self, filler_list_id: str, body: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Replace filler list membership (``PUT /api/filler-lists/{id}``)."""
        fid = str(filler_list_id or "").strip()
        if not fid:
            raise ValueError("filler_list_id is required")
        payload = request_json(
            self._api_url(f"/filler-lists/{fid}"),
            method="PUT",
            body=dict(body),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Tunarr update filler-list")
        return payload

    def get_all_channel_guides(
        self,
        date_from: Union[datetime, float, int, str],
        date_to: Union[datetime, float, int, str],
    ) -> Mapping[str, Any]:
        """Return guide lineups keyed by channel id (``GET /api/guide/channels``)."""
        query = urlencode(
            {
                "dateFrom": _iso_utc(date_from),
                "dateTo": _iso_utc(date_to),
            }
        )
        payload = request_json(
            f"{self._api_url('/guide/channels')}?{query}",
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            return {}
        return payload

    def get_now_playing(self, channel_id: str) -> Optional[Mapping[str, Any]]:
        """Return the program currently airing on a channel, or None if empty/404.

        Response is a ``TvGuideProgram`` (``start`` / ``stop`` / ``duration`` in ms).
        Projectionist derives elapsed/remaining/percent from those fields.
        """
        cid = str(channel_id or "").strip()
        if not cid:
            raise ValueError("channel_id is required")
        try:
            payload = request_json(
                self._api_url(f"/channels/{cid}/now_playing"),
                timeout=self.timeout,
            )
        except RuntimeError as error:
            # Tunarr returns 404 when the guide window is empty.
            if "HTTP 404" in str(error):
                return None
            raise
        if not isinstance(payload, dict):
            return None
        return payload

    def list_sessions(self) -> Mapping[str, List[Mapping[str, Any]]]:
        """Active stream sessions keyed by channel id (``GET /api/sessions``)."""
        payload = request_json(self._api_url("/sessions"), timeout=self.timeout)
        if not isinstance(payload, dict):
            return {}
        out: dict[str, List[Mapping[str, Any]]] = {}
        for key, value in payload.items():
            if not isinstance(value, list):
                continue
            out[str(key)] = [item for item in value if isinstance(item, Mapping)]
        return out

    def get_guide_status(self) -> Mapping[str, Any]:
        """Guide cache status (``GET /api/guide/status``)."""
        payload = request_json(self._api_url("/guide/status"), timeout=self.timeout)
        if not isinstance(payload, dict):
            return {}
        return payload

    def get_plex_settings(self) -> Mapping[str, Any]:
        """Plex stream access settings (``GET /api/plex-settings``)."""
        payload = request_json(self._api_url("/plex-settings"), timeout=self.timeout)
        return payload if isinstance(payload, dict) else {}

    def put_plex_settings(self, body: Mapping[str, Any]) -> Mapping[str, Any]:
        """Update Plex stream settings (``PUT /api/plex-settings``)."""
        payload = request_json(
            self._api_url("/plex-settings"),
            method="PUT",
            body=dict(body),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Tunarr PUT plex-settings")
        return payload

    def ensure_plex_stream_path_direct(self) -> Mapping[str, Any]:
        """Prefer filesystem reads when Tunarr can see library mounts.

        Tunarr 1.3.x ``streamPath`` is ``network`` | ``direct``. With media binds
        present, ``direct`` avoids mid-program HTTP seeks through Plex that stall
        cold HDHR tunes. Idempotent; never raises — returns ``ok`` / message.
        """
        try:
            current = dict(self.get_plex_settings())
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "changed": False, "error": str(error)[:200]}
        if str(current.get("streamPath") or "").strip().lower() == "direct":
            return {
                "ok": True,
                "changed": False,
                "streamPath": "direct",
                "message": "Tunarr already reads library files directly.",
            }
        body = {
            "streamPath": "direct",
            "updatePlayStatus": bool(current.get("updatePlayStatus", False)),
            "pathReplace": str(current.get("pathReplace") or ""),
            "pathReplaceWith": str(current.get("pathReplaceWith") or ""),
        }
        try:
            updated = self.put_plex_settings(body)
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "changed": False, "error": str(error)[:200]}
        return {
            "ok": True,
            "changed": True,
            "streamPath": str(updated.get("streamPath") or "direct"),
            "message": "Tunarr plex streamPath set to direct (local media mounts).",
            "settings": dict(updated),
        }


def tunarr_reachable(base_url: str, *, timeout: int = 8) -> dict[str, Any]:
    """Best-effort reachability check; never raises."""
    url = str(base_url or "").strip()
    if not url:
        return {"reachable": False, "error": "Tunarr URL is not configured"}
    try:
        client = TunarrClient(url, timeout=timeout)
        result = client.check()
        return {
            "reachable": True,
            "tunarr_version": result.get("tunarr_version") or "",
            "health": result.get("health") or {},
        }
    except Exception as error:  # noqa: BLE001
        return {"reachable": False, "error": str(error)[:240]}
