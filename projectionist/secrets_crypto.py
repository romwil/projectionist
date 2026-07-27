"""Encrypt UI-persisted settings secrets at rest (Architecture A — H4 Hybrid).

Reuses the watchlist Plex-token crypto pattern (HMAC-SHA256 keystream + MAC).
Key preference order:

1. ``PROJECTIONIST_SECRETS_KEY`` (dedicated; back up with ``/config``)
2. Derived from the session secret under the same ``data_dir`` as settings.json

Plaintext values (no ``enc:v1:`` prefix) are accepted on read for migration.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional

from projectionist.envcompat import resolve_env

logger = logging.getLogger(__name__)

_VERSION = b"v1"
_NONCE_LEN = 16
_MAC_LEN = 32
_PREFIX = "enc:v1:"

# Top-level Settings fields that hold secrets when saved from the UI.
SETTINGS_SECRET_FIELDS = (
    "plex_token",
    "radarr_api_key",
    "sonarr_api_key",
    "tmdb_api_key",
    "tvdb_api_key",
    "fanart_api_key",
    "omdb_api_key",
    "tautulli_api_key",
    "llm_api_key",
    "webhook_secret",
    "mcp_api_key",
    "mcp_full_api_key",
)

NESTED_SECRET_PATHS = (
    ("seerr", "api_key"),
    ("mail", "smtp_password"),
    ("mail", "resend_api_key"),
    ("auth", "oidc_client_secret"),
    ("apprise", "urls"),
    ("apprise", "config"),
)


def _key_material(data_dir: Optional[Path] = None) -> bytes:
    dedicated = (resolve_env("PROJECTIONIST_SECRETS_KEY") or "").strip()
    if dedicated:
        return hashlib.sha256(
            b"projectionist-settings-secrets-v1|" + dedicated.encode("utf-8")
        ).digest()
    from projectionist.web.session_tokens import resolve_session_secret

    # Persist under the same data_dir as settings.json when provided so tests
    # and multi-config installs never touch a foreign /config path.
    secret = resolve_session_secret(data_dir=data_dir, persist=True).encode("utf-8")
    return hashlib.sha256(b"projectionist-settings-secrets-v1|" + secret).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def is_encrypted_secret(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def encrypt_secret(plaintext: str, *, data_dir: Optional[Path] = None) -> str:
    cleaned = str(plaintext or "")
    if not cleaned.strip():
        return ""
    if is_encrypted_secret(cleaned):
        return cleaned
    key = _key_material(data_dir)
    nonce = secrets.token_bytes(_NONCE_LEN)
    raw = cleaned.encode("utf-8")
    cipher = bytes(a ^ b for a, b in zip(raw, _keystream(key, nonce, len(raw))))
    mac = hmac.new(key, _VERSION + nonce + cipher, hashlib.sha256).digest()
    blob = _VERSION + nonce + mac + cipher
    return _PREFIX + base64.urlsafe_b64encode(blob).decode("ascii")


def decrypt_secret(value: Optional[str], *, data_dir: Optional[Path] = None) -> str:
    if value is None:
        return ""
    text = str(value)
    if not text:
        return ""
    if not is_encrypted_secret(text):
        return text
    try:
        blob = base64.urlsafe_b64decode(text[len(_PREFIX) :].encode("ascii"))
    except (ValueError, TypeError):
        logger.warning("Could not decode encrypted settings secret; treating as empty")
        return ""
    if len(blob) < len(_VERSION) + _NONCE_LEN + _MAC_LEN:
        return ""
    if not blob.startswith(_VERSION):
        return ""
    offset = len(_VERSION)
    nonce = blob[offset : offset + _NONCE_LEN]
    offset += _NONCE_LEN
    mac = blob[offset : offset + _MAC_LEN]
    cipher = blob[offset + _MAC_LEN :]
    key = _key_material(data_dir)
    expected = hmac.new(key, _VERSION + nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        logger.warning("Settings secret MAC mismatch (wrong PROJECTIONIST_SECRETS_KEY?)")
        return ""
    plain = bytes(a ^ b for a, b in zip(cipher, _keystream(key, nonce, len(cipher))))
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError:
        return ""


def decrypt_settings_mapping(
    data: Mapping[str, Any], *, data_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Return a shallow+nested copy with secret fields decrypted for runtime use."""
    out: Dict[str, Any] = dict(data)
    for field in SETTINGS_SECRET_FIELDS:
        if field in out and out[field] is not None:
            out[field] = decrypt_secret(str(out[field]), data_dir=data_dir)
    for parent, child in NESTED_SECRET_PATHS:
        nested = out.get(parent)
        if isinstance(nested, Mapping) and child in nested and nested[child] is not None:
            nested_copy = dict(nested)
            nested_copy[child] = decrypt_secret(str(nested[child]), data_dir=data_dir)
            out[parent] = nested_copy
    return out


def encrypt_settings_mapping(
    data: Mapping[str, Any], *, data_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """Return a copy with secret fields encrypted for disk."""
    out: Dict[str, Any] = dict(data)
    for field in SETTINGS_SECRET_FIELDS:
        if field in out and out[field] is not None and str(out[field]).strip():
            out[field] = encrypt_secret(str(out[field]), data_dir=data_dir)
    for parent, child in NESTED_SECRET_PATHS:
        nested = out.get(parent)
        if isinstance(nested, Mapping) and child in nested and str(nested.get(child) or "").strip():
            nested_copy = dict(nested)
            nested_copy[child] = encrypt_secret(str(nested_copy[child]), data_dir=data_dir)
            out[parent] = nested_copy
    return out


def mapping_needs_secret_migration(data: Mapping[str, Any]) -> bool:
    """True when any secret field is non-empty plaintext (needs encrypt-on-boot)."""
    for field in SETTINGS_SECRET_FIELDS:
        value = data.get(field)
        if value and str(value).strip() and not is_encrypted_secret(str(value)):
            return True
    for parent, child in NESTED_SECRET_PATHS:
        nested = data.get(parent)
        if not isinstance(nested, Mapping):
            continue
        value = nested.get(child)
        if value and str(value).strip() and not is_encrypted_secret(str(value)):
            return True
    return False


def strip_env_only_secrets_for_save(
    data: MutableMapping[str, Any],
    *,
    env_sources: Mapping[str, str],
) -> None:
    """Clear top-level secrets that should stay env-only (never persist from env)."""
    for field, source in env_sources.items():
        if source == "env" and field in data:
            data[field] = ""
