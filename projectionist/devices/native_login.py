"""Device credentials for native sign-in (NAT-002).

A native client sends ``client: {"kind": "iphone"|"ipad", "label": "..."}`` on a
sign-in request. The response includes a device credential once and does not
set ``curatorx_session``. Only the hash is stored, the same way a paired TV
is stored. The pair-code flow stays available.
"""

from __future__ import annotations

import secrets
import time
import uuid
from typing import Any, Dict, Optional

from projectionist.devices.pairing import CREDENTIAL_PREFIX, hash_secret
from projectionist.library.db._shared import begin_immediate

NATIVE_KINDS = frozenset({"iphone", "ipad"})
NATIVE_OIDC_REDIRECT = "projectionist://auth/callback"
NATIVE_JOIN_SCHEME = "projectionist://join"
_LABEL_LIMIT = 40
_KIND_DEFAULT_LABEL = {"iphone": "iPhone", "ipad": "iPad"}


class NativeClientError(Exception):
    """The native client object was present and not usable."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def native_label(kind: str, raw: Optional[str]) -> str:
    text = " ".join(str(raw or "").split())
    if not text:
        return _KIND_DEFAULT_LABEL.get(kind, "Phone")
    return text[:_LABEL_LIMIT]


def parse_native_client(value: Any) -> Optional[Dict[str, str]]:
    """Return ``{kind, label}``, or None when this request is the browser.

    A missing client keeps the cookie session. A present but unusable client
    is rejected so a native caller cannot fall through into a cookie.
    """
    if value is None:
        return None
    if not isinstance(value, dict):
        raise NativeClientError("client must be an object with kind and label")
    kind = str(value.get("kind") or "").strip().lower()
    if kind not in NATIVE_KINDS:
        raise NativeClientError("client.kind must be iphone or ipad")
    return {"kind": kind, "label": native_label(kind, value.get("label"))}


def issue_device_credential(
    db: Any, *, user_id: str, kind: str, label: str
) -> Dict[str, str]:
    """Mint one device credential. The plaintext is returned and not stored."""
    if kind not in NATIVE_KINDS:
        raise NativeClientError("client.kind must be iphone or ipad")
    cleaned = native_label(kind, label)
    device_id = str(uuid.uuid4())
    credential = CREDENTIAL_PREFIX + secrets.token_urlsafe(32)
    digest = hash_secret(credential)
    now = time.time()

    def _write() -> Dict[str, str]:
        with db.connect() as conn:
            begin_immediate(conn)
            conn.execute(
                """
                INSERT INTO paired_devices (
                    id, user_id, label, credential_hash, created_at, kind
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (device_id, user_id, cleaned, digest, now, kind),
            )
        return {
            "device_id": device_id,
            "credential": credential,
            "kind": kind,
            "label": cleaned,
        }

    return db.run_write(_write, label="native_device_issue")


def attach_device_credential(body: Dict[str, Any], issued: Dict[str, str]) -> Dict[str, Any]:
    """Add the one-time credential fields. Callers must not set a session cookie."""
    merged = dict(body)
    merged["device_id"] = issued["device_id"]
    merged["credential"] = issued["credential"]
    merged["kind"] = issued["kind"]
    merged["label"] = issued["label"]
    return merged
