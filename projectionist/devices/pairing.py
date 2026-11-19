"""Apple TV sign-in codes, device credentials, and one throw intent per TV.

JSON the Apple TV client must match
------------------------------------
``POST /api/devices/pair/issue`` and ``POST /api/devices/pair/rotate`` (unsigned).
Rotate body is ``{"pending_id": "<id>"}``. Success::

    {"pending_id", "code", "expires_in_minutes", "expires_at", "status": "pending"}

``code`` is ``XXXX-XXXX`` from an alphabet with no 0, O, 1, or I.
``expires_in_minutes`` is the full lifetime (5). ``expires_at`` is unix seconds.
No ``credential`` field.

``GET /api/devices/pair/pending/{pending_id}`` (unsigned). Waiting::

    {"status": "pending", "pending_id", "expires_in_minutes", "expires_at"}

First poll after claim::

    {"status": "claimed", "pending_id", "device_id", "credential", "member"}

``member`` is ``{"id", "display_name", "role", "is_youth"}``.
``credential`` is returned once. Later polls are HTTP 410::

    {"status": "issue_again", "detail": ISSUE_AGAIN_DETAIL}

Unknown pending ids use that same 410 body. Rotate of an unknown or
already-claimed pending id does too. Rotate of an expired, still-unclaimed
pending id mints a new code on the same id.

``POST /api/devices/pair/claim`` (cookie session). Body ``{"code": "..."}``.
Success has ``status``, ``device_id``, ``label``, ``pending_id`` and no
credential. The browser keeps ``curatorx_session``.

Later member calls send ``Authorization: Bearer <credential>``.
A revoked credential is HTTP 401 ``{"detail": DEVICE_REVOKED_DETAIL}``.

``POST /api/devices/{id}/throw`` (cookie session). One intent, replaced by
the next throw. Title body::

    {"kind": "title", "media_type": "movie"|"show", "item_id", "id_type": "rating_key"}

Station body: ``{"kind": "station", "station_id": "..."}``.

``GET /api/devices/me/intent`` (device bearer) returns ``{"intent": null}`` or
the intent once, then null. Title intent fields: ``id``, ``kind``,
``media_type``, ``item_id``, ``id_type``. Station intent fields: ``id``,
``kind``, ``station_id``.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import uuid
from typing import Any, Dict, Optional

from projectionist.library.db._shared import begin_immediate

PAIR_CODE_TTL_SECONDS = 5 * 60
PAIR_CODE_TTL_MINUTES = 5
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8
DEFAULT_LABEL = "Apple TV"
CREDENTIAL_PREFIX = "cxd_"

ISSUE_AGAIN_DETAIL = "This code is no longer valid. Show a new one."
CLAIM_INVALID_DETAIL = "That code is not valid. Ask the TV for a new one."
CLAIM_EXPIRED_DETAIL = "That code expired. Ask the TV for a new one."
CLAIM_USED_DETAIL = "That code was already used."
DEVICE_REVOKED_DETAIL = "This Apple TV was removed. Enter a new code in Projectionist."
THROW_UNPAIRED_DETAIL = "That Apple TV is not paired."
THROW_REVOKED_DETAIL = (
    "That Apple TV was removed. It needs a new code before you can send something to it."
)
YOUTH_TITLE_DETAIL = "That title is above this Apple TV's rating limit."
YOUTH_STATION_DETAIL = "That station is above this Apple TV's rating limit."
TITLE_MISSING_DETAIL = "That title is not in the library."
TITLE_HIDDEN_DETAIL = "Title not available"
INTENT_NOT_TV_DETAIL = "Sign in from the Apple TV to read what was sent to it."
REVOKE_FORBIDDEN_DETAIL = (
    "Only the household owner, or the person this TV is signed in as, can remove it."
)
ALREADY_REVOKED_DETAIL = "That Apple TV was already removed."

_PENDING_ID = re.compile(r"^[A-Za-z0-9_-]{16,80}$")
_DEVICE_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


class DevicePairError(Exception):
    """Plain-language pairing or throw failure."""

    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = int(status_code)


def _now() -> float:
    return time.time()


def hash_secret(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def normalize_code(raw: str) -> str:
    return "".join(ch for ch in str(raw or "").upper() if ch.isalnum())


def code_is_well_formed(normalized: str) -> bool:
    if len(normalized) != CODE_LENGTH:
        return False
    return all(ch in CODE_ALPHABET for ch in normalized)


def format_code(normalized: str) -> str:
    return f"{normalized[:4]}-{normalized[4:]}"


def clean_label(raw: Optional[str]) -> str:
    text = " ".join(str(raw or "").split())
    if not text:
        return DEFAULT_LABEL
    return text[:40]


def _issue_again() -> Dict[str, Any]:
    return {"http": 410, "body": {"status": "issue_again", "detail": ISSUE_AGAIN_DETAIL}}


def _new_code(conn: Any) -> str:
    for _ in range(8):
        raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        digest = hash_secret(raw)
        taken = conn.execute(
            "SELECT 1 FROM device_pair_pending WHERE code_hash = ?",
            (digest,),
        ).fetchone()
        if taken is None:
            return raw
    raise DevicePairError("Could not make a sign-in code. Try again.", status_code=503)


def _purge_stale_pending(conn: Any, now: float) -> None:
    conn.execute(
        """
        DELETE FROM device_pair_pending
        WHERE claimed_at IS NULL AND expires_at < ?
        """,
        (now - 3600,),
    )


def issue_pair(db: Any, *, label: Optional[str] = None) -> Dict[str, Any]:
    """Start an unsigned sign-in. The response never includes a credential."""
    cleaned = clean_label(label)
    now = _now()
    expires_at = now + PAIR_CODE_TTL_SECONDS
    pending_id = secrets.token_urlsafe(18)

    def _write() -> Dict[str, Any]:
        with db.connect() as conn:
            begin_immediate(conn)
            _purge_stale_pending(conn, now)
            raw = _new_code(conn)
            conn.execute(
                """
                INSERT INTO device_pair_pending (
                    id, code_hash, expires_at, created_at, label
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (pending_id, hash_secret(raw), expires_at, now, cleaned),
            )
            return {
                "pending_id": pending_id,
                "code": format_code(raw),
                "expires_in_minutes": PAIR_CODE_TTL_MINUTES,
                "expires_at": int(expires_at),
                "status": "pending",
            }

    return db.run_write(_write, label="device_pair_issue")


def rotate_pair(db: Any, pending_id: str) -> Dict[str, Any]:
    """Replace the code on an unclaimed pending sign-in, including an expired one."""
    pending = str(pending_id or "").strip()
    if not _PENDING_ID.match(pending):
        return _issue_again()
    now = _now()
    expires_at = now + PAIR_CODE_TTL_SECONDS

    def _write() -> Dict[str, Any]:
        with db.connect() as conn:
            begin_immediate(conn)
            row = conn.execute(
                "SELECT claimed_at, label FROM device_pair_pending WHERE id = ?",
                (pending,),
            ).fetchone()
            if row is None or row["claimed_at"] is not None:
                return _issue_again()
            raw = _new_code(conn)
            conn.execute(
                """
                UPDATE device_pair_pending
                SET code_hash = ?, expires_at = ?, created_at = ?
                WHERE id = ? AND claimed_at IS NULL
                """,
                (hash_secret(raw), expires_at, now, pending),
            )
            return {
                "http": 200,
                "body": {
                    "pending_id": pending,
                    "code": format_code(raw),
                    "expires_in_minutes": PAIR_CODE_TTL_MINUTES,
                    "expires_at": int(expires_at),
                    "status": "pending",
                },
            }

    return db.run_write(_write, label="device_pair_rotate")


def poll_pending(db: Any, pending_id: str) -> Dict[str, Any]:
    """Waiting, the credential once, or issue-again."""
    pending = str(pending_id or "").strip()
    if not _PENDING_ID.match(pending):
        return _issue_again()
    now = _now()

    def _write() -> Dict[str, Any]:
        with db.connect() as conn:
            begin_immediate(conn)
            row = conn.execute(
                "SELECT * FROM device_pair_pending WHERE id = ?",
                (pending,),
            ).fetchone()
            if row is None:
                return _issue_again()
            if row["claimed_at"] is None:
                if float(row["expires_at"]) <= now:
                    return _issue_again()
                remaining = float(row["expires_at"]) - now
                minutes = max(1, int((remaining + 59) // 60))
                return {
                    "http": 200,
                    "body": {
                        "status": "pending",
                        "pending_id": pending,
                        "expires_in_minutes": minutes,
                        "expires_at": int(row["expires_at"]),
                    },
                }
            secret = row["credential_secret"]
            if not secret:
                return _issue_again()
            cursor = conn.execute(
                """
                UPDATE device_pair_pending
                SET credential_secret = NULL
                WHERE id = ? AND credential_secret IS NOT NULL
                """,
                (pending,),
            )
            if int(cursor.rowcount or 0) != 1:
                return _issue_again()
            return {
                "http": 200,
                "body": {
                    "status": "claimed",
                    "pending_id": pending,
                    "device_id": str(row["device_id"]),
                    "credential": str(secret),
                    "user_id": str(row["user_id"]),
                },
            }

    return db.run_write(_write, label="device_pair_poll")


def claim_pair(db: Any, *, code: str, user_id: str, label: Optional[str] = None) -> Dict[str, Any]:
    """Consume a code once and bind ``user_id`` to a new device credential."""
    normalized = normalize_code(code)
    if not code_is_well_formed(normalized):
        raise DevicePairError(CLAIM_INVALID_DETAIL, status_code=400)
    digest = hash_secret(normalized)
    now = _now()
    device_id = str(uuid.uuid4())
    credential = CREDENTIAL_PREFIX + secrets.token_urlsafe(32)
    credential_hash = hash_secret(credential)
    override = clean_label(label) if label else None

    def _write() -> Dict[str, Any]:
        with db.connect() as conn:
            begin_immediate(conn)
            row = conn.execute(
                "SELECT * FROM device_pair_pending WHERE code_hash = ?",
                (digest,),
            ).fetchone()
            if row is None:
                raise DevicePairError(CLAIM_INVALID_DETAIL, status_code=400)
            if row["claimed_at"] is not None:
                raise DevicePairError(CLAIM_USED_DETAIL, status_code=409)
            if float(row["expires_at"]) <= now:
                raise DevicePairError(CLAIM_EXPIRED_DETAIL, status_code=400)
            device_label = override or str(row["label"] or DEFAULT_LABEL)
            cursor = conn.execute(
                """
                UPDATE device_pair_pending
                SET claimed_at = ?, user_id = ?, device_id = ?,
                    credential_hash = ?, credential_secret = ?, label = ?
                WHERE id = ? AND claimed_at IS NULL AND expires_at > ?
                """,
                (
                    now,
                    user_id,
                    device_id,
                    credential_hash,
                    credential,
                    device_label,
                    str(row["id"]),
                    now,
                ),
            )
            if int(cursor.rowcount or 0) != 1:
                raise DevicePairError(CLAIM_USED_DETAIL, status_code=409)
            conn.execute(
                """
                INSERT INTO paired_devices (
                    id, user_id, label, credential_hash, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (device_id, user_id, device_label, credential_hash, now),
            )
            return {
                "status": "claimed",
                "device_id": device_id,
                "label": device_label,
                "pending_id": str(row["id"]),
            }

    return db.run_write(_write, label="device_pair_claim")


def credential_status(db: Any, token: str) -> tuple[str, Optional[str]]:
    """``(active|revoked|unknown, user_id)``. Unknown tokens are not members."""
    secret = str(token or "").strip()
    if not secret.startswith(CREDENTIAL_PREFIX):
        return "unknown", None
    digest = hash_secret(secret)
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT user_id, revoked_at
            FROM paired_devices
            WHERE credential_hash = ?
            """,
            (digest,),
        ).fetchone()
    if row is None:
        return "unknown", None
    user_id = str(row["user_id"] or "")
    if row["revoked_at"] is not None:
        return "revoked", user_id or None
    if not user_id:
        return "unknown", None
    return "active", user_id


def device_for_credential(db: Any, token: str) -> Optional[Dict[str, Any]]:
    """Active device bound to this credential, or None when missing or revoked."""
    secret = str(token or "").strip()
    if not secret.startswith(CREDENTIAL_PREFIX):
        return None
    digest = hash_secret(secret)
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, label, revoked_at
            FROM paired_devices
            WHERE credential_hash = ?
            """,
            (digest,),
        ).fetchone()
    if row is None or row["revoked_at"] is not None:
        return None
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"]),
        "label": str(row["label"] or DEFAULT_LABEL),
    }


def list_devices(db: Any) -> list[Dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.user_id, d.label, d.created_at,
                   u.display_name, u.role, u.is_youth
            FROM paired_devices d
            LEFT JOIN users u ON u.id = d.user_id
            WHERE d.revoked_at IS NULL
            ORDER BY d.created_at DESC
            """
        ).fetchall()
    devices = []
    for row in rows:
        devices.append(
            {
                "id": str(row["id"]),
                "label": str(row["label"] or DEFAULT_LABEL),
                "user_id": str(row["user_id"] or ""),
                "display_name": str(row["display_name"] or ""),
                "role": str(row["role"] or "member"),
                "is_youth": bool(int(row["is_youth"] or 0))
                if row["is_youth"] is not None
                else False,
                "created_at": float(row["created_at"] or 0),
            }
        )
    return devices


def get_device(db: Any, device_id: str) -> Optional[Dict[str, Any]]:
    device = str(device_id or "").strip().lower()
    if not _DEVICE_ID.match(device):
        return None
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, label, revoked_at
            FROM paired_devices
            WHERE id = ?
            """,
            (device,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"] or ""),
        "label": str(row["label"] or DEFAULT_LABEL),
        "revoked": row["revoked_at"] is not None,
    }


def revoke_device(db: Any, device_id: str) -> None:
    device = get_device(db, device_id)
    if device is None:
        raise DevicePairError(THROW_UNPAIRED_DETAIL, status_code=404)
    if device["revoked"]:
        raise DevicePairError(ALREADY_REVOKED_DETAIL, status_code=409)
    now = _now()

    def _write() -> None:
        with db.connect() as conn:
            begin_immediate(conn)
            cursor = conn.execute(
                """
                UPDATE paired_devices
                SET revoked_at = ?
                WHERE id = ? AND revoked_at IS NULL
                """,
                (now, device["id"]),
            )
            if int(cursor.rowcount or 0) != 1:
                raise DevicePairError(ALREADY_REVOKED_DETAIL, status_code=409)
            conn.execute(
                "DELETE FROM device_throw_intents WHERE device_id = ?",
                (device["id"],),
            )

    db.run_write(_write, label="device_revoke")


def store_intent(db: Any, device_id: str, *, kind: str, payload: Dict[str, Any]) -> str:
    intent_id = str(uuid.uuid4())
    now = _now()
    body = json.dumps(payload, separators=(",", ":"), sort_keys=True)

    def _write() -> None:
        with db.connect() as conn:
            begin_immediate(conn)
            conn.execute(
                """
                INSERT INTO device_throw_intents (
                    device_id, intent_id, kind, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    intent_id = excluded.intent_id,
                    kind = excluded.kind,
                    payload_json = excluded.payload_json,
                    created_at = excluded.created_at
                """,
                (device_id, intent_id, kind, body, now),
            )

    db.run_write(_write, label="device_throw")
    return intent_id


def take_intent(db: Any, device_id: str) -> Optional[Dict[str, Any]]:
    """Return the current intent and remove it so the TV navigates once."""

    def _write() -> Optional[Dict[str, Any]]:
        with db.connect() as conn:
            begin_immediate(conn)
            row = conn.execute(
                """
                DELETE FROM device_throw_intents
                WHERE device_id = ?
                RETURNING intent_id, kind, payload_json
                """,
                (device_id,),
            ).fetchone()
            if row is None:
                return None
            try:
                payload = json.loads(str(row["payload_json"] or "{}"))
            except json.JSONDecodeError:
                payload = {}
            if not isinstance(payload, dict):
                payload = {}
            intent = {"id": str(row["intent_id"]), "kind": str(row["kind"])}
            intent.update(payload)
            return intent

    return db.run_write(_write, label="device_intent_take")
