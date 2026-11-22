"""The shared session object (SES-003).

One screen, one session. The member who starts it owns the intent: level,
and whether it is still going. The screen reports position. Other members
cannot see it. Joining is a later item. State is kept in memory and is gone
after a restart.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any

LEVELS = ("off", "moments", "popups", "class")
STATES = ("playing", "paused", "buffering", "ended")


class SharedSessionError(Exception):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = int(status_code)


@dataclass
class SharedSession:
    id: str
    owner_id: str
    screen_id: str
    rating_key: str
    position_ms: int
    state: str
    level: str
    engine_session_id: str
    youth: bool
    updated_at: float

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "screen_id": self.screen_id,
            "rating_key": self.rating_key,
            "position_ms": self.position_ms,
            "state": self.state,
            "level": self.level,
            "engine_session_id": self.engine_session_id,
            "youth": self.youth,
            "updated_at": self.updated_at,
        }


_LOCK = threading.Lock()
_SESSIONS: dict[str, SharedSession] = {}
_BY_SCREEN: dict[str, str] = {}


def reset_shared_sessions() -> None:
    with _LOCK:
        _SESSIONS.clear()
        _BY_SCREEN.clear()


def _rating_key(raw: str) -> str:
    text = str(raw or "").strip()
    if not text or len(text) > 80 or any(ch in text for ch in "/\\\n\r"):
        raise SharedSessionError("That title is not available.")
    return text


def _level(raw: str) -> str:
    text = str(raw or "off").strip().lower()
    if text not in LEVELS:
        raise SharedSessionError("Level must be off, moments, popups, or class.")
    return text


def _state(raw: str) -> str:
    text = str(raw or "").strip().lower()
    if text not in STATES:
        raise SharedSessionError("State must be playing, paused, buffering, or ended.")
    return text


def can_read(session: SharedSession, *, user_id: str, screen_user_id: str | None) -> bool:
    if session.owner_id == user_id:
        return True
    return bool(screen_user_id) and screen_user_id == user_id


def open_shared_session(
    *,
    owner_id: str,
    screen_id: str,
    rating_key: str,
    level: str = "off",
    position_ms: int = 0,
    engine_session_id: str = "",
    youth: bool = False,
) -> SharedSession:
    screen = str(screen_id or "").strip().lower()
    key = _rating_key(rating_key)
    chosen = _level(level)
    if position_ms < 0:
        raise SharedSessionError("Position cannot be negative.")
    now = time.time()
    session = SharedSession(
        id=str(uuid.uuid4()),
        owner_id=str(owner_id or ""),
        screen_id=screen,
        rating_key=key,
        position_ms=int(position_ms),
        state="playing",
        level=chosen,
        engine_session_id=str(engine_session_id or "")[:80],
        youth=bool(youth),
        updated_at=now,
    )
    with _LOCK:
        previous = _BY_SCREEN.get(screen)
        if previous:
            _SESSIONS.pop(previous, None)
        _SESSIONS[session.id] = session
        _BY_SCREEN[screen] = session.id
    return session


def get_shared_session(session_id: str) -> SharedSession | None:
    with _LOCK:
        return _SESSIONS.get(str(session_id or "").strip())


def update_shared_session(
    session: SharedSession,
    *,
    position_ms: int | None = None,
    state: str | None = None,
    level: str | None = None,
    allow_level: bool = False,
) -> SharedSession:
    if level is not None and not allow_level:
        raise SharedSessionError("Only the person who started this session can change the level.", status_code=403)
    if position_ms is not None and position_ms < 0:
        raise SharedSessionError("Position cannot be negative.")
    with _LOCK:
        current = _SESSIONS.get(session.id)
        if current is None:
            raise SharedSessionError("That session is not available.", status_code=404)
        if position_ms is not None:
            current.position_ms = int(position_ms)
        if state is not None:
            current.state = _state(state)
        if level is not None:
            current.level = _level(level)
        current.updated_at = time.time()
        return current


def end_shared_session(session: SharedSession) -> None:
    with _LOCK:
        current = _SESSIONS.pop(session.id, None)
        if current is not None and _BY_SCREEN.get(current.screen_id) == current.id:
            _BY_SCREEN.pop(current.screen_id, None)
