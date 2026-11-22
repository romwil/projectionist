"""Shared session object routes (SES-003)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from projectionist.sessions.rooms import screen_signed_in_user
from projectionist.sessions.shared import (
    SharedSessionError,
    can_read,
    end_shared_session,
    get_shared_session,
    open_shared_session,
    update_shared_session,
)
from projectionist.web.auth import get_current_user_dep

router = APIRouter(tags=["sessions"])

_UNAVAILABLE = "That session is not available."


class OpenSessionPayload(BaseModel):
    screen_id: str = ""
    rating_key: str = ""
    level: str = "off"
    position_ms: int = Field(default=0, ge=0)
    engine_session_id: str = ""


class UpdateSessionPayload(BaseModel):
    position_ms: Optional[int] = Field(default=None, ge=0)
    state: Optional[str] = None
    level: Optional[str] = None


def _db():
    from projectionist.web.jobs import get_job_manager

    return get_job_manager().db


def _raise(error: SharedSessionError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from error


def _visible(session_id: str, user):
    session = get_shared_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=_UNAVAILABLE)
    screen_user = screen_signed_in_user(_db(), session.screen_id)
    user_id = str(getattr(user, "id", "") or "")
    if not can_read(session, user_id=user_id, screen_user_id=screen_user):
        raise HTTPException(status_code=404, detail=_UNAVAILABLE)
    return session, user_id, screen_user


@router.post("/api/sessions")
def open_session(payload: OpenSessionPayload, user=Depends(get_current_user_dep)) -> dict:
    """Start a session on a screen. The caller owns it. One session per screen."""
    screen_user = screen_signed_in_user(_db(), payload.screen_id)
    if screen_user is None:
        raise HTTPException(status_code=404, detail="That room is not in this household.")
    try:
        session = open_shared_session(
            owner_id=str(getattr(user, "id", "") or ""),
            screen_id=payload.screen_id,
            rating_key=payload.rating_key,
            level=payload.level,
            position_ms=payload.position_ms,
            engine_session_id=payload.engine_session_id,
            youth=bool(getattr(user, "is_youth", False)),
        )
    except SharedSessionError as error:
        _raise(error)
    return session.public()


@router.get("/api/sessions/{session_id}")
def read_session(session_id: str, user=Depends(get_current_user_dep)) -> dict:
    session, _user_id, _screen_user = _visible(session_id, user)
    return session.public()


@router.patch("/api/sessions/{session_id}")
def patch_session(
    session_id: str,
    payload: UpdateSessionPayload,
    user=Depends(get_current_user_dep),
) -> dict:
    session, user_id, _screen_user = _visible(session_id, user)
    try:
        updated = update_shared_session(
            session,
            position_ms=payload.position_ms,
            state=payload.state,
            level=payload.level,
            allow_level=session.owner_id == user_id,
        )
    except SharedSessionError as error:
        _raise(error)
    return updated.public()


@router.delete("/api/sessions/{session_id}")
def close_session(session_id: str, user=Depends(get_current_user_dep)) -> dict:
    session, user_id, _screen_user = _visible(session_id, user)
    if session.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Only the person who started this session can end it.")
    end_shared_session(session)
    return {"id": session.id, "state": "ended"}


def register_shared_session_routes(app) -> None:
    app.include_router(router)
