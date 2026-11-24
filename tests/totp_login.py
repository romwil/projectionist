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
    from projectionist.web.totp import SIGN_IN_CODE_REQUIRED, current_code

    key = (id(client), str(username).casefold())
    current = response
    # The first answer may be the setup step. A follow-up that still carries a
    # secret is the same step with a replacement key. Try the code each time.
    for _ in range(2):
        try:
            body = current.json()
        except Exception:
            return current
        if current.status_code != 401 or not isinstance(body, dict):
            return current
        secret = body.get("secret")
        if isinstance(secret, str) and secret:
            _SECRETS[key] = secret
        elif body.get("detail") == SIGN_IN_CODE_REQUIRED and key in _SECRETS:
            secret = _SECRETS[key]
        else:
            return current
        sent = dict(payload or {"username": username, "password": password})
        sent["code"] = current_code(str(secret))
        current = client.post("/api/auth/local/login", json=sent, **request_kwargs)
    return current
