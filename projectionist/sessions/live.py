"""Realtime session channel (SES-004).

Commands are authorized, then applied to the session object and returned as
an event that carries server time. A device estimates the playhead from the
last position plus elapsed time while the state is playing.
"""

from __future__ import annotations

import time
from typing import Any

from projectionist.sessions.shared import (
    SharedSession,
    SharedSessionError,
    end_shared_session,
    update_shared_session,
)

_TRANSPORT = frozenset({"play", "pause", "seek", "skip"})
_OWNER_ONLY = frozenset({"rate", "captions", "level", "end"})
_ALL = _TRANSPORT | _OWNER_ONLY


def estimate_playhead(position_ms: int, server_time_ms: int, now_ms: int, state: str) -> int:
    """Where the picture is, from the last heartbeat and the clock."""
    if str(state or "") != "playing":
        return max(0, int(position_ms))
    elapsed = max(0, int(now_ms) - int(server_time_ms))
    return max(0, int(position_ms) + elapsed)


def server_time_ms() -> int:
    return int(time.time() * 1000)


def authorize_command(role: str, command: str) -> bool:
    name = str(command or "").strip().lower()
    if name not in _ALL:
        return False
    if role == "owner":
        return True
    if role == "screen":
        return name in _TRANSPORT
    return False


def _event(session: SharedSession, kind: str, **extra: Any) -> dict[str, Any]:
    body = {
        "type": kind,
        "server_time_ms": server_time_ms(),
        "position_ms": session.position_ms,
        "state": session.state,
        "level": session.level,
    }
    body.update(extra)
    return body


def apply_command(session: SharedSession, role: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Authorize one command and fold it into the session. Raises on refusal."""
    command = str(payload.get("command") or "").strip().lower()
    if not authorize_command(role, command):
        raise SharedSessionError("That command is not allowed.", status_code=403)
    if command == "play":
        update_shared_session(session, state="playing")
        return _event(session, "state")
    if command == "pause":
        update_shared_session(session, state="paused")
        return _event(session, "state")
    if command == "seek":
        ms = payload.get("ms")
        if not isinstance(ms, int) or isinstance(ms, bool) or ms < 0:
            raise SharedSessionError("Seek needs a position in milliseconds.")
        update_shared_session(session, position_ms=ms)
        return _event(session, "position")
    if command == "skip":
        seconds = payload.get("s")
        if not isinstance(seconds, int) or isinstance(seconds, bool) or not -600 <= seconds <= 600:
            raise SharedSessionError("Skip needs a number of seconds.")
        update_shared_session(session, position_ms=max(0, session.position_ms + seconds * 1000))
        return _event(session, "position")
    if command == "rate":
        value = payload.get("value")
        if value not in {1, 2}:
            raise SharedSessionError("Rate must be 1 or 2.")
        return _event(session, "state", rate=value)
    if command == "level":
        update_shared_session(session, level=str(payload.get("level") or ""), allow_level=True)
        return _event(session, "track")
    if command == "captions":
        choice = str(payload.get("id") or "").strip()
        if not choice or len(choice) > 40:
            raise SharedSessionError("Captions need a track id, or off.")
        return _event(session, "track", captions=choice)
    end_shared_session(session)
    return {
        "type": "ended",
        "server_time_ms": server_time_ms(),
        "position_ms": session.position_ms,
        "state": "ended",
        "level": session.level,
    }
