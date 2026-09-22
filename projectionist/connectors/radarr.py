"""Radarr API client with read and write operations."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from projectionist.config_store import pick_arr_root_folder, root_folder_paths_from_api
from projectionist.connectors.arr_errors import (
    ArrPathConflictError,
    ArrTitleExistsError,
    arr_exists_error_code,
    folder_path_from_arr_error,
    intended_movie_folder,
    is_arr_path_conflict_error,
)
from projectionist.connectors.http import request_json


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
    folder_path: str = ""


def normalize_folder_path(path: str) -> str:
    return str(path or "").strip().rstrip("/").casefold()


def folder_path_for_movie(movie: RadarrMovie) -> str:
    folder = str(movie.folder_path or "").strip().rstrip("/")
    if folder:
        return folder
    file_path = str(movie.file_path or "").strip()
    if not file_path:
        return ""
    parent = str(PurePosixPath(file_path).parent)
    return "" if parent in {".", "/"} else parent


def index_radarr_movies(
    movies: Sequence[RadarrMovie],
) -> Tuple[Dict[int, RadarrMovie], Dict[str, RadarrMovie]]:
    by_tmdb: Dict[int, RadarrMovie] = {}
    by_path: Dict[str, RadarrMovie] = {}
    for movie in movies:
        if movie.tmdb_id:
            by_tmdb.setdefault(int(movie.tmdb_id), movie)
        folder = folder_path_for_movie(movie)
        key = normalize_folder_path(folder)
        if key:
            by_path.setdefault(key, movie)
    return by_tmdb, by_path


def movie_occupying_folder(
    movies_or_index: Sequence[RadarrMovie] | Mapping[str, RadarrMovie],
    path: str,
) -> Optional[RadarrMovie]:
    key = normalize_folder_path(path)
    if not key:
        return None
    if isinstance(movies_or_index, Mapping):
        found = movies_or_index.get(key)
        return found if isinstance(found, RadarrMovie) else None
    _by_tmdb, by_path = index_radarr_movies(movies_or_index)
    return by_path.get(key)


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
            folder_path=str(item.get("path") or ""),
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
        intended_path = intended_movie_folder(
            root_folder=resolved_root,
            title=str(body.get("title") or ""),
            year=body.get("year"),
            lookup_path=str(body.get("path") or ""),
        )
        occupant = movie_occupying_folder(self.movies(), intended_path)
        if occupant is not None:
            if occupant.tmdb_id and int(occupant.tmdb_id) == int(tmdb_id):
                raise ArrTitleExistsError(
                    "Radarr",
                    title=occupant.title,
                    external_id=tmdb_id,
                    arr_id=occupant.id,
                )
            raise ArrPathConflictError(
                path=intended_path or folder_path_for_movie(occupant),
                intended_title=str(body.get("title") or ""),
                intended_tmdb_id=tmdb_id,
                occupant_title=occupant.title,
                occupant_tmdb_id=occupant.tmdb_id,
                occupant_arr_id=occupant.id,
            )
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
            body_text = detail[next((i for i, ch in enumerate(detail) if ch in "[{"), 0) :]
            if arr_exists_error_code(body_text, movie=True) or arr_exists_error_code(detail, movie=True):
                found = self.movie_by_tmdb_id(tmdb_id)
                raise ArrTitleExistsError(
                    "Radarr",
                    title=found.title if found else str(body.get("title") or ""),
                    external_id=tmdb_id,
                    arr_id=found.id if found else None,
                ) from error
            if is_arr_path_conflict_error(error):
                folder = folder_path_from_arr_error(error) or intended_path
                found = movie_occupying_folder(self.movies(), folder)
                if found and found.tmdb_id and int(found.tmdb_id) == int(tmdb_id):
                    raise ArrTitleExistsError(
                        "Radarr",
                        title=found.title,
                        external_id=tmdb_id,
                        arr_id=found.id,
                    ) from error
                raise ArrPathConflictError(
                    path=folder,
                    intended_title=str(body.get("title") or ""),
                    intended_tmdb_id=tmdb_id,
                    occupant_title=found.title if found else "",
                    occupant_tmdb_id=found.tmdb_id if found else 0,
                    occupant_arr_id=found.id if found else None,
                ) from error
            raise
        return result if isinstance(result, dict) else {}

    def movie_by_id(self, movie_id: int) -> Optional[Mapping[str, Any]]:
        """Return the raw Radarr movie payload (includes movieFile / sizeOnDisk)."""
        payload = request_json(
            f"{self.base_url}/api/v3/movie/{int(movie_id)}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        return payload if isinstance(payload, dict) else None

    def delete_movie(
        self,
        movie_id: int,
        *,
        delete_files: bool = False,
        add_exclusion: bool = False,
    ) -> None:
        """Remove a movie from Radarr.

        ``delete_files`` removes media on disk. ``add_exclusion`` adds the title
        to Radarr's import exclusion list so list syncs will not re-add it.
        """
        params = (
            f"deleteFiles={'true' if delete_files else 'false'}"
            f"&addExclusion={'true' if add_exclusion else 'false'}"
        )
        request_json(
            f"{self.base_url}/api/v3/movie/{movie_id}?{params}",
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
