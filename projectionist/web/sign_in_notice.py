"""Tell the household about a new browser or device (SEC-025).

The owner gets an inbox letter. The account holder gets email when an address
is set. Push stays NAT-006. A repeat visit from the same browser is quiet.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from projectionist.mail import mail_configured, send_mail
from projectionist.mail.links import app_base_url, lifecycle_footer, text_to_html
from projectionist.mail.unsubscribe import unsubscribe_url
from projectionist.notifications.service import (
    deliver_notification,
    resolve_notification_email,
)
from projectionist.web.session_tokens import hash_session_jti, parse_session_claims

logger = logging.getLogger(__name__)

SIGN_IN_TITLE = "New sign-in"
_MAX_SESSIONS = 8


def browser_label(user_agent: str) -> str:
    cleaned = " ".join(str(user_agent or "").split())
    if not cleaned:
        return "a browser"
    return f"a browser ({cleaned[:80]})"


def _fingerprint(user_id: str, user_agent: str) -> str:
    material = f"{user_id}\n{user_agent}".encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _load_hashes(raw: str) -> list[list[Any]]:
    try:
        parsed = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    kept = []
    for item in parsed:
        if isinstance(item, list) and len(item) == 2 and item[0]:
            kept.append([str(item[0]), float(item[1] or 0)])
    return kept[-_MAX_SESSIONS:]


def remember_browser_sign_in(db: Any, request: Any, *, user_id: str, token: str) -> bool:
    """Record this browser. True only the first time it signs in to this account."""
    claims = parse_session_claims(token)
    if not claims or not user_id:
        return False
    user_agent = str(request.headers.get("user-agent") or "") if request is not None else ""
    fingerprint = _fingerprint(user_id, user_agent)
    label = browser_label(user_agent)
    jti = str(claims.get("jti") or "")
    jti_hash = hash_session_jti(jti) if jti else ""
    expires_at = float(claims.get("exp") or 0)
    created = _record_browser(
        db,
        user_id=user_id,
        fingerprint=fingerprint,
        label=label,
        jti_hash=jti_hash,
        expires_at=expires_at,
    )
    if not created:
        return False
    notice_new_sign_in(db, request, user_id=user_id, label=label, kind="browser")
    return True


def _record_browser(
    db: Any,
    *,
    user_id: str,
    fingerprint: str,
    label: str,
    jti_hash: str,
    expires_at: float,
) -> bool:
    """Insert a new browser row, or attach this session to the one already known."""

    def _write() -> bool:
        with db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, session_jti_hashes
                FROM sign_in_clients
                WHERE user_id = ? AND fingerprint = ? AND revoked_at IS NULL
                """,
                (user_id, fingerprint),
            ).fetchone()
            if row is not None:
                hashes = _load_hashes(str(row["session_jti_hashes"] or "[]"))
                if jti_hash and not any(item[0] == jti_hash for item in hashes):
                    hashes.append([jti_hash, expires_at])
                    conn.execute(
                        "UPDATE sign_in_clients SET session_jti_hashes = ? WHERE id = ?",
                        (json.dumps(hashes[-_MAX_SESSIONS:]), row["id"]),
                    )
                return False
            conn.execute(
                """
                INSERT INTO sign_in_clients (
                    id, user_id, kind, label, fingerprint, session_jti_hashes, created_at
                ) VALUES (?, ?, 'browser', ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    user_id,
                    label,
                    fingerprint,
                    json.dumps([[jti_hash, expires_at]] if jti_hash else []),
                    time.time(),
                ),
            )
            return True

    return bool(db.run_write(_write, label="sign_in_client"))


def notice_new_sign_in(
    db: Any,
    request: Any,
    *,
    user_id: str,
    label: str,
    kind: str,
) -> None:
    """Inbox the owner. Email the account holder when an address is set. Never raises."""
    try:
        _deliver(db, request, user_id=user_id, label=label, kind=kind)
    except Exception:
        logger.warning("Sign-in notice could not be delivered", exc_info=True)


def _deliver(db: Any, request: Any, *, user_id: str, label: str, kind: str) -> None:
    from projectionist.config_store import load_merged_settings
    from projectionist.web.ingress import request_is_external

    settings = load_merged_settings(Path(os.environ.get("DATA_DIR", "/config")))
    row = db.get_user(user_id)
    if row is None:
        return
    holder = db._row_to_user(row)
    name = str(holder.get("preferred_name") or holder.get("display_name") or "Someone").strip()
    where = "from outside the house" if request is not None and request_is_external(request) else "on the home network"
    body = f"{name} signed in on {label}, {where}."
    payload = {"event": "sign_in", "kind": kind, "path": "/settings/apple-tv"}
    emailed: set[str] = set()
    for owner in db.list_users(limit=200):
        if str(owner.get("role") or "") != "owner":
            continue
        result = deliver_notification(
            db,
            settings,
            user_id=str(owner["id"]),
            kind="account",
            title=SIGN_IN_TITLE,
            body=body,
            payload=payload,
            from_user_id=user_id,
            force_inbox=True,
        )
        if result.get("emailed"):
            emailed.add(str(owner["id"]))
    if user_id in emailed:
        return
    to_email = resolve_notification_email(holder)
    if not to_email or not mail_configured(settings):
        return
    try:
        one_click = unsubscribe_url(app_base_url(settings), db, user_id, "account")
    except Exception:
        logger.warning("Sign-in notice has no unsubscribe link", exc_info=True)
        one_click = None
    footer = lifecycle_footer(settings, unsubscribe_url=one_click)
    send_mail(
        settings,
        to_email=to_email,
        subject=SIGN_IN_TITLE,
        body_text=f"{body}\n\n{footer.text}",
        body_html=text_to_html(body) + footer.html,
        list_unsubscribe=footer.list_unsubscribe,
        one_click=footer.one_click,
    )


def list_sign_in_clients(db: Any) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.user_id, c.label, c.kind, c.created_at,
                   u.display_name, u.role, u.is_youth
            FROM sign_in_clients c
            LEFT JOIN users u ON u.id = c.user_id
            WHERE c.revoked_at IS NULL
            ORDER BY c.created_at DESC
            """
        ).fetchall()
    clients = []
    for row in rows:
        clients.append(
            {
                "id": str(row["id"]),
                "label": str(row["label"] or "a browser"),
                "kind": str(row["kind"] or "browser"),
                "user_id": str(row["user_id"] or ""),
                "display_name": str(row["display_name"] or ""),
                "role": str(row["role"] or "member"),
                "is_youth": bool(int(row["is_youth"] or 0)) if row["is_youth"] is not None else False,
                "created_at": float(row["created_at"] or 0),
            }
        )
    return clients


def get_sign_in_client(db: Any, client_id: str) -> Optional[dict[str, Any]]:
    cleaned = str(client_id or "").strip()
    if not cleaned:
        return None
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, revoked_at
            FROM sign_in_clients
            WHERE id = ?
            """,
            (cleaned,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": str(row["id"]),
        "user_id": str(row["user_id"] or ""),
        "revoked": row["revoked_at"] is not None,
    }


def revoke_sign_in_client(db: Any, client_id: str) -> Optional[dict[str, Any]]:
    """Mark the browser revoked and retire the session cookies it opened."""
    cleaned = str(client_id or "").strip()
    if not cleaned:
        return None

    def _write() -> Optional[dict[str, Any]]:
        with db.connect() as conn:
            row = conn.execute(
                """
                SELECT id, user_id, session_jti_hashes, revoked_at
                FROM sign_in_clients
                WHERE id = ?
                """,
                (cleaned,),
            ).fetchone()
            if row is None:
                return None
            if row["revoked_at"] is not None:
                return {"id": str(row["id"]), "user_id": str(row["user_id"] or ""), "already": True}
            conn.execute(
                "UPDATE sign_in_clients SET revoked_at = ? WHERE id = ?",
                (time.time(), cleaned),
            )
            return {
                "id": str(row["id"]),
                "user_id": str(row["user_id"] or ""),
                "already": False,
                "sessions": _load_hashes(str(row["session_jti_hashes"] or "[]")),
            }

    found = db.run_write(_write, label="revoke_sign_in_client")
    if not found or found.get("already"):
        return found
    for digest, expires_at in found.get("sessions") or []:
        db.revoke_session_jti(str(digest), expires_at=float(expires_at or 0))
    return {"id": found["id"], "user_id": found["user_id"], "already": False}
