"""Invite-only household join helpers."""

from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

from projectionist.config_store import Settings, invite_required_for_new_users
from projectionist.library.db import Database
from projectionist.mail import MailSendError, mail_configured, send_mail
from projectionist.web.auth import _hash_password, row_to_current_user_from_dict

logger = logging.getLogger(__name__)

DEFAULT_INVITE_TTL_SECONDS = 7 * 24 * 3600


def hash_invite_token(raw_token: str) -> str:
    return hashlib.sha256(str(raw_token or "").encode("utf-8")).hexdigest()


def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)


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

    raw = generate_invite_token()
    token_hash = hash_invite_token(raw)
    expires_at = time.time() + max(3600, int(expires_in_seconds))
    invite = db.create_invite(
        token_hash=token_hash,
        created_by=owner_id,
        role=role,
        is_youth=is_youth,
        allowed_methods=allowed_methods,
        expires_at=expires_at,
        email=email,
        expected_plex_user_id=expected_plex_user_id,
        expected_oidc_sub=expected_oidc_sub,
        access_request_id=access_request_id,
    )
    join_path = f"/join?token={raw}"
    join_url = urljoin(str(base_url or "").rstrip("/") + "/", join_path.lstrip("/")) if base_url else join_path
    mailed = False
    if send_email and email and mail_configured(settings):
        try:
            send_mail(
                settings,
                to=str(email),
                subject="You're invited to join CuratorX",
                text=(
                    "You've been invited to join a CuratorX household.\n\n"
                    f"Open this link to finish joining:\n{join_url}\n\n"
                    "If you did not expect this, you can ignore the message."
                ),
                html=(
                    "<p>You've been invited to join a CuratorX household.</p>"
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
        "token": raw,
        "join_path": join_path,
        "join_url": join_url,
        "emailed": mailed,
    }


def lookup_pending_invite(db: Database, raw_token: str) -> Dict[str, Any]:
    """Validate a raw token and return the pending invite or raise ValueError."""
    import time

    cleaned = str(raw_token or "").strip()
    if not cleaned:
        raise ValueError("Invite token is required")
    invite = db.get_invite_by_token_hash(hash_invite_token(cleaned))
    if invite is None:
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
    """Create a local-password member/guest from a pending invite."""
    del settings  # reserved for future mail/welcome hooks
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
    user = db.create_local_user(
        user_id=user_id,
        display_name=name,
        password_hash=_hash_password(password),
        role=str(invite["role"]),
        email=invite.get("email"),
    )
    if invite.get("is_youth"):
        try:
            user = db.set_user_youth(user_id, True)
        except Exception:  # noqa: BLE001
            logger.debug("Could not set youth on invite redeem", exc_info=True)
    redeemed = db.redeem_invite(invite["id"], redeemed_user_id=user_id)
    return {
        "invite": public_invite_view(redeemed),
        "user": row_to_current_user_from_dict(user).to_dict(),
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

    role = str(invite["role"])
    if plex_user_id:
        user = db.upsert_plex_user(
            user_id=user_id,
            display_name=display_name,
            email=email,
            plex_user_id=plex_user_id,
            role=role,
            avatar_url=avatar_url,
            seerr_user_id=seerr_user_id,
            seerr_permissions=seerr_permissions,
        )
    elif oidc_sub:
        user = db.upsert_oidc_user(
            oidc_sub=oidc_sub,
            display_name=display_name,
            email=email,
            role=role,
        )
    else:
        raise ValueError("Plex or OIDC identity is required")

    if invite.get("is_youth"):
        try:
            user = db.set_user_youth(str(user["id"]), True)
        except Exception:  # noqa: BLE001
            logger.debug("Could not set youth on invite redeem", exc_info=True)

    redeemed = db.redeem_invite(invite["id"], redeemed_user_id=str(user["id"]))
    return {"invite": redeemed, "user": user}


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
        raise ValueError(
            "An invite is required to join this household. Ask the owner for a /join link."
        )
    invite = lookup_pending_invite(db, raw_token)
    assert_method_allowed(invite, method)
    return invite
