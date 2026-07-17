"""Plex Discover watchlist client (account-token scoped)."""

from __future__ import annotations

import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Mapping, Optional

from curatorx.connectors.http import merge_plex_provider_ids, optional_int, request_empty, request_json, request_xml

logger = logging.getLogger(__name__)

DISCOVER_BASE = "https://discover.provider.plex.tv"


def _headers(token: str) -> Dict[str, str]:
    return {
        "Accept": "application/xml",
        "X-Plex-Token": token.strip(),
        "X-Plex-Product": "CuratorX",
        "X-Plex-Client-Identifier": "curatorx-watchlist",
    }


def _json_headers(token: str) -> Dict[str, str]:
    headers = _headers(token)
    headers["Accept"] = "application/json"
    return headers


def discover_rating_key_from_guid(guid: str) -> Optional[str]:
    cleaned = str(guid or "").strip()
    if not cleaned:
        return None
    if "/" in cleaned:
        return cleaned.rsplit("/", 1)[-1] or None
    return cleaned or None


def _media_type_from_element(element: ET.Element) -> Optional[str]:
    kind = (element.attrib.get("type") or element.tag or "").lower()
    if kind in {"movie", "video"}:
        return "movie"
    if kind in {"show", "directory"}:
        return "show"
    return None


def _parse_watchlist_element(element: ET.Element) -> Optional[Dict[str, Any]]:
    media_type = _media_type_from_element(element)
    if media_type is None:
        return None
    title = (element.attrib.get("title") or "").strip()
    if not title:
        return None
    guid = element.attrib.get("guid") or ""
    child_guids = [child.attrib.get("id", "") for child in element.findall("Guid")]
    providers = merge_plex_provider_ids(guid, *child_guids)
    tmdb_raw = providers.get("tmdb_id")
    tvdb_raw = providers.get("tvdb_id")
    tmdb_id = optional_int(tmdb_raw) if tmdb_raw else None
    tvdb_id = optional_int(tvdb_raw) if tvdb_raw else None
    rating_key = element.attrib.get("ratingKey") or discover_rating_key_from_guid(guid)
    year = optional_int(element.attrib.get("year"))
    if tmdb_id is None and tvdb_id is None and not rating_key:
        return None
    return {
        "title": title,
        "media_type": media_type,
        "tmdb_id": tmdb_id,
        "tvdb_id": tvdb_id,
        "year": year,
        "plex_rating_key": rating_key,
        "guid": guid,
    }


def fetch_watchlist(
    token: str,
    *,
    timeout: int = 30,
    page_size: int = 100,
    max_items: int = 5000,
) -> List[Dict[str, Any]]:
    """Pull the full account Discover watchlist.

    The Discover endpoint force-paginates large watchlists, so we page through
    with ``X-Plex-Container-Start`` / ``X-Plex-Container-Size`` until the server
    stops returning full pages. Without this, only the first page (a handful of
    items) is ever imported.
    """
    items: List[Dict[str, Any]] = []
    start = 0
    while True:
        params = {
            "includeCollections": 1,
            "includeExternalMedia": 1,
            "X-Plex-Container-Start": start,
            "X-Plex-Container-Size": page_size,
        }
        url = f"{DISCOVER_BASE}/library/sections/watchlist/all?{urllib.parse.urlencode(params)}"
        root = request_xml(url, headers=_headers(token), timeout=timeout)
        children = list(root)
        for element in children:
            parsed = _parse_watchlist_element(element)
            if parsed:
                items.append(parsed)

        returned = len(children)
        total = optional_int(root.attrib.get("totalSize") or root.attrib.get("size"))
        start += page_size
        if returned < page_size:
            break
        if total is not None and start >= total:
            break
        if len(items) >= max_items:
            break
    return items


def add_to_watchlist(token: str, plex_rating_key: str, *, timeout: int = 30) -> None:
    key = str(plex_rating_key or "").strip()
    if not key:
        raise ValueError("plex_rating_key is required")
    url = f"{DISCOVER_BASE}/actions/addToWatchlist?{urllib.parse.urlencode({'ratingKey': key})}"
    request_empty(url, method="PUT", headers=_headers(token), timeout=timeout)


def remove_from_watchlist(token: str, plex_rating_key: str, *, timeout: int = 30) -> None:
    key = str(plex_rating_key or "").strip()
    if not key:
        raise ValueError("plex_rating_key is required")
    url = f"{DISCOVER_BASE}/actions/removeFromWatchlist?{urllib.parse.urlencode({'ratingKey': key})}"
    request_empty(url, method="PUT", headers=_headers(token), timeout=timeout)


def resolve_discover_rating_key(
    token: str,
    *,
    title: str,
    media_type: str,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    year: Optional[int] = None,
    timeout: int = 30,
) -> Optional[str]:
    """Best-effort Discover metadata key for a local pin (needed to push)."""
    query = (title or "").strip()
    if not query:
        return None
    libtype = "movies" if media_type == "movie" else "tv"
    params = {
        "query": query,
        "limit": 15,
        "searchTypes": libtype,
        "searchProviders": "discover",
        "includeMetadata": 1,
    }
    url = f"{DISCOVER_BASE}/library/search?{urllib.parse.urlencode(params)}"
    try:
        payload = request_json(url, headers=_json_headers(token), timeout=timeout)
    except RuntimeError:
        logger.debug("Discover search failed for title=%s", query, exc_info=True)
        return None
    if not isinstance(payload, Mapping):
        return None
    container = payload.get("MediaContainer") if isinstance(payload.get("MediaContainer"), Mapping) else {}
    groups = container.get("SearchResults") if isinstance(container, Mapping) else None
    if not isinstance(groups, list):
        return None

    wanted_type = "movie" if media_type == "movie" else "show"
    candidates: List[Mapping[str, Any]] = []
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        results = group.get("SearchResult") or []
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, Mapping):
                continue
            metadata = result.get("Metadata")
            if isinstance(metadata, Mapping):
                candidates.append(metadata)

    for meta in candidates:
        meta_type = str(meta.get("type") or "").lower()
        if meta_type != wanted_type:
            continue
        guids = [str(meta.get("guid") or "")]
        for guid_entry in meta.get("Guid") or []:
            if isinstance(guid_entry, Mapping):
                guids.append(str(guid_entry.get("id") or ""))
        providers = merge_plex_provider_ids(*guids)
        meta_tmdb = optional_int(providers.get("tmdb_id")) if providers.get("tmdb_id") else None
        meta_tvdb = optional_int(providers.get("tvdb_id")) if providers.get("tvdb_id") else None
        if tmdb_id is not None and meta_tmdb == int(tmdb_id):
            return str(meta.get("ratingKey") or discover_rating_key_from_guid(str(meta.get("guid") or "")) or "") or None
        if tvdb_id is not None and meta_tvdb == int(tvdb_id):
            return str(meta.get("ratingKey") or discover_rating_key_from_guid(str(meta.get("guid") or "")) or "") or None

    # Fall back to title (+ year) match when IDs are missing from Discover payloads.
    title_l = query.lower()
    for meta in candidates:
        meta_type = str(meta.get("type") or "").lower()
        if meta_type != wanted_type:
            continue
        if str(meta.get("title") or "").strip().lower() != title_l:
            continue
        if year is not None:
            meta_year = optional_int(str(meta.get("year") or ""))
            if meta_year is not None and meta_year != int(year):
                continue
        return str(meta.get("ratingKey") or discover_rating_key_from_guid(str(meta.get("guid") or "")) or "") or None
    return None
