"""Tunarr OpenAPI client (Live Channels broadcast engine).

Projectionist is the sole management plane — Tunarr UI is not a supported
workflow. This client maps Coax-style channel-config vocabulary onto Tunarr's
REST API under ``{base}/api``:

| Coax / product vocabulary | Tunarr API |
|---------------------------|------------|
| Library / media server wire | ``GET/POST /media-sources`` |
| Station / channel | ``GET/POST /channels`` |
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

from datetime import datetime, timezone
from typing import Any, List, Mapping, Optional, Union
from urllib.parse import urlencode

from projectionist.connectors.http import request_json


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

    def list_channels(self) -> List[Mapping[str, Any]]:
        payload = request_json(self._api_url("/channels"), timeout=self.timeout)
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, Mapping)]

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
