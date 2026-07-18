"""Sonarr API client with read and write operations."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional

from curatorx.config_store import pick_arr_root_folder, root_folder_paths_from_api
from curatorx.connectors.arr_errors import ArrTitleExistsError, arr_exists_error_code
from curatorx.connectors.http import request_json


@dataclass
class SonarrSeries:
    id: int
    title: str
    year: Optional[int]
    tvdb_id: int
    tmdb_id: Optional[int]
    monitored: bool
    episode_file_count: int = 0
    total_file_size: int = 0


class SonarrClient:
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

    def _series_from_api(self, item: Mapping[str, Any]) -> SonarrSeries:
        stats = item.get("statistics") or {}
        return SonarrSeries(
            id=int(item["id"]),
            title=str(item.get("title") or ""),
            year=item.get("year"),
            tvdb_id=int(item.get("tvdbId") or 0),
            tmdb_id=item.get("tmdbId"),
            monitored=bool(item.get("monitored")),
            episode_file_count=int(stats.get("episodeFileCount") or 0),
            total_file_size=int(stats.get("sizeOnDisk") or 0),
        )

    def series_list(self) -> List[SonarrSeries]:
        payload = request_json(
            f"{self.base_url}/api/v3/series",
            headers=self._headers(),
            timeout=self.timeout,
        )
        series_items: List[SonarrSeries] = []
        if not isinstance(payload, list):
            return series_items
        for item in payload:
            series_items.append(self._series_from_api(item))
        return series_items

    def series_by_tvdb_id(self, tvdb_id: int) -> Optional[SonarrSeries]:
        payload = request_json(
            f"{self.base_url}/api/v3/series?tvdbId={tvdb_id}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        if isinstance(payload, list):
            for item in payload:
                if int(item.get("tvdbId") or 0) == tvdb_id:
                    return self._series_from_api(item)
            return None
        if isinstance(payload, dict) and int(payload.get("tvdbId") or 0) == tvdb_id:
            return self._series_from_api(payload)
        return None

    def lookup(self, term: str) -> List[Mapping[str, Any]]:
        encoded = urllib.parse.quote(term)
        payload = request_json(
            f"{self.base_url}/api/v3/series/lookup?term={encoded}",
            headers=self._headers(),
            timeout=self.timeout,
        )
        return payload if isinstance(payload, list) else []

    def lookup_tvdb(self, tvdb_id: int) -> Optional[Mapping[str, Any]]:
        results = self.lookup(f"tvdb:{tvdb_id}")
        for item in results:
            if int(item.get("tvdbId") or 0) == tvdb_id:
                return item
        return results[0] if results else None

    def add_series(
        self,
        tvdb_id: int,
        *,
        root_folder: str,
        quality_profile_id: int,
        monitored: bool = True,
        search_for_missing: bool = True,
        season_folder: bool = True,
    ) -> Mapping[str, Any]:
        cleaned_root = str(root_folder or "").strip()
        if not cleaned_root:
            raise RuntimeError(
                "Sonarr root folder path is not configured. "
                "Set sonarr_root_folder in Configuration → Advanced settings."
            )
        existing = self.series_by_tvdb_id(tvdb_id)
        if existing:
            raise ArrTitleExistsError(
                "Sonarr",
                title=existing.title,
                external_id=tvdb_id,
                arr_id=existing.id,
            )
        resolved_root = pick_arr_root_folder(
            cleaned_root,
            root_folder_paths_from_api(self.root_folders()),
            service="Sonarr",
        )
        lookup = self.lookup_tvdb(tvdb_id)
        if not lookup:
            raise RuntimeError(f"Sonarr could not lookup TVDB id {tvdb_id}")
        body = dict(lookup)
        body["rootFolderPath"] = resolved_root
        body["qualityProfileId"] = quality_profile_id
        body["monitored"] = monitored
        body["seasonFolder"] = season_folder
        body["addOptions"] = {"searchForMissingEpisodes": search_for_missing}
        if not str(body.get("path") or "").strip():
            body.pop("path", None)
        try:
            result = request_json(
                f"{self.base_url}/api/v3/series",
                method="POST",
                headers=self._headers(),
                body=body,
                timeout=self.timeout,
            )
        except RuntimeError as error:
            detail = str(error)
            body_text = detail.split(": ", 1)[-1] if ": " in detail else detail
            if arr_exists_error_code(body_text, movie=False):
                found = self.series_by_tvdb_id(tvdb_id)
                raise ArrTitleExistsError(
                    "Sonarr",
                    title=found.title if found else str(body.get("title") or ""),
                    external_id=tvdb_id,
                    arr_id=found.id if found else None,
                ) from error
            raise
        return result if isinstance(result, dict) else {}

    def delete_series(self, series_id: int, *, delete_files: bool = False) -> None:
        request_json(
            f"{self.base_url}/api/v3/series/{series_id}?deleteFiles={'true' if delete_files else 'false'}",
            method="DELETE",
            headers=self._headers(),
            timeout=self.timeout,
        )

    def search_series(self, series_id: int) -> Mapping[str, Any]:
        """Ask Sonarr to search a managed series through its Commands API."""
        payload = request_json(
            f"{self.base_url}/api/v3/command",
            method="POST",
            headers=self._headers(),
            body={"name": "SeriesSearch", "seriesId": series_id},
            timeout=self.timeout,
        )
        return payload if isinstance(payload, dict) else {}

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
