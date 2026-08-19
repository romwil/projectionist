"""Invite-only household join helpers."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from projectionist.config_store import Settings, invite_required_for_new_users
from projectionist.library.db import Database
from projectionist.mail import MailSendError, mail_configured, send_mail
from projectionist.web.auth import _hash_password, row_to_current_user_from_dict
from projectionist.web.ingress import JOIN_LINK_DETAIL
from projectionist.web.session_tokens import resolve_session_secret

logger = logging.getLogger(__name__)

DEFAULT_INVITE_TTL_SECONDS = 7 * 24 * 3600


def hash_invite_token(raw_token: str) -> str:
    return hashlib.sha256(str(raw_token or "").encode("utf-8")).hexdigest()


def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)


def _invite_hmac(invite_id: str, raw: str) -> str:
    secret = resolve_session_secret().encode("utf-8")
    return hmac.new(secret, f"{invite_id}.{raw}".encode("utf-8"), hashlib.sha256).hexdigest()


def encode_invite_token(invite_id: str, raw: str) -> str:
    return f"{invite_id}.{raw}.{_invite_hmac(invite_id, raw)}"


def parse_invite_token(token: str) -> Tuple[str, str]:
    """Verify HMAC and return (invite_id, raw). Fail closed without a DB lookup."""
    cleaned = str(token or "").strip()
    parts = cleaned.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError("Invite not found")
    invite_id, raw, mac = parts
    expected = _invite_hmac(invite_id, raw)
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Invite not found")
    return invite_id, raw


def public_invite_view(invite: Dict[str, Any]) -> Dict[str, Any]:
    """Safe fields for unauthenticated validate/redeem UI."""
    return {
        "id": invite["id"],
        "status": invite["status"],
        "expires_at": invite["expires_at"],
        "role": invite["role"],
        "is_youth": bool(invite.get("is_youth")),
        "allowed_methods": list(invite.get("allowed_methods") or []),
        "email": invite.get("email"),
    }


def create_household_invite(
    db: Database,
    settings: Settings,
    *,
    owner_id: str,
    role: str = "member",
    is_youth: bool = False,
    allowed_methods: Optional[List[str]] = None,
    email: Optional[str] = None,
    expected_plex_user_id: Optional[str] = None,
    expected_oidc_sub: Optional[str] = None,
    access_request_id: Optional[str] = None,
    expires_in_seconds: int = DEFAULT_INVITE_TTL_SECONDS,
    base_url: Optional[str] = None,
    send_email: bool = True,
) -> Dict[str, Any]:
    """Create a pending invite; returns invite + one-time raw token + join URL."""
    import time
    import uuid

    cleaned_role = str(role or "member").strip().lower()
    if cleaned_role != "member":
        raise ValueError("role must be member")
    invite_id = uuid.uuid4().hex
    raw = generate_invite_token()
    token_hash = hash_invite_token(raw)
    expires_at = time.time() + max(3600, int(expires_in_seconds))
    invite = db.create_invite(
        token_hash=token_hash,
        created_by=owner_id,
        role="member",
        is_youth=is_youth,
        allowed_methods=allowed_methods,
        expires_at=expires_at,
        email=email,
        expected_plex_user_id=expected_plex_user_id,
        expected_oidc_sub=expected_oidc_sub,
        access_request_id=access_request_id,
        invite_id=invite_id,
    )
    signed = encode_invite_token(str(invite["id"]), raw)
    domain = str(getattr(settings, "household_domain", "") or "").strip()
    origin = str(base_url or "").rstrip("/")
    if domain and not origin:
        origin = domain if domain.startswith("http") else f"https://{domain}"
    join_path = f"/join?token={signed}"
    join_url = urljoin(origin + "/", join_path.lstrip("/")) if origin else join_path
    mailed = False
    if send_email and email and mail_configured(settings):
        try:
            send_mail(
                settings,
                to=str(email),
                subject="You're invited to join Projectionist",
                text=(
                    "You've been invited to join a Projectionist household.\n\n"
                    f"Open this link to finish joining:\n{join_url}\n\n"
                    "If you did not expect this, you can ignore the message."
                ),
                html=(
                    "<p>You've been invited to join a Projectionist household.</p>"
                    f'<p><a href="{join_url}">Open your invite</a></p>'
                    "<p>If you did not expect this, you can ignore the message.</p>"
                ),
            )
            mailed = True
        except MailSendError:
            logger.exception("Could not email invite to %s", email)
        except Exception:  # noqa: BLE001
            logger.exception("Could not email invite to %s", email)

    return {
        "invite": public_invite_view(invite),
        "token": signed,
        "join_path": join_path,
        "join_url": join_url,
        "emailed": mailed,
    }


def lookup_pending_invite(db: Database, raw_token: str) -> Dict[str, Any]:
    """Validate a raw token and return the pending invite or raise ValueError."""
    import time

    invite_id, raw = parse_invite_token(raw_token)
    invite = db.get_invite_by_token_hash(hash_invite_token(raw))
    if invite is None or str(invite["id"]) != invite_id:
        raise ValueError("Invite not found")
    if invite["status"] == "revoked":
        raise ValueError("Invite has been revoked")
    if invite["status"] == "redeemed":
        raise ValueError("Invite has already been used")
    if invite["status"] != "pending":
        raise ValueError("Invite is not available")
    if float(invite["expires_at"]) < time.time():
        raise ValueError("Invite has expired")
    return invite


def assert_identity_not_denied(
    db: Database,
    *,
    email: Optional[str] = None,
    plex_user_id: Optional[str] = None,
    oidc_sub: Optional[str] = None,
) -> None:
    if db.has_denied_identity(email=email, plex_user_id=plex_user_id, oidc_sub=oidc_sub):
        raise ValueError("This identity cannot join — access was previously denied")


def assert_method_allowed(invite: Dict[str, Any], method: str) -> None:
    allowed = {str(m).lower() for m in (invite.get("allowed_methods") or [])}
    if str(method).lower() not in allowed:
        raise ValueError(f"This invite does not allow {method} sign-in")


def redeem_local_invite(
    db: Database,
    settings: Settings,
    *,
    raw_token: str,
    username: str,
    password: str,
) -> Dict[str, Any]:
    """Create a local-password member from a pending invite in one transaction."""
    del settings
    invite = lookup_pending_invite(db, raw_token)
    assert_method_allowed(invite, "local")
    assert_identity_not_denied(db, email=invite.get("email"))

    name = str(username or "").strip()
    if len(name) < 2:
        raise ValueError("Username must be at least 2 characters")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    if db.get_user_by_display_name(name) is not None:
        raise ValueError("Username already taken")

    user_id = f"local-{secrets.token_hex(12)}"
    result = db.create_local_user_and_redeem_invite(
        invite_id=str(invite["id"]),
        user_id=user_id,
        display_name=name,
        password_hash=_hash_password(password),
        role="member",
        email=invite.get("email"),
        is_youth=bool(invite.get("is_youth")),
    )
    return {
        "invite": public_invite_view(result["invite"]),
        "user": row_to_current_user_from_dict(result["user"]).to_dict(),
    }


def provision_from_invite(
    db: Database,
    settings: Settings,
    *,
    invite: Dict[str, Any],
    method: str,
    user_id: str,
    display_name: str,
    email: Optional[str],
    plex_user_id: Optional[str] = None,
    oidc_sub: Optional[str] = None,
    avatar_url: Optional[str] = None,
    seerr_user_id: Optional[int] = None,
    seerr_permissions: Optional[int] = None,
) -> Dict[str, Any]:
    """Bind a new Plex/OIDC identity using invite role/youth, then mark redeemed."""
    del settings
    assert_method_allowed(invite, method)
    assert_identity_not_denied(
        db,
        email=email or invite.get("email"),
        plex_user_id=plex_user_id or invite.get("expected_plex_user_id"),
        oidc_sub=oidc_sub or invite.get("expected_oidc_sub"),
    )
    expected_plex = invite.get("expected_plex_user_id")
    if expected_plex and plex_user_id and str(expected_plex) != str(plex_user_id):
        raise ValueError("This invite is for a different Plex account")
    expected_oidc = invite.get("expected_oidc_sub")
    if expected_oidc and oidc_sub and str(expected_oidc) != str(oidc_sub):
        raise ValueError("This invite is for a different SSO account")

    result = db.upsert_identity_and_redeem_invite(
        invite_id=str(invite["id"]),
        method=method,
        user_id=user_id,
        display_name=display_name,
        email=email,
        role="member",
        plex_user_id=plex_user_id,
        oidc_sub=oidc_sub,
        avatar_url=avatar_url,
        seerr_user_id=seerr_user_id,
        seerr_permissions=seerr_permissions,
        is_youth=bool(invite.get("is_youth")),
    )
    return {"invite": result["invite"], "user": result["user"]}


def require_invite_or_open(
    settings: Settings,
    db: Database,
    *,
    raw_token: Optional[str],
    method: str,
) -> Optional[Dict[str, Any]]:
    """Return a pending invite when invite-only; None when open auto-provision."""
    if not invite_required_for_new_users(settings):
        return None
    if not raw_token:
        raise ValueError(JOIN_LINK_DETAIL)
    invite = lookup_pending_invite(db, raw_token)
    assert_method_allowed(invite, method)
    return invite
