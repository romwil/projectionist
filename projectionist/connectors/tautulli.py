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

    def get_history(
        self,
        *,
        start: int = 0,
        length: int = 100,
        user_id: Optional[str] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
        grouping: int = 0,
        include_activity: int = 0,
    ) -> Mapping[str, Any]:
        """Paged Tautulli history. ``user_id`` is the Plex account id when present."""
        data = self._call(
            "get_history",
            start=max(0, int(start)),
            length=max(1, min(int(length), 500)),
            user_id=str(user_id).strip() if user_id is not None and str(user_id).strip() else None,
            after=str(after).strip() if after else None,
            before=str(before).strip() if before else None,
            grouping=int(grouping),
            include_activity=int(include_activity),
        )
        if isinstance(data, dict):
            rows = data.get("data")
            return {
                "data": rows if isinstance(rows, list) else [],
                "recordsFiltered": data.get("recordsFiltered"),
                "recordsTotal": data.get("recordsTotal"),
            }
        if isinstance(data, list):
            return {
                "data": data,
                "recordsFiltered": len(data),
                "recordsTotal": len(data),
            }
        return {"data": [], "recordsFiltered": 0, "recordsTotal": 0}

    def never_watched(self, section_id: int) -> List[Mapping[str, Any]]:
        items = self.get_library_media_info(section_id, length=5000)
        return [item for item in items if int(item.get("play_count") or 0) == 0]
