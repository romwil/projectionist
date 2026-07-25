"""Seerr (Overseerr / Jellyseerr) API client."""

from __future__ import annotations

import urllib.parse
from typing import Any, List, Mapping, Optional

from projectionist.connectors.http import request_json


class SeerrClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key}

    def _api_url(self, path: str) -> str:
        cleaned = path if path.startswith("/") else f"/{path}"
        return f"{self.base_url}/api/v1{cleaned}"

    def get_user(self) -> Mapping[str, Any]:
        payload = request_json(
            self._api_url("/auth/me"),
            headers=self._headers(),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Seerr /auth/me")
        return payload

    def link_plex_user(self, auth_token: str) -> Mapping[str, Any]:
        payload = request_json(
            self._api_url("/auth/plex"),
            method="POST",
            headers=self._headers(),
            body={"authToken": auth_token},
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Seerr /auth/plex")
        return payload

    def search(self, query: str, *, page: int = 1, language: str = "en") -> Mapping[str, Any]:
        params = urllib.parse.urlencode(
            {
                "query": query,
                "page": str(page),
                "language": language,
            }
        )
        payload = request_json(
            f"{self._api_url('/search')}?{params}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            return {"results": [], "page": page, "totalPages": 0, "totalResults": 0}
        return payload

    def search_movie(self, query: str, *, page: int = 1) -> List[Mapping[str, Any]]:
        return self._filter_search_results(self.search(query, page=page), media_type="movie")

    def search_tv(self, query: str, *, page: int = 1) -> List[Mapping[str, Any]]:
        return self._filter_search_results(self.search(query, page=page), media_type="tv")

    def create_request(
        self,
        media_type: str,
        media_id: int,
        *,
        tvdb_id: Optional[int] = None,
        seasons: Optional[List[int] | str] = None,
        is4k: bool = False,
        user_id: Optional[int] = None,
    ) -> Mapping[str, Any]:
        body: dict[str, Any] = {
            "mediaType": "tv" if media_type == "show" else str(media_type),
            "mediaId": int(media_id),
            "is4k": is4k,
        }
        if tvdb_id is not None:
            body["tvdbId"] = int(tvdb_id)
        if seasons is not None:
            body["seasons"] = seasons
        if user_id is not None:
            body["userId"] = int(user_id)
        payload = request_json(
            self._api_url("/request"),
            method="POST",
            headers=self._headers(),
            body=body,
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Seerr create request")
        return payload

    def list_requests(
        self,
        *,
        take: int = 20,
        skip: int = 0,
        filter: Optional[str] = None,
        sort: str = "added",
        requested_by: Optional[int] = None,
        media_type: Optional[str] = None,
    ) -> Mapping[str, Any]:
        params: dict[str, str] = {
            "take": str(take),
            "skip": str(skip),
            "sort": sort,
        }
        if filter:
            params["filter"] = filter
        if requested_by is not None:
            params["requestedBy"] = str(requested_by)
        if media_type:
            params["mediaType"] = "tv" if media_type == "show" else media_type
        query = urllib.parse.urlencode(params)
        payload = request_json(
            f"{self._api_url('/request')}?{query}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            return {"results": [], "pageInfo": {"pages": 0, "results": 0, "page": 1, "pageSize": take}}
        return payload

    def approve_request(self, request_id: int) -> Mapping[str, Any]:
        payload = request_json(
            self._api_url(f"/request/{int(request_id)}/approve"),
            method="POST",
            headers=self._headers(),
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Unexpected response from Seerr approve request")
        return payload

    @staticmethod
    def _filter_search_results(payload: Mapping[str, Any], *, media_type: str) -> List[Mapping[str, Any]]:
        results = payload.get("results") or []
        if not isinstance(results, list):
            return []
        filtered: List[Mapping[str, Any]] = []
        for item in results:
            if not isinstance(item, Mapping):
                continue
            item_type = str(item.get("mediaType") or item.get("media_type") or "").lower()
            if item_type == media_type:
                filtered.append(item)
        return filtered
