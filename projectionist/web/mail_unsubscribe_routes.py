"""Public one-click unsubscribe (GRO-008, RFC 8058).

``GET`` shows a page with one button and changes nothing, so mail scanners that
prefetch links cannot unsubscribe anyone. ``POST`` (the button, or a mail
client's one-click request) turns off one program for one person.
"""

from __future__ import annotations

import html
from typing import Any, Callable, Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from projectionist.mail.unsubscribe import (
    PROGRAM_LABELS,
    UNSUBSCRIBE_PATH,
    UnsubscribeError,
    apply_unsubscribe,
    resolve_unsubscribe_token,
)
from projectionist.web.rate_limit import enforce_rate_limit

router = APIRouter(tags=["mail"])

_db_factory: Optional[Callable[[], Any]] = None


def _db():
    if _db_factory is None:
        raise RuntimeError("mail unsubscribe routes not registered")
    return _db_factory()


def _page(title: str, body: str, *, status_code: int = 200) -> HTMLResponse:
    markup = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<meta name=\"robots\" content=\"noindex\">"
        f"<title>{html.escape(title)} · Projectionist</title>"
        "<style>body{font:16px/1.5 system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem}"
        "button{font:inherit;padding:.6rem 1.1rem;border-radius:.4rem;border:1px solid #333;cursor:pointer}"
        "button:focus-visible{outline:2px solid #1a4fd6;outline-offset:2px}</style>"
        f"</head><body><main><h1>{html.escape(title)}</h1>{body}</main></body></html>"
    )
    return HTMLResponse(markup, status_code=status_code, headers={"Cache-Control": "no-store"})


def _token_from(request: Request) -> str:
    return str(request.query_params.get("t") or "")


@router.get(UNSUBSCRIBE_PATH, response_class=HTMLResponse)
def unsubscribe_page(request: Request) -> HTMLResponse:
    enforce_rate_limit(request, bucket="mail_unsubscribe", limit=30, window_seconds=60)
    token = _token_from(request)
    try:
        target = resolve_unsubscribe_token(_db(), token)
    except UnsubscribeError as error:
        return _page("Link not valid", f"<p>{html.escape(str(error))}</p>", status_code=400)
    label = PROGRAM_LABELS[target.kind]
    form = (
        f"<p>Stop getting {html.escape(label)} by email? Nothing else changes.</p>"
        f'<form method="post" action="{UNSUBSCRIBE_PATH}?t={html.escape(token, quote=True)}">'
        '<input type="hidden" name="List-Unsubscribe" value="One-Click">'
        f"<button type=\"submit\">Unsubscribe from {html.escape(label)}</button></form>"
    )
    return _page("Unsubscribe", form)


@router.post(UNSUBSCRIBE_PATH, response_class=HTMLResponse)
def unsubscribe_one_click(request: Request) -> HTMLResponse:
    enforce_rate_limit(request, bucket="mail_unsubscribe", limit=30, window_seconds=60)
    try:
        target = resolve_unsubscribe_token(_db(), _token_from(request))
    except UnsubscribeError as error:
        return _page("Link not valid", f"<p>{html.escape(str(error))}</p>", status_code=400)
    label = apply_unsubscribe(_db(), target)
    return _page(
        "Unsubscribed",
        f"<p>You won't get {html.escape(label)} by email any more. "
        "You can turn it back on in Settings → Notifications.</p>",
    )


def register_mail_unsubscribe_routes(app, *, db_factory: Callable[[], Any]) -> None:
    global _db_factory
    _db_factory = db_factory
    app.include_router(router)
