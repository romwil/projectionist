"""Absolute links back into the app for outbound mail (GRO-008).

Links are plain app URLs that need a normal sign-in. Nothing secret goes in a
URL, so mail logs, proxies, and link scanners learn nothing they could replay.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from typing import Any, Optional

NOTIFICATION_SETTINGS_PATH = "/settings/notifications"
INBOX_PATH = "/inbox"


def app_base_url(settings: Any) -> str:
    """Public origin from ``household_domain`` (``https://`` unless a scheme is given), else ``""``."""
    domain = str(getattr(settings, "household_domain", "") or "").strip().rstrip("/")
    if not domain:
        return ""
    return domain if domain.startswith(("http://", "https://")) else f"https://{domain}"


@dataclass(frozen=True)
class MailFooter:
    text: str
    html: str
    list_unsubscribe: Optional[str]


def lifecycle_footer(
    settings: Any,
    *,
    manage_path: str = NOTIFICATION_SETTINGS_PATH,
    manage_label: str = "Settings → Notifications",
    noun: str = "emails",
) -> MailFooter:
    """Footer for recurring mail: a way back in and a way to stop these emails."""
    base = app_base_url(settings)
    if not base:
        text = (
            "Open Projectionist on your home network to see these in your inbox.\n"
            f"To stop these {noun}, turn them off in {manage_label}."
        )
        return MailFooter(text=text, html=_paragraph(text), list_unsubscribe=None)
    inbox_url = f"{base}{INBOX_PATH}"
    manage_url = f"{base}{manage_path}"
    text = f"See these in your inbox: {inbox_url}\nStop these {noun}: {manage_url}"
    markup = (
        '<p style="margin:1.5rem 0 0;font-size:0.9rem;color:#555">'
        f'<a href="{html.escape(inbox_url, quote=True)}">See these in your inbox</a>'
        " · "
        f'<a href="{html.escape(manage_url, quote=True)}">Stop these {html.escape(noun)}</a>'
        "</p>"
    )
    return MailFooter(text=text, html=markup, list_unsubscribe=manage_url)


def _paragraph(text: str) -> str:
    escaped = html.escape(text).replace("\n", "<br>\n")
    return f'<p style="margin:0 0 1rem;line-height:1.5">{escaped}</p>'


def text_to_html(text: str) -> str:
    """Escape plain text into paragraphs (blank line = new paragraph)."""
    blocks = [block for block in str(text or "").strip().split("\n\n") if block.strip()]
    return "".join(_paragraph(block) for block in blocks)
