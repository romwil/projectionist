"""Radarr API client with read and write operations."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional

from curatorx.config_store import pick_arr_root_folder, root_folder_paths_from_api
from curatorx.connectors.arr_errors import ArrTitleExistsError, arr_exists_error_code
from curatorx.connectors.http import request_json


@dataclass
class RadarrMovie:
    id: int
    title: str
    year: Optional[int]
    tmdb_id: int
    monitored: bool
    has_file: bool
    file_path: str = ""
    file_size: int = 0
    movie_file_id: Optional[int] = None


class RadarrClient:
    def __init__(self, base_url: str, api_key: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"X-Api-Key": self.api_key}

    def system_status(self) -> Mapping[str, Any]:
        return request_json(
            f"{self.base_url}/api/v3/system/status",
            headers=self._headers(),
            timeout=self.timeout,
        )

    def _movie_from_api(self, item: Mapping[str, Any]) -> RadarrMovie:
        movie_file = item.get("movieFile") or {}
        return RadarrMovie(
            id=int(item["id"]),
            title=str(item.get("title") or ""),
            year=item.get("year"),
            tmdb_id=int(item.get("tmdbId") or 0),
            monitored=bool(item.get("monitored")),
            has_file=bool(movie_file),
            file_path=str(movie_file.get("path") or item.get("path") or ""),
            file_size=int(movie_file.get("size") or 0),
            movie_file_id=int(movie_file["id"]) if movie_file.get("id") is not None else None,
        )

    def movies(self) -> List[RadarrMovie]:
        payload = request_json(
            f"{self.base_url}/api/v3/movie",
            headers=self._headers(),
            timeout=self.timeout,
        )
        movies: List[RadarrMovie] = []
        if not isinstance(payload, list):
            return movies
        for item in payload:
            movies.append(self._movie_from_api(item))
        return movies

    def movie_by_tmdb_id(self, tmdb_id: int) -> Optional[RadarrMovie]:
        payload = request_json(
            f"{self.base_url}/api/v3/movie?tmdbId={tmdb_id}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        if isinstance(payload, list):
            for item in payload:
                if int(item.get("tmdbId") or 0) == tmdb_id:
                    return self._movie_from_api(item)
            return None
        if isinstance(payload, dict) and int(payload.get("tmdbId") or 0) == tmdb_id:
            return self._movie_from_api(payload)
        return None

    def lookup(self, term: str) -> List[Mapping[str, Any]]:
        encoded = urllib.parse.quote(term)
        payload = request_json(
            f"{self.base_url}/api/v3/movie/lookup?term={encoded}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        return payload if isinstance(payload, list) else []

    def lookup_tmdb(self, tmdb_id: int) -> Optional[Mapping[str, Any]]:
        payload = request_json(
            f"{self.base_url}/api/v3/movie/lookup/tmdb?tmdbId={tmdb_id}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        return payload if isinstance(payload, dict) else None

    def add_movie(
        self,
        tmdb_id: int,
        *,
        root_folder: str,
        quality_profile_id: int,
        monitored: bool = True,
        search_for_movie: bool = True,
    ) -> Mapping[str, Any]:
        cleaned_root = str(root_folder or "").strip()
        if not cleaned_root:
            raise RuntimeError(
                "Radarr root folder path is not configured. "
                "Set radarr_root_folder in Configuration → Advanced settings."
            )
        existing = self.movie_by_tmdb_id(tmdb_id)
        if existing:
            raise ArrTitleExistsError(
                "Radarr",
                title=existing.title,
                external_id=tmdb_id,
                arr_id=existing.id,
            )
        resolved_root = pick_arr_root_folder(
            cleaned_root,
            root_folder_paths_from_api(self.root_folders()),
            service="Radarr",
        )
        lookup = self.lookup_tmdb(tmdb_id)
        if not lookup:
            raise RuntimeError(f"Radarr could not lookup TMDB id {tmdb_id}")
        body = dict(lookup)
        body["rootFolderPath"] = resolved_root
        body["qualityProfileId"] = quality_profile_id
        body["monitored"] = monitored
        body["addOptions"] = {"searchForMovie": search_for_movie}
        if not str(body.get("path") or "").strip():
            body.pop("path", None)
        try:
            result = request_json(
                f"{self.base_url}/api/v3/movie",
                method="POST",
                headers=self._headers(),
                body=body,
                timeout=self.timeout,
            )
        except RuntimeError as error:
            detail = str(error)
            body_text = detail.split(": ", 1)[-1] if ": " in detail else detail
            if arr_exists_error_code(body_text, movie=True):
                found = self.movie_by_tmdb_id(tmdb_id)
                raise ArrTitleExistsError(
                    "Radarr",
                    title=found.title if found else str(body.get("title") or ""),
                    external_id=tmdb_id,
                    arr_id=found.id if found else None,
                ) from error
            raise
        return result if isinstance(result, dict) else {}

    def delete_movie(self, movie_id: int, *, delete_files: bool = False) -> None:
        request_json(
            f"{self.base_url}/api/v3/movie/{movie_id}?deleteFiles={'true' if delete_files else 'false'}",
            method="DELETE",
            headers=self._headers(),
            timeout=self.timeout,
        )

    def search_movie(self, movie_id: int) -> Mapping[str, Any]:
        """Ask Radarr to search for a managed movie (Commands API)."""
        payload = request_json(
            f"{self.base_url}/api/v3/command",
            method="POST",
            headers=self._headers(),
            body={"name": "MoviesSearch", "movieIds": [movie_id]},
            timeout=self.timeout,
        )
        return payload if isinstance(payload, dict) else {}

    def mark_movie_file_failed(self, movie_file_id: int) -> None:
        """Remove a known bad Radarr file so the subsequent search can replace it."""
        request_json(
            f"{self.base_url}/api/v3/moviefile/{movie_file_id}",
            method="DELETE",
            headers=self._headers(),
            timeout=self.timeout,
        )

    def quality_profiles(self) -> List[Mapping[str, Any]]:
        payload = request_json(
            f"{self.base_url}/api/v3/qualityprofile",
            headers=self._headers(),
            timeout=self.timeout,
        )
        return payload if isinstance(payload, list) else []

    def root_folders(self) -> List[Mapping[str, Any]]:
        payload = request_json(
            f"{self.base_url}/api/v3/rootfolder",
            headers=self._headers(),
            timeout=self.timeout,
        )
        return payload if isinstance(payload, list) else []
