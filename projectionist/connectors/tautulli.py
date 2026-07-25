"""Tautulli API client for Plex watch statistics."""

from __future__ import annotations

from typing import Any, List, Mapping, Optional

from projectionist.connectors.http import request_json


class TautulliClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _call(self, cmd: str, **params: Any) -> Any:
        query = "&".join(f"{key}={value}" for key, value in params.items() if value is not None)
        url = f"{self.base_url}/api/v2?apikey={self.api_key}&cmd={cmd}"
        if query:
            url = f"{url}&{query}"
        payload = request_json(url, timeout=self.timeout)
        if isinstance(payload, dict):
            return payload.get("response", {}).get("data")
        return None

    def get_libraries(self) -> List[Mapping[str, Any]]:
        data = self._call("get_libraries")
        return data if isinstance(data, list) else []

    def get_library_media_info(
        self, section_id: int, *, start: int = 0, length: int = 500
    ) -> List[Mapping[str, Any]]:
        data = self._call(
            "get_library_media_info",
            section_id=section_id,
            start=start,
            length=length,
        )
        if isinstance(data, dict):
            return data.get("data", []) if isinstance(data.get("data"), list) else []
        return data if isinstance(data, list) else []

    def get_metadata(self, rating_key: str) -> Mapping[str, Any]:
        data = self._call("get_metadata", rating_key=rating_key)
        return data if isinstance(data, dict) else {}

    def never_watched(self, section_id: int) -> List[Mapping[str, Any]]:
        items = self.get_library_media_info(section_id, length=5000)
        return [item for item in items if int(item.get("play_count") or 0) == 0]
