"""The household's away address: an http(s) origin, nothing else.

Playlist and segment URLs stay relative. Clients join them to this origin
or to the home address. This module only checks the string the owner saved.
"""

from __future__ import annotations

from urllib.parse import urlsplit

_MAX_LENGTH = 200


class PublicBaseUrlError(ValueError):
    """The away address is not an origin a client can use."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def normalize_public_base_url(raw: str) -> str:
    """Return a scheme + host origin, or ``""`` when the owner clears it.

    Raises ``PublicBaseUrlError`` with a sentence a settings form can show.
    """
    text = str(raw or "").strip()
    if not text:
        return ""
    if len(text) > _MAX_LENGTH:
        raise PublicBaseUrlError("That address is too long.")
    if any(ch.isspace() for ch in text):
        raise PublicBaseUrlError("That address cannot contain a space.")
    parts = urlsplit(text)
    if parts.scheme not in {"http", "https"}:
        raise PublicBaseUrlError("Use an http or https address.")
    if parts.username or parts.password:
        raise PublicBaseUrlError("That address cannot include a username or password.")
    if parts.query or parts.fragment:
        raise PublicBaseUrlError("That address cannot include a query or a fragment.")
    host = parts.hostname
    if not host:
        raise PublicBaseUrlError("That address needs a host.")
    if parts.path not in {"", "/"}:
        raise PublicBaseUrlError("Use the site address only, without a path.")
    display_host = f"[{host}]" if ":" in host else host
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{display_host}{port}"


def sanitize_stored_public_base_url(raw: str) -> str:
    """Drop a stored value that is not an origin. Never raises.

    A bad settings file must not stop the household from starting.
    """
    try:
        return normalize_public_base_url(raw)
    except PublicBaseUrlError:
        return ""
