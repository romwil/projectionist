"""Plex Discover watchlist client (account-token scoped)."""

from __future__ import annotations

import logging
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Mapping, Optional

from curatorx.connectors.http import (
    merge_plex_provider_ids,
    optional_int,
    request_empty,
    request_json,
    request_xml,
)

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


def _safe_optional_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return optional_int(str(value))
    except (TypeError, ValueError):
        return None


def _media_type_from_element(element: ET.Element) -> Optional[str]:
    kind = (element.attrib.get("type") or element.tag or "").lower()
    if kind in {"movie", "video"}:
        return "movie"
    if kind in {"show", "directory"}:
        return "show"
    return None


def _media_type_from_json(meta: Mapping[str, Any]) -> Optional[str]:
    kind = str(meta.get("type") or "").lower()
    if kind in {"movie", "video"}:
        return "movie"
    if kind in {"show", "directory"}:
        return "show"
    return None


def _item_from_providers(
    *,
    title: str,
    media_type: str,
    guid: str,
    provider_guids: List[str],
    rating_key: Optional[str],
    year: Any,
) -> Optional[Dict[str, Any]]:
    providers = merge_plex_provider_ids(guid, *provider_guids)
    tmdb_id = _safe_optional_int(providers.get("tmdb_id"))
    tvdb_id = _safe_optional_int(providers.get("tvdb_id"))
    key = rating_key or discover_rating_key_from_guid(guid)
    if tmdb_id is None and tvdb_id is None and not key:
        return None
    return {
        "title": title,
        "media_type": media_type,
        "tmdb_id": tmdb_id,
        "tvdb_id": tvdb_id,
        "year": _safe_optional_int(year),
        "plex_rating_key": key,
        "guid": guid,
    }


def _parse_watchlist_element(element: ET.Element) -> Optional[Dict[str, Any]]:
    media_type = _media_type_from_element(element)
    if media_type is None:
        return None
    title = (element.attrib.get("title") or "").strip()
    if not title:
        return None
    guid = element.attrib.get("guid") or ""
    child_guids = [child.attrib.get("id", "") for child in element.findall("Guid")]
    return _item_from_providers(
        title=title,
        media_type=media_type,
        guid=guid,
        provider_guids=child_guids,
        rating_key=element.attrib.get("ratingKey"),
        year=element.attrib.get("year"),
    )


def _parse_watchlist_json_item(meta: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
    media_type = _media_type_from_json(meta)
    if media_type is None:
        return None
    title = str(meta.get("title") or "").strip()
    if not title:
        return None
    guid = str(meta.get("guid") or "")
    child_guids: List[str] = []
    for entry in meta.get("Guid") or []:
        if isinstance(entry, Mapping):
            child_guids.append(str(entry.get("id") or ""))
        elif isinstance(entry, str):
            child_guids.append(entry)
    return _item_from_providers(
        title=title,
        media_type=media_type,
        guid=guid,
        provider_guids=child_guids,
        rating_key=str(meta.get("ratingKey") or "") or None,
        year=meta.get("year"),
    )


def _watchlist_page_params(start: int, page_size: int) -> Dict[str, Any]:
    # includeGuids is required — without it Discover often returns only plex://
    # guids and every title lands as "unresolved" (no TMDB/TVDB id).
    return {
        "includeCollections": 1,
        "includeExternalMedia": 1,
        "includeGuids": 1,
        "X-Plex-Container-Start": start,
        "X-Plex-Container-Size": page_size,
    }


def _fetch_watchlist_page_json(
    token: str,
    *,
    start: int,
    page_size: int,
    timeout: int,
) -> tuple[List[Dict[str, Any]], int, Optional[int]]:
    params = _watchlist_page_params(start, page_size)
    url = f"{DISCOVER_BASE}/library/sections/watchlist/all?{urllib.parse.urlencode(params)}"
    payload = request_json(url, headers=_json_headers(token), timeout=timeout)
    container = payload.get("MediaContainer") if isinstance(payload, Mapping) else None
    if not isinstance(container, Mapping):
        return [], 0, None
    metadata = container.get("Metadata") or container.get("Video") or []
    if isinstance(metadata, Mapping):
        metadata = [metadata]
    if not isinstance(metadata, list):
        metadata = []
    items: List[Dict[str, Any]] = []
    for entry in metadata:
        if not isinstance(entry, Mapping):
            continue
        parsed = _parse_watchlist_json_item(entry)
        if parsed:
            items.append(parsed)
    total = _safe_optional_int(container.get("totalSize") or container.get("size"))
    return items, len(metadata), total


def _fetch_watchlist_page_xml(
    token: str,
    *,
    start: int,
    page_size: int,
    timeout: int,
) -> tuple[List[Dict[str, Any]], int, Optional[int]]:
    params = _watchlist_page_params(start, page_size)
    url = f"{DISCOVER_BASE}/library/sections/watchlist/all?{urllib.parse.urlencode(params)}"
    root = request_xml(url, headers=_headers(token), timeout=timeout)
    children = list(root)
    items: List[Dict[str, Any]] = []
    for element in children:
        parsed = _parse_watchlist_element(element)
        if parsed:
            items.append(parsed)
    total = _safe_optional_int(root.attrib.get("totalSize") or root.attrib.get("size"))
    return items, len(children), total


def fetch_metadata_guids(
    token: str,
    plex_rating_key: str,
    *,
    timeout: int = 20,
) -> Dict[str, Optional[int]]:
    """Resolve TMDB/TVDB ids for a Discover rating key via metadata + Guids."""
    key = str(plex_rating_key or "").strip()
    empty: Dict[str, Optional[int]] = {"tmdb_id": None, "tvdb_id": None}
    if not key:
        return empty
    params = {"includeGuids": 1}
    url = (
        f"{DISCOVER_BASE}/library/metadata/{urllib.parse.quote(key)}"
        f"?{urllib.parse.urlencode(params)}"
    )
    try:
        payload = request_json(url, headers=_json_headers(token), timeout=timeout)
    except RuntimeError:
        logger.debug("Discover metadata lookup failed for key=%s", key, exc_info=True)
        return empty
    container = payload.get("MediaContainer") if isinstance(payload, Mapping) else None
    if not isinstance(container, Mapping):
        return empty
    metadata = container.get("Metadata") or []
    if isinstance(metadata, Mapping):
        metadata = [metadata]
    if not isinstance(metadata, list) or not metadata:
        return empty
    meta = metadata[0]
    if not isinstance(meta, Mapping):
        return empty
    guids = [str(meta.get("guid") or "")]
    for entry in meta.get("Guid") or []:
        if isinstance(entry, Mapping):
            guids.append(str(entry.get("id") or ""))
    providers = merge_plex_provider_ids(*guids)
    return {
        "tmdb_id": _safe_optional_int(providers.get("tmdb_id")),
        "tvdb_id": _safe_optional_int(providers.get("tvdb_id")),
    }


def enrich_watchlist_provider_ids(
    token: str,
    items: List[Dict[str, Any]],
    *,
    timeout: int = 20,
    max_lookups: int = 600,
) -> List[Dict[str, Any]]:
    """Fill missing TMDB/TVDB ids via per-item Discover metadata (Guid) lookups."""
    remaining = max(0, int(max_lookups))
    enriched: List[Dict[str, Any]] = []
    for item in items:
        if item.get("tmdb_id") is not None or item.get("tvdb_id") is not None:
            enriched.append(item)
            continue
        key = str(item.get("plex_rating_key") or "").strip()
        if not key or remaining <= 0:
            enriched.append(item)
            continue
        remaining -= 1
        ids = fetch_metadata_guids(token, key, timeout=timeout)
        if ids.get("tmdb_id") is None and ids.get("tvdb_id") is None:
            enriched.append(item)
            continue
        next_item = dict(item)
        next_item["tmdb_id"] = ids.get("tmdb_id")
        next_item["tvdb_id"] = ids.get("tvdb_id")
        enriched.append(next_item)
    return enriched


def fetch_watchlist(
    token: str,
    *,
    timeout: int = 30,
    page_size: int = 100,
    max_items: int = 5000,
    enrich_missing_ids: bool = True,
) -> List[Dict[str, Any]]:
    """Pull the full account Discover watchlist.

    The Discover endpoint force-paginates large watchlists, so we page through
    with ``X-Plex-Container-Start`` / ``X-Plex-Container-Size`` until the server
    stops returning full pages. Without this, only the first page (a handful of
    items) is ever imported.

    Prefers JSON (richer Guid payloads). Falls back to XML when JSON fails.
    When list rows still lack TMDB/TVDB, optionally resolves them via metadata
    lookups so pins can be saved instead of counted as unresolved.
    """
    items: List[Dict[str, Any]] = []
    start = 0
    use_json = True
    while True:
        try:
            if use_json:
                page_items, returned, total = _fetch_watchlist_page_json(
                    token, start=start, page_size=page_size, timeout=timeout
                )
            else:
                page_items, returned, total = _fetch_watchlist_page_xml(
                    token, start=start, page_size=page_size, timeout=timeout
                )
        except RuntimeError:
            if use_json:
                logger.info("Discover watchlist JSON failed; falling back to XML")
                use_json = False
                continue
            raise

        items.extend(page_items)
        start += page_size
        if returned < page_size:
            break
        if total is not None and start >= total:
            break
        if len(items) >= max_items:
            break

    if len(items) > max_items:
        items = items[:max_items]

    missing = sum(
        1 for item in items if item.get("tmdb_id") is None and item.get("tvdb_id") is None
    )
    if enrich_missing_ids and missing:
        logger.info(
            "Discover watchlist: enriching provider ids for %s/%s unresolved rows",
            missing,
            len(items),
        )
        items = enrich_watchlist_provider_ids(token, items, timeout=min(timeout, 20))
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
        meta_tmdb = _safe_optional_int(providers.get("tmdb_id"))
        meta_tvdb = _safe_optional_int(providers.get("tvdb_id"))
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
            meta_year = _safe_optional_int(meta.get("year"))
            if meta_year is not None and meta_year != int(year):
                continue
        return str(meta.get("ratingKey") or discover_rating_key_from_guid(str(meta.get("guid") or "")) or "") or None
    return None
