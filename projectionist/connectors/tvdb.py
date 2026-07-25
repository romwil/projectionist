"""TVDB API v4 client."""

from __future__ import annotations

import time
from typing import Any, Mapping, Optional

from projectionist.connectors.http import request_json


class TVDBClient:
    def __init__(self, api_key: str, timeout: int = 30) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self._token: Optional[str] = None
        self._token_expires: float = 0

    @property
    def base_url(self) -> str:
        return "https://api4.thetvdb.com/v4"

    def _auth_headers(self) -> dict[str, str]:
        token = self._ensure_token()
        return {"Authorization": f"Bearer {token}"}

    def _ensure_token(self) -> str:
        if self._token and time.time() < self._token_expires:
            return self._token
        payload = request_json(
            f"{self.base_url}/login",
            method="POST",
            body={"apikey": self.api_key},
            timeout=self.timeout,
        )
        if not isinstance(payload, dict):
            raise RuntimeError("TVDB login failed")
        data = payload.get("data") or {}
        self._token = str(data.get("token") or "")
        self._token_expires = time.time() + 60 * 60 * 24 * 25
        if not self._token:
            raise RuntimeError("TVDB login returned no token")
        return self._token

    def series(self, tvdb_id: int) -> Mapping[str, Any]:
        payload = request_json(
            f"{self.base_url}/series/{tvdb_id}/extended",
            headers=self._auth_headers(),
            timeout=self.timeout,
        )
        if isinstance(payload, dict):
            return payload.get("data") or {}
        return {}
