"""Fanart.tv API client for poster and backdrop art."""

from __future__ import annotations

from typing import Any, Mapping, Optional

from projectionist.connectors.http import request_json


class FanartClient:
    BASE = "https://webservice.fanart.tv/v3"

    def __init__(self, api_key: str, timeout: int = 30) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def movie(self, tmdb_id: int) -> Mapping[str, Any]:
        payload = request_json(
            f"{self.BASE}/movies/{tmdb_id}?api_key={self.api_key}",
            timeout=self.timeout,
        )
        return payload if isinstance(payload, dict) else {}

    def tv(self, tvdb_id: int) -> Mapping[str, Any]:
        payload = request_json(
            f"{self.BASE}/tv/{tvdb_id}?api_key={self.api_key}",
            timeout=self.timeout,
        )
        return payload if isinstance(payload, dict) else {}

    def best_poster(self, payload: Mapping[str, Any]) -> str:
        posters = payload.get("movieposter") or payload.get("tvposter") or []
        if not posters:
            return ""
        return str(posters[0].get("url") or "")

    def best_backdrop(self, payload: Mapping[str, Any]) -> str:
        backdrops = payload.get("moviebackground") or payload.get("showbackground") or []
        if not backdrops:
            return ""
        return str(backdrops[0].get("url") or "")
