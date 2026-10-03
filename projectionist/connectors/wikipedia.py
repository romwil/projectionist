"""Wikipedia extract client for long-synopsis enrichment.

Uses the free MediaWiki Action API (no API key). Default ``long_synopsis_source``
is ``wikipedia``; set ``off`` to disable. We never invent plot text.
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Mapping, Optional

from projectionist.connectors.http import request_json

USER_AGENT = "CuratorX/1.0 (homelab media curator; https://github.com/willrompala/mediacurator)"
API = "https://en.wikipedia.org/w/api.php"


def _extract_from_payload(payload: Mapping[str, Any]) -> str:
    pages = (payload.get("query") or {}).get("pages") or {}
    if not isinstance(pages, dict):
        return ""
    for page in pages.values():
        if not isinstance(page, dict):
            continue
        if page.get("missing") is not None:
            continue
        extract = str(page.get("extract") or "").strip()
        if extract:
            return extract
    return ""


def fetch_extract(
    title: str,
    *,
    year: Optional[int] = None,
    media_type: str = "movie",
    timeout: int = 20,
    strict: bool = False,
) -> str:
    """Return a plain-text intro extract for *title*, or empty string.

    With ``strict=True`` a title that could not be looked up at all (every request
    failed) raises ``RuntimeError`` instead of looking like "Wikipedia has no
    page" — the retrieval task needs to tell an outage from a genuine miss.

    Tries the bare title first, then a disambiguated film/series form when year
    is known (e.g. ``Kill Bill: Volume 1 (2003 film)``).
    """
    cleaned = str(title or "").strip()
    if not cleaned:
        return ""

    candidates = [cleaned]
    if year is not None:
        kind = "film" if str(media_type or "").strip().lower() == "movie" else "TV series"
        candidates.append(f"{cleaned} ({int(year)} {kind})")
        candidates.append(f"{cleaned} ({int(year)} film)")

    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    answered = False
    last_error: Optional[RuntimeError] = None
    for candidate in candidates:
        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "exintro": "1",
            "explaintext": "1",
            "redirects": "1",
            "titles": candidate,
        }
        url = f"{API}?{urllib.parse.urlencode(params)}"
        try:
            payload = request_json(url, headers=headers, timeout=timeout)
        except RuntimeError as error:
            last_error = error
            continue
        if not isinstance(payload, dict):
            continue
        answered = True
        extract = _extract_from_payload(payload)
        if extract:
            return extract
    if strict and not answered and last_error is not None:
        raise last_error
    return ""
