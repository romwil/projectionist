"""OMDb client for optional long-synopsis enrichment.

Requires an operator-configured OMDb API key. Plot text is copied from OMDb
responses only — never invented locally.
"""

from __future__ import annotations

import urllib.parse
from typing import Any, Mapping, Optional

from curatorx.connectors.http import request_json

BASE = "https://www.omdbapi.com/"


class OMDbClient:
    def __init__(self, api_key: str, timeout: int = 20) -> None:
        self.api_key = str(api_key or "").strip()
        self.timeout = timeout

    def _get(self, **params: Any) -> Mapping[str, Any]:
        if not self.api_key:
            raise RuntimeError("OMDb API key is required")
        query = {"apikey": self.api_key, "plot": "full", **params}
        encoded = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
        payload = request_json(f"{BASE}?{encoded}", timeout=self.timeout)
        return payload if isinstance(payload, dict) else {}

    def plot_by_imdb(self, imdb_id: str) -> str:
        cleaned = str(imdb_id or "").strip()
        if not cleaned:
            return ""
        payload = self._get(i=cleaned)
        if str(payload.get("Response") or "").lower() != "true":
            return ""
        plot = str(payload.get("Plot") or "").strip()
        if plot.lower() in {"", "n/a"}:
            return ""
        return plot

    def plot_by_title(self, title: str, *, year: Optional[int] = None) -> str:
        cleaned = str(title or "").strip()
        if not cleaned:
            return ""
        params: dict[str, Any] = {"t": cleaned}
        if year is not None:
            params["y"] = int(year)
        payload = self._get(**params)
        if str(payload.get("Response") or "").lower() != "true":
            return ""
        plot = str(payload.get("Plot") or "").strip()
        if plot.lower() in {"", "n/a"}:
            return ""
        return plot
