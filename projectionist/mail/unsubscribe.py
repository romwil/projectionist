"""One-click email unsubscribe (GRO-008).

A token names one person and one program and is signed with the session secret.
It can do exactly one thing: turn that program's email off for that person.
It is also bound to a per-person nonce stored in ``mail_unsubscribe_nonces``;
"Delete my data" and account removal delete the nonce, so older links stop
working. A token for another person fails the signature check.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

from projectionist.library.db import Database

UNSUBSCRIBE_PATH = "/api/mail/unsubscribe"

# Programs with an existing opt-in flag turn that flag off. The rest are muted
# for email only, so the inbox copy keeps arriving.
_OPT_IN_FLAGS: Dict[str, str] = {
    "digest": "newsletter_opt_in",
    "nudge": "nudge_opt_in",
    "year-in-review": "year_in_review_opt_in",
}

PROGRAM_LABELS: Dict[str, str] = {
    "digest": "the weekly newsletter",
    "nudge": "watch nudges",
    "year-in-review": "Year in Review",
    "arrival": "new-arrival emails",
    "recommendation": "recommendation emails",
    "library-share": "shared-title emails",
    "access-request": "join-request emails",
    "account": "account-change emails",
}


class UnsubscribeError(ValueError):
    """The token is malformed, forged, for a removed person, or from before a purge."""


@dataclass(frozen=True)
class UnsubscribeTarget:
    user_id: str
    kind: str


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _secret() -> bytes:
    from projectionist.web.session_tokens import resolve_session_secret

    return hashlib.sha256(b"mail-unsubscribe:" + resolve_session_secret().encode("utf-8")).digest()


def _sign(body: bytes) -> str:
    return _b64(hmac.new(_secret(), body, hashlib.sha256).digest())


def _nonce(db: Database, user_id: str, *, create: bool) -> Optional[str]:
    def _work() -> Optional[str]:
        with db.connect() as conn:
            row = conn.execute(
                "SELECT nonce FROM mail_unsubscribe_nonces WHERE user_id = ?", (user_id,)
            ).fetchone()
            if row is not None:
                return str(row["nonce"])
            if not create:
                return None
            exists = conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone()
            if exists is None:
                return None
            nonce = secrets.token_urlsafe(12)
            conn.execute(
                "INSERT OR IGNORE INTO mail_unsubscribe_nonces (user_id, nonce, created_at) VALUES (?, ?, ?)",
                (user_id, nonce, time.time()),
            )
            row = conn.execute(
                "SELECT nonce FROM mail_unsubscribe_nonces WHERE user_id = ?", (user_id,)
            ).fetchone()
            return str(row["nonce"]) if row else None

    if create:
        return db.run_write(_work, label="mail_unsubscribe_nonce")
    return _work()


def make_unsubscribe_token(db: Database, user_id: str, kind: str) -> Optional[str]:
    cleaned_kind = str(kind or "").strip().lower()
    if cleaned_kind not in PROGRAM_LABELS or not user_id:
        return None
    nonce = _nonce(db, str(user_id), create=True)
    if not nonce:
        return None
    body = json.dumps({"u": str(user_id), "k": cleaned_kind, "n": nonce}, separators=(",", ":")).encode()
    return f"{_b64(body)}.{_sign(body)}"


def resolve_unsubscribe_token(db: Database, token: str) -> UnsubscribeTarget:
    raw = str(token or "").strip()
    if not raw or raw.count(".") != 1 or len(raw) > 512:
        raise UnsubscribeError("This unsubscribe link is not valid.")
    body_part, sig = raw.split(".", 1)
    try:
        body = _unb64(body_part)
    except (ValueError, TypeError) as exc:
        raise UnsubscribeError("This unsubscribe link is not valid.") from exc
    if not hmac.compare_digest(_sign(body), sig):
        raise UnsubscribeError("This unsubscribe link is not valid.")
    try:
        claims = json.loads(body)
    except ValueError as exc:
        raise UnsubscribeError("This unsubscribe link is not valid.") from exc
    user_id = str(claims.get("u") or "")
    kind = str(claims.get("k") or "")
    nonce = str(claims.get("n") or "")
    if kind not in PROGRAM_LABELS or not user_id or not nonce:
        raise UnsubscribeError("This unsubscribe link is not valid.")
    current = _nonce(db, user_id, create=False)
    if not current or not hmac.compare_digest(current, nonce):
        raise UnsubscribeError("This unsubscribe link has expired. Turn emails off in Settings → Notifications.")
    return UnsubscribeTarget(user_id=user_id, kind=kind)


def email_muted_kinds(user: Any) -> Set[str]:
    """Programs this person muted for email, from a user row or dict."""
    try:
        raw = user["email_muted_kinds"] if user is not None else None
    except (KeyError, IndexError, TypeError):
        raw = None
    if not raw:
        return set()
    try:
        parsed = json.loads(raw) if isinstance(raw, str) else list(raw)
    except (TypeError, ValueError):
        return set()
    return {str(item) for item in parsed if str(item) in PROGRAM_LABELS}


def apply_unsubscribe(db: Database, target: UnsubscribeTarget) -> str:
    """Turn off one program for one person. Returns the program label."""
    flag = _OPT_IN_FLAGS.get(target.kind)

    def _write() -> None:
        with db.connect() as conn:
            if flag:
                conn.execute(f"UPDATE users SET {flag} = 0 WHERE id = ?", (target.user_id,))
                return
            row = conn.execute(
                "SELECT email_muted_kinds FROM users WHERE id = ?", (target.user_id,)
            ).fetchone()
            muted = email_muted_kinds(row)
            muted.add(target.kind)
            conn.execute(
                "UPDATE users SET email_muted_kinds = ? WHERE id = ?",
                (json.dumps(sorted(muted)), target.user_id),
            )

    db.run_write(_write, label="mail_unsubscribe")
    from projectionist import security_audit as sa

    sa.audit(db, sa.EMAIL_UNSUBSCRIBE, actor_id=target.user_id, target_id=target.user_id, program=target.kind)
    return PROGRAM_LABELS[target.kind]


def unsubscribe_url(base_url: str, db: Database, user_id: str, kind: str) -> Optional[str]:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return None
    token = make_unsubscribe_token(db, user_id, kind)
    if not token:
        return None
    return f"{base}{UNSUBSCRIBE_PATH}?t={token}"
