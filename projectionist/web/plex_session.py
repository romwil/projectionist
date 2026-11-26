"""Sign a TestClient in as a Plex account without the removed token route.

``POST /api/auth/plex`` is gone. Tests that used it as a fixture call this
helper, which still runs ``authenticate_plex_user`` and sets the session cookie.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Mapping, Optional

from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response


def sign_in_plex_token(
    client: Any,
    auth_token: str,
    *,
    invite_token: Optional[str] = None,
    headers: Optional[Mapping[str, str]] = None,
) -> Any:
    from projectionist.web.auth import authenticate_plex_user, set_session_cookie
    from projectionist.web.jobs import get_job_manager

    request = _request(headers, client)
    db = get_job_manager().db
    try:
        user = authenticate_plex_user(
            auth_token,
            db,
            invite_token=invite_token,
            request=request,
        )
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail)
        return _result(exc.status_code, {"detail": exc.detail}, text=detail)
    response = Response()
    set_session_cookie(response, user.id, request, db=db)
    _copy_cookie(client, response)
    body = {"user": user.to_dict(), "authenticated": True}
    return _result(
        200,
        body,
        headers={"set-cookie": response.headers.get("set-cookie", "")},
        cookies=client.cookies,
    )


def _request(headers: Optional[Mapping[str, str]], client: Any) -> Request:
    merged = {str(key): str(value) for key, value in (headers or {}).items()}
    jar = getattr(getattr(client, "cookies", None), "jar", None)
    if jar is not None and "cookie" not in {key.lower() for key in merged}:
        pairs: dict[str, str] = {}
        for cookie in jar:
            pairs[str(cookie.name)] = str(cookie.value)
        if pairs:
            merged["cookie"] = "; ".join(f"{key}={value}" for key, value in pairs.items())
    raw = []
    for key, value in merged.items():
        raw.append((key.lower().encode("latin-1"), value.encode("latin-1")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": raw,
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
    )


def _copy_cookie(client: Any, response: Response) -> None:
    from http.cookies import SimpleCookie

    raw = response.headers.get("set-cookie")
    if not raw:
        return
    parsed = SimpleCookie()
    parsed.load(raw)
    for key, morsel in parsed.items():
        client.cookies.set(key, morsel.value)


def _result(
    status: int,
    body: dict[str, Any],
    *,
    text: str = "",
    headers: Optional[Mapping[str, str]] = None,
    cookies: Any = None,
) -> Any:
    payload = text or json.dumps(body)
    return SimpleNamespace(
        status_code=status,
        text=payload,
        headers=dict(headers or {}),
        cookies=cookies if cookies is not None else {},
        json=lambda: body,
    )
