"""Notification fan-out: inbox rows + optional email."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Sequence

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.library.db._notifications import NOTIFICATION_KINDS
from curatorx.mail import MailSendError, mail_configured, send_mail

logger = logging.getLogger(__name__)


def _user_dict(db: Database, user_id: str) -> Optional[Dict[str, Any]]:
    row = db.get_user(user_id)
    if row is None:
        return None
    return db._row_to_user(row)


def resolve_notification_email(user: Dict[str, Any]) -> Optional[str]:
    """Prefer dedicated notification email, then account email."""
    for key in ("notification_email", "email"):
        value = str(user.get(key) or "").strip()
        if value and "@" in value:
            return value
    return None


def user_wants_channel(user: Dict[str, Any], *, kind: str, channel: str) -> bool:
    cleaned_kind = str(kind or "").strip().lower()
    cleaned_channel = str(channel or "").strip().lower()
    if cleaned_kind not in NOTIFICATION_KINDS:
        return False
    # Enthusiast nudges are opt-in even when inbox/email channels are otherwise on.
    if cleaned_kind == "nudge" and not user.get("nudge_opt_in"):
        return False
    if cleaned_channel == "inbox":
        if user.get("notify_channel_inbox") is False:
            return False
        return True
    if cleaned_channel == "email":
        if not user.get("notify_channel_email"):
            return False
        # Digests / newsletters also require newsletter opt-in.
        if cleaned_kind == "digest" and not user.get("newsletter_opt_in"):
            return False
        return True
    return False


def deliver_notification(
    db: Database,
    settings: Settings,
    *,
    user_id: str,
    kind: str,
    title: str,
    body: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    media_type: Optional[str] = None,
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    rating_key: Optional[str] = None,
    year: Optional[int] = None,
    poster_url: Optional[str] = None,
    from_user_id: Optional[str] = None,
    related_id: Optional[str] = None,
    email_subject: Optional[str] = None,
    force_email: bool = False,
) -> Dict[str, Any]:
    """Create an inbox notification and optionally email the member."""
    user = _user_dict(db, user_id)
    if user is None:
        raise ValueError(f"User not found: {user_id}")

    result: Dict[str, Any] = {"notification": None, "emailed": False, "email_error": None}
    if user_wants_channel(user, kind=kind, channel="inbox"):
        result["notification"] = db.create_notification(
            notification_id=str(uuid.uuid4()),
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            payload=payload,
            media_type=media_type,
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
            rating_key=rating_key,
            year=year,
            poster_url=poster_url,
            from_user_id=from_user_id,
            related_id=related_id,
        )

    should_email = force_email or user_wants_channel(user, kind=kind, channel="email")
    if should_email and mail_configured(settings):
        to_email = resolve_notification_email(user)
        if to_email:
            try:
                send_mail(
                    settings,
                    to_email=to_email,
                    subject=email_subject or title,
                    body_text=body or title,
                )
                result["emailed"] = True
            except MailSendError as exc:
                logger.warning("Notification email failed for %s: %s", user_id, exc)
                result["email_error"] = str(exc)
    return result


def fan_out_notifications(
    db: Database,
    settings: Settings,
    *,
    user_ids: Sequence[str],
    kind: str,
    title: str,
    body: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    email_subject: Optional[str] = None,
    **media_fields: Any,
) -> List[Dict[str, Any]]:
    delivered: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw_id in user_ids:
        uid = str(raw_id or "").strip()
        if not uid or uid in seen:
            continue
        seen.add(uid)
        try:
            delivered.append(
                deliver_notification(
                    db,
                    settings,
                    user_id=uid,
                    kind=kind,
                    title=title,
                    body=body,
                    payload=payload,
                    email_subject=email_subject,
                    **media_fields,
                )
            )
        except Exception:  # noqa: BLE001
            logger.exception("Failed to deliver %s notification to %s", kind, uid)
    return delivered
