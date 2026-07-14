"""Encrypt Plex account tokens at rest using the session secret."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from typing import Optional

from curatorx.web.session_tokens import resolve_session_secret

_VERSION = b"v1"
_NONCE_LEN = 16
_MAC_LEN = 32


def _key_material() -> bytes:
    secret = resolve_session_secret(persist=True).encode("utf-8")
    return hashlib.sha256(b"curatorx-plex-token-v1|" + secret).digest()


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(key, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def encrypt_plex_token(plaintext: str) -> str:
    cleaned = str(plaintext or "").strip()
    if not cleaned:
        raise ValueError("plex token is required")
    key = _key_material()
    nonce = secrets.token_bytes(_NONCE_LEN)
    raw = cleaned.encode("utf-8")
    cipher = bytes(a ^ b for a, b in zip(raw, _keystream(key, nonce, len(raw))))
    mac = hmac.new(key, _VERSION + nonce + cipher, hashlib.sha256).digest()
    blob = _VERSION + nonce + mac + cipher
    return base64.urlsafe_b64encode(blob).decode("ascii")


def decrypt_plex_token(token_enc: Optional[str]) -> Optional[str]:
    if not token_enc:
        return None
    try:
        blob = base64.urlsafe_b64decode(str(token_enc).encode("ascii"))
    except (ValueError, TypeError):
        return None
    if len(blob) < len(_VERSION) + _NONCE_LEN + _MAC_LEN:
        return None
    if not blob.startswith(_VERSION):
        return None
    offset = len(_VERSION)
    nonce = blob[offset : offset + _NONCE_LEN]
    offset += _NONCE_LEN
    mac = blob[offset : offset + _MAC_LEN]
    cipher = blob[offset + _MAC_LEN :]
    key = _key_material()
    expected = hmac.new(key, _VERSION + nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        return None
    plain = bytes(a ^ b for a, b in zip(cipher, _keystream(key, nonce, len(cipher))))
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError:
        return None
