"""Plex account validation and Overseerr-style PIN login helpers."""

from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlencode

from curatorx.connectors.http import request_json

PLEX_PRODUCT = "CuratorX"
PLEX_VERSION = "Plex OAuth"
CLIENT_ID_FILENAME = "plex_oauth_client_id"


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/config"))


def get_or_create_client_id(data_dir: Optional[Path] = None) -> str:
    """Stable per-install client identifier for plex.tv PIN auth."""
    root = data_dir or _data_dir()
    root.mkdir(parents=True, exist_ok=True)
    path = root / CLIENT_ID_FILENAME
    if path.exists():
        existing = path.read_text(encoding="utf-8").strip()
        if existing:
            return existing
    client_id = str(uuid.uuid4())
    path.write_text(client_id + "\n", encoding="utf-8")
    return client_id


def plex_oauth_headers(client_id: str) -> Dict[str, str]:
    return {
        "Accept": "application/json",
        "X-Plex-Product": PLEX_PRODUCT,
        "X-Plex-Version": PLEX_VERSION,
        "X-Plex-Client-Identifier": client_id,
        "X-Plex-Model": "Plex OAuth",
        "X-Plex-Platform": "Web",
        "X-Plex-Platform-Version": "Unknown",
        "X-Plex-Device": "Web",
        "X-Plex-Device-Name": f"Web ({PLEX_PRODUCT})",
        "X-Plex-Language": "en",
    }


def build_plex_auth_url(client_id: str, code: str) -> str:
    params = {
        "clientID": client_id,
        "code": code,
        "context[device][product]": PLEX_PRODUCT,
        "context[device][version]": PLEX_VERSION,
        "context[device][platform]": "Web",
        "context[device][platformVersion]": "Unknown",
        "context[device][device]": "Web",
        "context[device][deviceName]": f"Web ({PLEX_PRODUCT})",
        "context[device][model]": "Plex OAuth",
        "context[device][layout]": "desktop",
    }
    return f"https://app.plex.tv/auth/#!?{urlencode(params)}"


def fetch_plex_account(auth_token: str, *, timeout: int = 20) -> Dict[str, Any]:
    payload = request_json(
        "https://plex.tv/api/v2/user",
        headers={
            "Accept": "application/json",
            "X-Plex-Token": auth_token.strip(),
        },
        timeout=timeout,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Plex account response")
    return payload


def create_plex_pin(
    client_id: Optional[str] = None,
    *,
    timeout: int = 20,
) -> Dict[str, Any]:
    """Create a plex.tv PIN for Overseerr-style link login."""
    resolved_client_id = (client_id or get_or_create_client_id()).strip()
    if not resolved_client_id:
        raise RuntimeError("Plex client identifier is required")

    payload = request_json(
        "https://plex.tv/api/v2/pins?strong=true",
        method="POST",
        headers=plex_oauth_headers(resolved_client_id),
        timeout=timeout,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Plex PIN create response")

    pin_id = payload.get("id")
    code = str(payload.get("code") or "").strip()
    if pin_id is None or not code:
        raise RuntimeError("Plex PIN response missing id or code")

    return {
        "id": int(pin_id),
        "code": code,
        "client_id": resolved_client_id,
        "auth_url": build_plex_auth_url(resolved_client_id, code),
        "expires_in": payload.get("expiresIn"),
        "expires_at": payload.get("expiresAt"),
    }


def fetch_plex_pin(
    pin_id: int,
    client_id: str,
    *,
    timeout: int = 20,
) -> Dict[str, Any]:
    """Poll a plex.tv PIN; authToken is set once the user authorizes."""
    payload = request_json(
        f"https://plex.tv/api/v2/pins/{int(pin_id)}",
        headers=plex_oauth_headers(client_id),
        timeout=timeout,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Unexpected Plex PIN poll response")
    return payload
