"""Plex collection create/list/mutate helpers."""

from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import List, Optional, Sequence

from projectionist.connectors.http import request_empty, request_xml
from projectionist.connectors.plex import PlexClient, PLEX_LIBRARY_IDENTIFIER

_MEDIA_TYPE_TO_PLEX = {"movie": 1, "show": 2}


@dataclass
class PlexCollection:
    rating_key: str
    title: str
    section_id: str
    media_type: str


def _plex_type(media_type: str) -> int:
    normalized = str(media_type or "").strip().lower()
    if normalized not in _MEDIA_TYPE_TO_PLEX:
        raise ValueError("media_type must be movie or show")
    return _MEDIA_TYPE_TO_PLEX[normalized]


def _metadata_uri(client: PlexClient, rating_keys: Sequence[str]) -> str:
    keys = [str(key).strip() for key in rating_keys if str(key).strip()]
    if not keys:
        raise ValueError("At least one rating_key is required")
    machine_id = client.machine_identifier()
    joined = ",".join(keys)
    return (
        f"server://{machine_id}/{PLEX_LIBRARY_IDENTIFIER}/library/metadata/{joined}"
    )


def _auth_url(client: PlexClient, path: str) -> str:
    separator = "&" if "?" in path else "?"
    return f"{client.base_url}{path}{separator}X-Plex-Token={urllib.parse.quote(client.token)}"


def list_collections(client: PlexClient, section_id: str) -> List[PlexCollection]:
    section = str(section_id or "").strip()
    if not section:
        raise ValueError("section_id is required")
    root = client._request_xml(
        f"/library/sections/{section}/collections?includeCollections=1"
    )
    collections: List[PlexCollection] = []
    for element in root.findall(".//Directory"):
        rating_key = str(element.attrib.get("ratingKey") or "").strip()
        if not rating_key:
            continue
        subtype = str(element.attrib.get("subtype") or element.attrib.get("type") or "movie")
        media_type = "show" if subtype in {"show", "2"} else "movie"
        collections.append(
            PlexCollection(
                rating_key=rating_key,
                title=str(element.attrib.get("title") or ""),
                section_id=section,
                media_type=media_type,
            )
        )
    return collections


def find_collection_by_title(
    client: PlexClient,
    section_id: str,
    title: str,
) -> Optional[PlexCollection]:
    wanted = str(title or "").strip().casefold()
    if not wanted:
        return None
    for collection in list_collections(client, section_id):
        if collection.title.casefold() == wanted:
            return collection
    return None


def create_collection(
    client: PlexClient,
    *,
    section_id: str,
    title: str,
    media_type: str,
    rating_keys: Optional[Sequence[str]] = None,
) -> PlexCollection:
    section = str(section_id or "").strip()
    collection_title = str(title or "").strip()
    if not section:
        raise ValueError("section_id is required")
    if not collection_title:
        raise ValueError("title is required")

    params = {
        "sectionId": section,
        "title": collection_title,
        "type": str(_plex_type(media_type)),
        "smart": "0",
    }
    keys = [str(key).strip() for key in (rating_keys or []) if str(key).strip()]
    if keys:
        params["uri"] = _metadata_uri(client, keys)

    query = urllib.parse.urlencode(params)
    root = request_xml(_auth_url(client, f"/library/collections?{query}"), method="POST")
    element = root.find(".//Directory") or root.find(".//Collection")
    if element is None:
        raise RuntimeError("Plex did not return a collection rating key")
    rating_key = str(element.attrib.get("ratingKey") or "").strip()
    if not rating_key:
        raise RuntimeError("Plex did not return a collection rating key")
    return PlexCollection(
        rating_key=rating_key,
        title=collection_title,
        section_id=section,
        media_type=str(media_type),
    )


def add_items_to_collection(
    client: PlexClient,
    collection_rating_key: str,
    rating_keys: Sequence[str],
) -> None:
    collection_key = str(collection_rating_key or "").strip()
    if not collection_key:
        raise ValueError("collection_rating_key is required")
    uri = _metadata_uri(client, rating_keys)
    query = urllib.parse.urlencode({"uri": uri})
    request_empty(
        _auth_url(client, f"/library/collections/{collection_key}/items?{query}"),
        method="PUT",
        timeout=client.timeout,
    )


def delete_collection(client: PlexClient, collection_rating_key: str) -> None:
    """Delete a Plex collection by rating key.

    Only call this for collections CuratorX marked as ephemeral — never for
    owner-named evergreen collections without a DB marker.
    """
    collection_key = str(collection_rating_key or "").strip()
    if not collection_key:
        raise ValueError("collection_rating_key is required")
    request_empty(
        _auth_url(client, f"/library/collections/{collection_key}"),
        method="DELETE",
        timeout=client.timeout,
    )


def is_ephemeral_collection_title(title: str, *, prefix: str) -> bool:
    """True when the title carries the CuratorX ephemeral prefix."""
    cleaned = str(title or "").strip()
    # Preserve trailing space in the marker (e.g. ``"[CuratorX] "``).
    marker = str(prefix or "").lstrip()
    if not cleaned or not marker:
        return False
    return cleaned.casefold().startswith(marker.casefold())


def apply_ephemeral_title_prefix(title: str, *, prefix: str) -> str:
    """Ensure ``title`` starts with the ephemeral prefix (no double-prefix)."""
    cleaned = str(title or "").strip()
    marker = str(prefix or "").lstrip()
    if not marker:
        return cleaned
    if is_ephemeral_collection_title(cleaned, prefix=marker):
        return cleaned
    return f"{marker}{cleaned}"
