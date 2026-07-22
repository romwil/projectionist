"""Outbound mail transport (SMTP + Resend) for CuratorX notifications."""

from __future__ import annotations

from curatorx.mail.transport import MailSendError, MailSendResult, send_mail, mail_configured

__all__ = [
    "MailSendError",
    "MailSendResult",
    "mail_configured",
    "send_mail",
]
