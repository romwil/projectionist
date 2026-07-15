"""TMDB API client for discovery and metadata."""

from __future__ import annotations

import urllib.parse
from typing import Any, List, Mapping, Optional

from curatorx.connectors.http import request_json


class TMDBClient:
    BASE = "https://api.themoviedb.org/3"
    IMAGE_BASE = "https://image.tmdb.org/t/p"

    def __init__(self, api_key: str, timeout: int = 30) -> None:
        self.api_key = api_key
        self.timeout = timeout

    def _url(self, path: str, **params: Any) -> str:
        query = {"api_key": self.api_key, **params}
        encoded = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        return f"{self.BASE}{path}?{encoded}"

    def poster_url(self, path: Optional[str], size: str = "w500") -> str:
        if not path:
            return ""
        return f"{self.IMAGE_BASE}/{size}{path}"

    def backdrop_url(self, path: Optional[str], size: str = "w1280") -> str:
        if not path:
            return ""
        return f"{self.IMAGE_BASE}/{size}{path}"

    def _search(self, path: str, query: str, *, page: int = 1, year: Optional[int] = None) -> Mapping[str, Any]:
        params: dict[str, Any] = {"query": query, "page": page}
        if year is not None:
            params["year"] = year
        payload = request_json(self._url(path, **params), timeout=self.timeout)
        return payload if isinstance(payload, dict) else {}

    def search_movie(self, query: str, *, page: int = 1, year: Optional[int] = None) -> List[Mapping[str, Any]]:
        return self._search("/search/movie", query, page=page, year=year).get("results", [])

    def search_movie_page(self, query: str, *, page: int = 1, year: Optional[int] = None) -> Mapping[str, Any]:
        return self._search("/search/movie", query, page=page, year=year)

    def search_tv(self, query: str, *, page: int = 1) -> List[Mapping[str, Any]]:
        return self._search("/search/tv", query, page=page).get("results", [])

    def search_tv_page(self, query: str, *, page: int = 1) -> Mapping[str, Any]:
        return self._search("/search/tv", query, page=page)

    def movie_details(self, tmdb_id: int) -> Mapping[str, Any]:
        payload = request_json(
            self._url(f"/movie/{tmdb_id}", append_to_response="credits,keywords,external_ids"),
            timeout=self.timeout,
        )
        return payload if isinstance(payload, dict) else {}

    def tv_details(self, tmdb_id: int) -> Mapping[str, Any]:
        payload = request_json(
            self._url(f"/tv/{tmdb_id}", append_to_response="credits,keywords,external_ids"),
            timeout=self.timeout,
        )
        return payload if isinstance(payload, dict) else {}

    def discover_movies(
        self,
        *,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        with_genres: Optional[str] = None,
        with_keywords: Optional[str] = None,
        sort_by: str = "popularity.desc",
        page: int = 1,
    ) -> List[Mapping[str, Any]]:
        params: dict[str, Any] = {"sort_by": sort_by, "page": page}
        if year_from:
            params["primary_release_date.gte"] = f"{year_from}-01-01"
        if year_to:
            params["primary_release_date.lte"] = f"{year_to}-12-31"
        if with_genres:
            params["with_genres"] = with_genres
        if with_keywords:
            params["with_keywords"] = with_keywords
        payload = request_json(self._url("/discover/movie", **params), timeout=self.timeout)
        return payload.get("results", []) if isinstance(payload, dict) else []

    def discover_tv(
        self,
        *,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        with_genres: Optional[str] = None,
        sort_by: str = "popularity.desc",
        page: int = 1,
    ) -> List[Mapping[str, Any]]:
        params: dict[str, Any] = {"sort_by": sort_by, "page": page}
        if year_from:
            params["first_air_date.gte"] = f"{year_from}-01-01"
        if year_to:
            params["first_air_date.lte"] = f"{year_to}-12-31"
        if with_genres:
            params["with_genres"] = with_genres
        payload = request_json(self._url("/discover/tv", **params), timeout=self.timeout)
        return payload.get("results", []) if isinstance(payload, dict) else []

    def movie_keywords(self, tmdb_id: int) -> List[str]:
        payload = request_json(self._url(f"/movie/{tmdb_id}/keywords"), timeout=self.timeout)
        if not isinstance(payload, dict):
            return []
        return [k.get("name", "") for k in payload.get("keywords", []) if k.get("name")]

    def search_keywords(self, query: str, *, page: int = 1) -> List[Mapping[str, Any]]:
        """Search TMDB keywords by text. Returns list of {id, name} dicts."""
        payload = request_json(
            self._url("/search/keyword", query=query, page=page), timeout=self.timeout
        )
        return payload.get("results", []) if isinstance(payload, dict) else []

    def genre_list_movies(self) -> List[Mapping[str, Any]]:
        payload = request_json(self._url("/genre/movie/list"), timeout=self.timeout)
        return payload.get("genres", []) if isinstance(payload, dict) else []

    def genre_list_tv(self) -> List[Mapping[str, Any]]:
        payload = request_json(self._url("/genre/tv/list"), timeout=self.timeout)
        return payload.get("genres", []) if isinstance(payload, dict) else []
