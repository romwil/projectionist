"""Guest request-access helpers (CuratorX-owned queue, not Seerr)."""

from __future__ import annotations

import logging
import secrets
from typing import Any, Dict, List, Optional

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.notifications.service import deliver_notification
from curatorx.web.auth import _hash_password

logger = logging.getLogger(__name__)


def notify_owners_of_access_request(
    db: Database,
    settings: Settings,
    request_row: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Fan out access-request inbox (+ email) to every owner."""
    owners = [u for u in db.list_users(limit=100) if u.get("role") == "owner" and not u.get("disabled")]
    results = []
    name = str(request_row.get("display_name") or "Someone")
    body_bits = [f"{name} asked to join your CuratorX household."]
    if request_row.get("email"):
        body_bits.append(f"Email: {request_row['email']}")
    if request_row.get("message"):
        body_bits.append(str(request_row["message"]))
    body = "\n".join(body_bits)
    for owner in owners:
        try:
            results.append(
                deliver_notification(
                    db,
                    settings,
                    user_id=str(owner["id"]),
                    kind="access-request",
                    title=f"Access request from {name}",
                    body=body,
                    payload={
                        "access_request_id": request_row["id"],
                        "display_name": name,
                        "email": request_row.get("email"),
                    },
                    related_id=str(request_row["id"]),
                    email_subject=f"Access request from {name}",
                )
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to notify owner %s of access request", owner.get("id"))
    return results


def approve_access_request(
    db: Database,
    settings: Settings,
    *,
    request_id: str,
    owner_id: str,
) -> Dict[str, Any]:
    """Approve a pending request.

    When local login is enabled, create a member account with a one-time password.
    Otherwise mark approved and tell the owner to invite them to sign in with Plex/SSO
    (first successful auth becomes a member).
    """
    row = db.get_access_request(request_id)
    if row is None:
        raise ValueError("Access request not found")
    if row["status"] != "pending":
        raise ValueError("Access request is already resolved")

    display_name = str(row["display_name"])
    email = row.get("email")
    temp_password: Optional[str] = None
    user: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None

    if settings.auth.local_login_enabled:
        user_id = f"invite-{secrets.token_hex(10)}"
        temp_password = secrets.token_urlsafe(10)
        user = db.create_local_user(
            user_id=user_id,
            display_name=display_name,
            password_hash=_hash_password(temp_password),
            role="member",
            email=email,
        )
        if email:
            try:
                db.update_user_profile(user_id, notification_email=email)
            except Exception:  # noqa: BLE001
                logger.debug("Could not set notification email on invite user", exc_info=True)

    resolved = db.resolve_access_request(
        request_id,
        status="approved",
        resolved_by=owner_id,
        created_user_id=user_id,
    )
    return {
        "request": resolved,
        "user": user,
        "temporary_password": temp_password,
        "sign_in_hint": (
            "Share the temporary password so they can sign in with local login."
            if temp_password
            else "Ask them to sign in with Plex or SSO — new household sign-ins become members."
        ),
    }


def deny_access_request(db: Database, *, request_id: str, owner_id: str) -> Dict[str, Any]:
    return db.resolve_access_request(
        request_id,
        status="denied",
        resolved_by=owner_id,
    )
