"""Finish an owner sign-in that is waiting on its first code.

Existing tests sign in with a password to reach a session. An owner account
now has to confirm a sign-in code before that session exists. When the login
response is that setup step, submit the current code and return the session.
A later login on the same client reuses the secret from that setup.
"""

from __future__ import annotations

from typing import Any

_SECRETS: dict[tuple[int, str], str] = {}


def finish_sign_in_code(
    client: Any,
    response: Any,
    username: str,
    password: str,
    *,
    payload: dict | None = None,
    **request_kwargs: Any,
):
    key = (id(client), str(username).casefold())
    try:
        body = response.json()
    except Exception:
        return response
    if response.status_code != 401 or not isinstance(body, dict):
        return response
    secret = body.get("secret")
    if isinstance(secret, str) and secret:
        _SECRETS[key] = secret
    elif key not in _SECRETS:
        return response
    from projectionist.web.totp import current_code

    sent = dict(payload or {"username": username, "password": password})
    sent["code"] = current_code(_SECRETS[key])
    return client.post("/api/auth/local/login", json=sent, **request_kwargs)
