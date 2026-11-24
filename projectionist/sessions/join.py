"""Join a room (SES-005).

A signed-in member joins with the code on the screen, or asks the person who
started the session. Until then they learn nothing about what is playing.
The code is not part of the session object a guest can read.
"""

from __future__ import annotations

import hmac
import re
import secrets
import time
from typing import Any

from projectionist.sessions.shared import (
    JoinRequest,
    SharedSession,
    SharedSessionError,
    add_guest,
    mark_declined,
    remember_pending,
    take_pending,
)

_CODE = re.compile(r"^[0-9a-f]{8}$")
_FAILS: dict[str, list[float]] = {}
_WINDOW_SECONDS = 60.0
_MAX_FAILS = 8


def reset_join_attempts() -> None:
    _FAILS.clear()


def _clean_name(raw: str) -> str:
    text = " ".join(str(raw or "").split())
    return (text or "Someone")[:40]


def _too_many(user_id: str) -> bool:
    now = time.time()
    recent = [stamp for stamp in _FAILS.get(user_id, []) if now - stamp < _WINDOW_SECONDS]
    _FAILS[user_id] = recent
    return len(recent) >= _MAX_FAILS


def _note_failure(user_id: str) -> None:
    _FAILS.setdefault(user_id, []).append(time.time())


def _code_matches(session: SharedSession, code: str) -> bool:
    offered = str(code or "").strip().lower()
    if not _CODE.fullmatch(offered):
        return False
    expected = str(session.join_code or "")
    if len(expected) != len(offered):
        return False
    return hmac.compare_digest(offered, expected)


def _already_inside(session: SharedSession, user_id: str, *, screen_user_id: str | None) -> bool:
    if session.owner_id == user_id:
        return True
    if user_id in session.guest_ids:
        return True
    return bool(screen_user_id) and screen_user_id == user_id


def request_join(
    session: SharedSession,
    *,
    user_id: str,
    display_name: str,
    code: str,
    screen_user_id: str | None,
) -> dict[str, Any]:
    """Join, or leave a request that does not name the title."""
    if _already_inside(session, user_id, screen_user_id=screen_user_id):
        body = session.public()
        body["status"] = "joined"
        return body
    if _too_many(user_id):
        raise SharedSessionError("That code is not right. Wait a moment and try again.", status_code=429)
    if _code_matches(session, code):
        add_guest(session, user_id)
        body = session.public()
        body["status"] = "joined"
        return body
    offered = str(code or "").strip()
    if offered:
        _note_failure(user_id)
        raise SharedSessionError("That code is not right.", status_code=403)
    if user_id in session.declined_ids:
        return {"status": "declined"}
    request = remember_pending(
        session,
        JoinRequest(
            id=secrets.token_hex(8),
            user_id=user_id,
            display_name=_clean_name(display_name),
            created_at=time.time(),
        ),
    )
    return {"status": "pending", "request_id": request.id}


def list_join_requests(session: SharedSession) -> dict[str, Any]:
    return {
        "requests": [
            {"id": item.id, "display_name": item.display_name}
            for item in session.pending
        ]
    }


def decide_join(
    session: SharedSession,
    *,
    actor_id: str,
    request_id: str,
    decision: str,
) -> dict[str, Any]:
    if session.owner_id != actor_id:
        raise SharedSessionError(
            "Only the person who started this session can answer a request.",
            status_code=403,
        )
    choice = str(decision or "").strip().lower()
    if choice not in {"approve", "not_now"}:
        raise SharedSessionError("Choose approve or not now.")
    pending = take_pending(session, request_id)
    if choice == "not_now":
        mark_declined(session, pending.user_id)
        return {"status": "declined", "request_id": pending.id}
    add_guest(session, pending.user_id)
    return {"status": "approved", "request_id": pending.id}
