"""Shared session object routes (SES-003)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from projectionist.sessions.join import decide_join, list_join_requests, request_join
from projectionist.sessions.live import apply_command, server_time_ms
from projectionist.sessions.rooms import screen_signed_in_user
from projectionist.sessions.shared import (
    get_shared_session_for_screen,
    SharedSessionError,
    can_read,
    end_shared_session,
    get_shared_session,
    open_shared_session,
    remove_guest,
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
    guests_may_remote: Optional[bool] = None


class JoinPayload(BaseModel):
    code: str = ""


class DecideJoinPayload(BaseModel):
    decision: str = ""


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
        if (payload.position_ms is not None or payload.state is not None) and user_id not in {
            session.owner_id,
            screen_signed_in_user(_db(), session.screen_id),
        }:
            raise HTTPException(
                status_code=403,
                detail="Only the screen can report where the picture is.",
            )
        updated = update_shared_session(
            session,
            position_ms=payload.position_ms,
            state=payload.state,
            level=payload.level,
            guests_may_remote=payload.guests_may_remote,
            allow_level=session.owner_id == user_id,
            allow_remote=session.owner_id == user_id,
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


def _role(session, user_id: str) -> str | None:
    screen_user = screen_signed_in_user(_db(), session.screen_id)
    if session.owner_id == user_id:
        return "owner"
    if screen_user and screen_user == user_id:
        return "screen"
    if user_id in session.guest_ids:
        return "guest"
    return None


def _display_name(user) -> str:
    return str(getattr(user, "display_name", "") or "")


@router.post("/api/rooms/{room_id}/join")
def join_room(room_id: str, payload: JoinPayload, user=Depends(get_current_user_dep)) -> dict:
    """Join with the screen's code, or ask the person who started the session."""
    screen_user = screen_signed_in_user(_db(), room_id)
    if screen_user is None:
        raise HTTPException(status_code=404, detail="That room is not in this household.")
    session = get_shared_session_for_screen(room_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Nothing is open in that room.")
    user_id = str(getattr(user, "id", "") or "")
    try:
        return request_join(
            session,
            user_id=user_id,
            display_name=_display_name(user),
            code=payload.code,
            screen_user_id=screen_user,
        )
    except SharedSessionError as error:
        _raise(error)


@router.get("/api/sessions/{session_id}/code")
def read_join_code(session_id: str, user=Depends(get_current_user_dep)) -> dict:
    """The code on the screen. Guests do not receive a copy of it."""
    session, user_id, screen_user = _visible(session_id, user)
    if session.owner_id != user_id and screen_user != user_id:
        raise HTTPException(status_code=404, detail=_UNAVAILABLE)
    return {"code": session.join_code}


@router.get("/api/sessions/{session_id}/join-requests")
def read_join_requests(session_id: str, user=Depends(get_current_user_dep)) -> dict:
    session, user_id, _screen_user = _visible(session_id, user)
    if session.owner_id != user_id:
        raise HTTPException(status_code=404, detail=_UNAVAILABLE)
    return list_join_requests(session)


@router.post("/api/sessions/{session_id}/join-requests/{request_id}")
def answer_join_request(
    session_id: str,
    request_id: str,
    payload: DecideJoinPayload,
    user=Depends(get_current_user_dep),
) -> dict:
    session, user_id, _screen_user = _visible(session_id, user)
    try:
        return decide_join(
            session,
            actor_id=user_id,
            request_id=request_id,
            decision=payload.decision,
        )
    except SharedSessionError as error:
        _raise(error)


@router.delete("/api/sessions/{session_id}/guests/me")
def leave_session(session_id: str, user=Depends(get_current_user_dep)) -> dict:
    session, user_id, _screen_user = _visible(session_id, user)
    try:
        remove_guest(session, user_id)
    except SharedSessionError as error:
        _raise(error)
    return {"status": "left"}


def _user_from_websocket(websocket: WebSocket):
    from projectionist.web.auth import row_to_current_user
    from projectionist.web.session_tokens import SESSION_COOKIE_NAME, parse_session_claims

    token = websocket.cookies.get(SESSION_COOKIE_NAME) or ""
    if not token:
        header = websocket.headers.get("authorization") or ""
        if header.lower().startswith("bearer "):
            token = header.split(" ", 1)[1].strip()
    claims = parse_session_claims(token) if token else None
    if not claims:
        return None
    row = _db().get_user(str(claims.get("uid") or ""))
    if row is None:
        return None
    return row_to_current_user(row)


@router.websocket("/api/sessions/{session_id}/live")
async def session_live(websocket: WebSocket, session_id: str) -> None:
    """Events down, commands up. The server authorizes every command."""
    await websocket.accept()
    user = _user_from_websocket(websocket)
    session = get_shared_session(session_id)
    user_id = str(getattr(user, "id", "") or "")
    role = _role(session, user_id) if session is not None and user is not None else None
    if session is None or role is None:
        await websocket.send_json({"type": "error", "detail": _UNAVAILABLE})
        await websocket.close(code=1008)
        return
    await websocket.send_json(
        {
            "type": "state",
            "server_time_ms": server_time_ms(),
            "position_ms": session.position_ms,
            "state": session.state,
            "level": session.level,
        }
    )
    while True:
        try:
            payload = await websocket.receive_json()
        except WebSocketDisconnect:
            return
        if not isinstance(payload, dict):
            await websocket.send_json({"type": "error", "detail": "That command is not allowed."})
            continue
        try:
            event = apply_command(session, role, payload)
        except SharedSessionError as error:
            await websocket.send_json({"type": "error", "detail": error.detail})
            continue
        await websocket.send_json(event)
        if event.get("type") == "ended":
            await websocket.close()
            return


@router.post("/api/sessions/{session_id}/commands")
def post_command(session_id: str, payload: dict, user=Depends(get_current_user_dep)) -> dict:
    """The same commands as the live channel, for a client that posts them."""
    session, user_id, _screen_user = _visible(session_id, user)
    role = _role(session, user_id) or ""
    try:
        return apply_command(session, role, payload)
    except SharedSessionError as error:
        _raise(error)


def register_shared_session_routes(app) -> None:
    app.include_router(router)
