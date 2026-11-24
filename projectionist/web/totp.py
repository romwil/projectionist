"""Time-based sign-in codes and one-time recovery codes (SEC-019).

The secret and the recovery-code hashes live on the account row. Nothing here is logged.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from typing import List, Optional
from urllib.parse import quote

DIGITS = 6
STEP_SECONDS = 30
WINDOW = 1
RECOVERY_COUNT = 8
ISSUER = "Projectionist"

SIGN_IN_CODE_REQUIRED = "A sign-in code is required."
SIGN_IN_CODE_SETUP = "Set up a sign-in code to finish signing in."
SIGN_IN_CODE_INVALID = "That sign-in code isn't valid."

_RECOVERY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class SignInCodeRequired(Exception):
    """The password matched and a sign-in code is still needed. Not a failed guess."""


class SignInCodeEnrollment(Exception):
    """The password matched and a sign-in code has not been confirmed yet."""

    def __init__(self, *, secret: str, otpauth_uri: str, recovery_codes: List[str]) -> None:
        self.secret = secret
        self.otpauth_uri = otpauth_uri
        self.recovery_codes = recovery_codes


def new_secret() -> str:
    """160-bit base32 secret, without padding."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _secret_bytes(secret: str) -> bytes:
    padded = str(secret or "").strip().upper()
    padded += "=" * ((8 - len(padded) % 8) % 8)
    return base64.b32decode(padded, casefold=True)


def totp_at(secret: str, counter: int) -> str:
    digest = hmac.new(_secret_bytes(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10**DIGITS)).zfill(DIGITS)


def current_code(secret: str, *, now: Optional[float] = None) -> str:
    moment = time.time() if now is None else now
    return totp_at(secret, int(moment // STEP_SECONDS))


def totp_matches(secret: str, code: str, *, now: Optional[float] = None) -> bool:
    cleaned = "".join(ch for ch in str(code or "") if ch.isdigit())
    if len(cleaned) != DIGITS or not secret:
        return False
    moment = time.time() if now is None else now
    counter = int(moment // STEP_SECONDS)
    for delta in range(-WINDOW, WINDOW + 1):
        if hmac.compare_digest(totp_at(secret, counter + delta), cleaned):
            return True
    return False


def otpauth_uri(secret: str, account: str) -> str:
    label = quote(f"{ISSUER}:{account}", safe="")
    issuer = quote(ISSUER, safe="")
    return (
        f"otpauth://totp/{label}?secret={secret}&issuer={issuer}"
        f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}"
    )


def _recovery_plain() -> List[str]:
    codes: List[str] = []
    for _ in range(RECOVERY_COUNT):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(8))
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def hash_recovery(code: str) -> str:
    normalized = "".join(ch for ch in str(code or "").upper() if ch.isalnum())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def new_recovery_codes() -> tuple[List[str], str]:
    """Plain codes for the one response that shows them, and the JSON hashes to store."""
    codes = _recovery_plain()
    return codes, json.dumps([hash_recovery(code) for code in codes])


def take_recovery_code(raw_json: str, code: str) -> Optional[str]:
    """Return the remaining hash list when ``code`` matches one entry. None otherwise."""
    try:
        parsed = json.loads(raw_json or "[]")
    except ValueError:
        return None
    if not isinstance(parsed, list):
        return None
    digest = hash_recovery(code)
    kept: List[str] = []
    found = False
    for item in parsed:
        text = str(item)
        if not found and hmac.compare_digest(text, digest):
            found = True
            continue
        kept.append(text)
    if not found:
        return None
    return json.dumps(kept)
