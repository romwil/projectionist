"""Headlines from public RSS: Google News (local search, country front page), BBC World.

Each title is shown as published with its source. Nothing here rewrites a title.
"""

from __future__ import annotations

import re
import urllib.parse
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional

from projectionist.theater.weather_channel.http import Fetcher, WeatherFetchError
from projectionist.theater.weather_channel.place import GOOGLE_NEWS_ENGLISH_EDITIONS, Place

GOOGLE_NEWS_SEARCH_URL = "https://news.google.com/rss/search"
GOOGLE_NEWS_TOP_URL = "https://news.google.com/rss"
BBC_WORLD_URL = "https://feeds.bbci.co.uk/news/world/rss.xml"
PER_SCOPE = 4


def _edition(code: str) -> Dict[str, str]:
    cc = code if code in GOOGLE_NEWS_ENGLISH_EDITIONS else "US"
    return {"hl": f"en-{cc}", "gl": cc, "ceid": f"{cc}:en"}


def headline_feeds(place: Place) -> List[Dict[str, str]]:
    """Feeds for this place: local (city search), national (country), world."""
    feeds: List[Dict[str, str]] = []
    code = place.country_code
    if code and place.city:
        query = " ".join(part for part in (place.city, place.region) if part)
        params = urllib.parse.urlencode({"q": query, **_edition(code)})
        feeds.append({"scope": "local", "label": place.city, "url": f"{GOOGLE_NEWS_SEARCH_URL}?{params}"})
    if code and code in GOOGLE_NEWS_ENGLISH_EDITIONS:
        params = urllib.parse.urlencode(_edition(code))
        feeds.append({"scope": "national", "label": place.country, "url": f"{GOOGLE_NEWS_TOP_URL}?{params}"})
    feeds.append({"scope": "world", "label": "World", "url": BBC_WORLD_URL})
    return feeds


def _text(node: Optional[ET.Element]) -> str:
    return " ".join(str(node.text or "").split()) if node is not None else ""


def parse_rss(body: bytes, *, default_source: str = "") -> List[Dict[str, str]]:
    if b"<!ENTITY" in body[:4096]:
        raise WeatherFetchError("RSS with entity declarations refused")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise WeatherFetchError("Bad RSS") from exc
    items: List[Dict[str, str]] = []
    for item in root.iter("item"):
        title = _text(item.find("title"))
        source = _text(item.find("source")) or default_source
        if not title:
            continue
        if source and title.endswith(f" - {source}"):
            title = title[: -len(f" - {source}")].rstrip()
        elif not source:
            match = re.match(r"^(.*\S) - ([^-]{2,60})$", title)
            if match:
                title, source = match.group(1), match.group(2).strip()
        items.append({"title": title[:240], "source": (source or "Unknown source")[:80]})
    return items


def fetch_headlines(place: Place, *, fetch: Optional[Fetcher] = None) -> Dict[str, Any]:
    """Returns ``{"scopes": [...], "failed": [...]}``. A failed feed is left out."""
    from projectionist.theater.weather_channel.http import default_fetch

    loader = fetch or default_fetch
    scopes: List[Dict[str, Any]] = []
    failed: List[str] = []
    seen_titles = set()
    for feed in headline_feeds(place):
        try:
            result = loader(feed["url"], headers={"Accept": "application/rss+xml, application/xml"})
            items = parse_rss(result.body, default_source="BBC News" if feed["scope"] == "world" else "")
        except WeatherFetchError:
            failed.append(feed["scope"])
            continue
        unique = []
        for item in items:
            key = item["title"].lower()
            if key in seen_titles:
                continue
            seen_titles.add(key)
            unique.append(item)
            if len(unique) >= PER_SCOPE:
                break
        if unique:
            scopes.append({"scope": feed["scope"], "label": feed["label"], "items": unique})
    return {"scopes": scopes, "failed": failed}
