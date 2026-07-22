"""Send email via SMTP or Resend using owner mail settings."""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Optional

import httpx

from curatorx.config_store import MailSettings, Settings

logger = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"


class MailSendError(RuntimeError):
    """Raised when a mail send fails after configuration was present."""


@dataclass(frozen=True)
class MailSendResult:
    ok: bool
    provider: str
    message_id: str = ""
    detail: str = ""


def mail_configured(settings: Settings | MailSettings) -> bool:
    """Return True when outbound mail can be attempted."""
    mail = settings if isinstance(settings, MailSettings) else getattr(settings, "mail", MailSettings())
    if not mail.enabled:
        return False
    provider = str(mail.provider or "off").strip().lower()
    if provider == "smtp":
        return bool(str(mail.smtp_host or "").strip() and str(mail.from_email or "").strip())
    if provider == "resend":
        return bool(str(mail.resend_api_key or "").strip() and str(mail.from_email or "").strip())
    return False


def _from_header(mail: MailSettings) -> str:
    email = str(mail.from_email or "").strip()
    name = str(mail.from_name or "").strip()
    if name and email:
        return f"{name} <{email}>"
    return email


def _apply_subject_prefix(mail: MailSettings, subject: str) -> str:
    cleaned = str(subject or "").strip() or "CuratorX"
    prefix = str(mail.subject_prefix or "").strip()
    if not prefix:
        return cleaned
    if cleaned.lower().startswith(prefix.lower()):
        return cleaned
    return f"{prefix} {cleaned}".strip()


def _html_body(mail: MailSettings, *, body_text: str, body_html: Optional[str] = None) -> str:
    text = str(body_text or "").strip()
    if body_html:
        inner = str(body_html)
    else:
        escaped = (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\n", "<br>\n")
        )
        inner = f"<p style=\"margin:0 0 1rem;line-height:1.5\">{escaped}</p>"
    logo = str(mail.logo_url or "").strip()
    footer = str(mail.footer_text or "").strip()
    parts = ['<div style="font-family:Georgia,serif;color:#1a1a1a;max-width:560px">']
    if logo:
        parts.append(
            f'<p style="margin:0 0 1.25rem"><img src="{logo}" alt="" '
            'style="max-height:48px;max-width:200px"/></p>'
        )
    parts.append(inner)
    if footer:
        footer_esc = (
            footer.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>\n")
        )
        parts.append(
            f'<p style="margin:1.5rem 0 0;padding-top:1rem;border-top:1px solid #ddd;'
            f'font-size:0.85rem;color:#555">{footer_esc}</p>'
        )
    parts.append("</div>")
    return "".join(parts)


def _send_smtp(mail: MailSettings, *, to_email: str, subject: str, text: str, html: str) -> MailSendResult:
    host = str(mail.smtp_host or "").strip()
    port = int(mail.smtp_port or 587)
    username = str(mail.smtp_username or "").strip()
    password = str(mail.smtp_password or "")
    use_tls = bool(mail.smtp_use_tls)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = _from_header(mail)
    msg["To"] = to_email
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")

    try:
        if use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                if username:
                    smtp.login(username, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                if username:
                    smtp.login(username, password)
                smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        raise MailSendError(f"SMTP send failed: {exc}") from exc
    return MailSendResult(ok=True, provider="smtp", detail="sent")


def _send_resend(mail: MailSettings, *, to_email: str, subject: str, text: str, html: str) -> MailSendResult:
    api_key = str(mail.resend_api_key or "").strip()
    payload: dict[str, Any] = {
        "from": _from_header(mail),
        "to": [to_email],
        "subject": subject,
        "text": text,
        "html": html,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                RESEND_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except Exception as exc:  # noqa: BLE001
        raise MailSendError(f"Resend request failed: {exc}") from exc
    if response.status_code >= 400:
        detail = response.text[:400]
        raise MailSendError(f"Resend API error {response.status_code}: {detail}")
    message_id = ""
    try:
        data = response.json()
        if isinstance(data, dict):
            message_id = str(data.get("id") or "")
    except Exception:  # noqa: BLE001
        message_id = ""
    return MailSendResult(ok=True, provider="resend", message_id=message_id, detail="sent")


def send_mail(
    settings: Settings | MailSettings,
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> MailSendResult:
    """Send one email using the configured provider.

    Raises ``MailSendError`` when configuration is incomplete or the provider fails.
    """
    mail = settings if isinstance(settings, MailSettings) else getattr(settings, "mail", MailSettings())
    recipient = str(to_email or "").strip()
    if not recipient or "@" not in recipient:
        raise MailSendError("A valid recipient email is required")
    if not mail_configured(mail):
        raise MailSendError("Mail is not configured (enable SMTP or Resend in Admin → Mail)")

    provider = str(mail.provider or "off").strip().lower()
    final_subject = _apply_subject_prefix(mail, subject)
    text = str(body_text or "").strip() or final_subject
    html = _html_body(mail, body_text=text, body_html=body_html)

    if provider == "smtp":
        return _send_smtp(mail, to_email=recipient, subject=final_subject, text=text, html=html)
    if provider == "resend":
        return _send_resend(mail, to_email=recipient, subject=final_subject, text=text, html=html)
    raise MailSendError(f"Unsupported mail provider: {provider}")
