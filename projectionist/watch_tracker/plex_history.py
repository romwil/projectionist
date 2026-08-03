"""Plex history → WatchEventInput normalization and paged fetch."""

from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass
from typing import List, Optional
from xml.etree import ElementTree

from projectionist.connectors.http import optional_int
from projectionist.connectors.plex import PlexClient
from projectionist.watch_tracker.models import WatchEventInput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlexHistoryItem:
    rating_key: str
    media_type: str
    account_id: str
    viewed_at_ms: int
    parent_rating_key: Optional[str] = None
    duration_ms: Optional[int] = None
    progress_ms: Optional[int] = None
    title: str = ""
    history_key: Optional[str] = None


@dataclass(frozen=True)
class PlexHistoryPage:
    items: List[PlexHistoryItem]
    total_size: Optional[int]
    size: int
    start: int
    skipped: int = 0
    missing_identity: int = 0


def normalize_plex_history(
    row: PlexHistoryItem,
    *,
    server_machine_id: str,
) -> WatchEventInput:
    """Normalize a parsed Plex history row without inventing absent fields."""
    return WatchEventInput(
        source="plex_history",
        source_event_id=row.history_key,
        source_event_kind="history_played",
        server_machine_id=server_machine_id,
        source_user_key=row.account_id,
        rating_key=row.rating_key,
        parent_rating_key=row.parent_rating_key,
        media_type=row.media_type,  # type: ignore[arg-type]
        occurred_at_ms=row.viewed_at_ms,
        progress_ms=row.progress_ms,
        duration_ms=row.duration_ms,
        terminal=True,
        manual=False,
    )


def normalize_plex_history_element(
    element: ElementTree.Element,
    *,
    server_machine_id: str,
) -> Optional[WatchEventInput]:
    """Map one Plex history Video/Directory row to a normalized event."""
    attrib = element.attrib
    media_type = str(attrib.get("type") or "").strip().lower()
    if media_type not in {"movie", "episode"}:
        return None
    rating_key = str(attrib.get("ratingKey") or "").strip()
    if not rating_key:
        return None
    account_id = str(attrib.get("accountID") or attrib.get("accountId") or "").strip()
    if not account_id:
        return None
    viewed_at = optional_int(attrib.get("viewedAt"))
    if viewed_at is None:
        return None
    # Plex viewedAt is usually epoch seconds.
    occurred_at_ms = int(viewed_at) * 1000 if viewed_at < 10_000_000_000 else int(viewed_at)
    parent = str(attrib.get("grandparentRatingKey") or attrib.get("parentRatingKey") or "").strip() or None
    source_event_id = str(attrib.get("historyKey") or "").strip() or None
    return WatchEventInput(
        source="plex_history",
        source_event_id=source_event_id,
        source_event_kind="history_played",
        server_machine_id=server_machine_id,
        source_user_key=account_id,
        rating_key=rating_key,
        parent_rating_key=parent,
        media_type=media_type,  # type: ignore[arg-type]
        occurred_at_ms=occurred_at_ms,
        progress_ms=optional_int(attrib.get("viewOffset")),
        duration_ms=optional_int(attrib.get("duration")),
        terminal=True,
        manual=False,
    )


def parse_history_page(
    root: ElementTree.Element,
    *,
    server_machine_id: str,
    start: int = 0,
) -> tuple[PlexHistoryPage, List[WatchEventInput]]:
    container = root if root.tag == "MediaContainer" else root.find("MediaContainer")
    if container is None:
        container = root
    total_size = optional_int(container.attrib.get("totalSize"))
    items: List[PlexHistoryItem] = []
    events: List[WatchEventInput] = []
    skipped = 0
    missing_identity = 0
    history_rows = [
        element for element in list(container) if element.tag in {"Video", "Directory"}
    ]
    for element in history_rows:
        event = normalize_plex_history_element(element, server_machine_id=server_machine_id)
        if event is None:
            skipped += 1
            if not str(
                element.attrib.get("accountID")
                or element.attrib.get("accountId")
                or ""
            ).strip():
                missing_identity += 1
            continue
        events.append(event)
        items.append(
            PlexHistoryItem(
                rating_key=event.rating_key,
                media_type=event.media_type,
                account_id=event.source_user_key,
                viewed_at_ms=event.occurred_at_ms,
                parent_rating_key=event.parent_rating_key,
                duration_ms=event.duration_ms,
                progress_ms=event.progress_ms,
                title=str(element.attrib.get("title") or ""),
                history_key=event.source_event_id,
            )
        )
    page = PlexHistoryPage(
        items=items,
        total_size=total_size,
        # Advance by rows returned by Plex, not rows we could normalize. A
        # malformed row must not make the next request replay this page forever.
        size=optional_int(container.attrib.get("size")) or len(history_rows),
        start=start,
        skipped=skipped,
        missing_identity=missing_identity,
    )
    return page, events


def history_page(
    client: PlexClient,
    *,
    start: int = 0,
    size: int = 250,
    since_ms: Optional[int] = None,
) -> tuple[PlexHistoryPage, List[WatchEventInput]]:
    """Fetch one page of Plex `/status/sessions/history/all`."""
    params: dict[str, str] = {
        "X-Plex-Container-Start": str(max(0, int(start))),
        "X-Plex-Container-Size": str(max(1, min(int(size), 500))),
    }
    if since_ms is not None:
        params["viewedAt>"] = str(max(0, int(since_ms) // 1000))
    query = urllib.parse.urlencode(params)
    path = f"/status/sessions/history/all?{query}"
    machine_id = client.machine_identifier()
    root = client._request_xml(path)
    return parse_history_page(root, server_machine_id=machine_id, start=start)
