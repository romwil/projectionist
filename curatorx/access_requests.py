"""Guest request-access helpers (CuratorX-owned queue, not Seerr)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from curatorx.config_store import Settings
from curatorx.invites import create_household_invite
from curatorx.library.db import Database
from curatorx.notifications.service import deliver_notification

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
    role: str = "member",
    is_youth: bool = False,
    allowed_methods: Optional[List[str]] = None,
    expires_in_seconds: Optional[int] = None,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Approve a pending request by creating a household invite.

    Returns a one-time join token/URL for the owner to copy (and emails it when
    Mail is configured and the request included an address).
    """
    row = db.get_access_request(request_id)
    if row is None:
        raise ValueError("Access request not found")
    if row["status"] != "pending":
        raise ValueError("Access request is already resolved")

    invite_payload = create_household_invite(
        db,
        settings,
        owner_id=owner_id,
        role=role,
        is_youth=is_youth,
        allowed_methods=allowed_methods,
        email=row.get("email"),
        access_request_id=request_id,
        expires_in_seconds=expires_in_seconds or (7 * 24 * 3600),
        base_url=base_url,
        send_email=True,
    )

    resolved = db.resolve_access_request(
        request_id,
        status="approved",
        resolved_by=owner_id,
        created_user_id=None,
    )
    return {
        "request": resolved,
        "invite": invite_payload["invite"],
        "token": invite_payload["token"],
        "join_path": invite_payload["join_path"],
        "join_url": invite_payload["join_url"],
        "emailed": invite_payload["emailed"],
        "sign_in_hint": (
            "Copy the join link and share it with them. "
            "They finish joining at /join — the link works once."
        ),
    }


def deny_access_request(db: Database, *, request_id: str, owner_id: str) -> Dict[str, Any]:
    return db.resolve_access_request(
        request_id,
        status="denied",
        resolved_by=owner_id,
    )
