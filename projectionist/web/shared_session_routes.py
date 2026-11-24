"""Shared session object routes (SES-003)."""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from projectionist.sessions.approvals import (
    ensure_youth_approval,
    finish_approval,
    list_approvals,
    open_approval,
)
from projectionist.sessions.join import decide_join, list_join_requests, request_join
from projectionist.sessions.live import apply_command, server_time_ms
from projectionist.sessions.rooms import screen_signed_in_user
from projectionist.sessions.captions import parse_cues
from projectionist.sessions.shared import (
    SharedSessionError,
    can_read,
    change_title,
    end_shared_session,
    get_shared_session,
    get_shared_session_for_screen,
    mark_declined,
    open_shared_session,
    remove_guest,
    tighten_ceiling,
    update_shared_session,
    add_guest,
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
    rating_key: Optional[str] = None


class JoinPayload(BaseModel):
    code: str = ""


class DecideJoinPayload(BaseModel):
    decision: str = ""


def _db():
    from projectionist.web.jobs import get_job_manager

    return get_job_manager().db


def _settings():
    from projectionist.web.app import _settings as load

    return load()


def _title_facts(rating_key: str) -> tuple[str, str]:
    row = _db().library_item_by_rating_key(rating_key)
    if row is None:
        return "", ""
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    title = str(row["title"] or "") if "title" in keys else ""
    rating = str(row["content_rating"] or "") if "content_rating" in keys else ""
    return title, rating


def _youth_ceiling() -> str:
    from projectionist.youth.rating_gate import resolve_youth_max_rating

    return resolve_youth_max_rating(_settings())


def _ceiling_covers(session, youth_ceiling: str) -> bool:
    from projectionist.youth.rating_gate import rating_rank

    if not session.ceiling:
        return False
    room = rating_rank(session.ceiling)
    theirs = rating_rank(youth_ceiling)
    if room is None or theirs is None:
        return False
    return room <= theirs


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
    _title, rating = _title_facts(payload.rating_key)
    youth = bool(getattr(user, "is_youth", False))
    try:
        session = open_shared_session(
            owner_id=str(getattr(user, "id", "") or ""),
            screen_id=payload.screen_id,
            rating_key=payload.rating_key,
            level=payload.level,
            position_ms=payload.position_ms,
            engine_session_id=payload.engine_session_id,
            youth=youth,
            content_rating=rating,
            ceiling=_youth_ceiling() if youth else "",
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
        if payload.rating_key is not None:
            if session.owner_id != user_id:
                raise HTTPException(
                    status_code=403,
                    detail="Only the person who started this session can change the title.",
                )
            _title, rating = _title_facts(payload.rating_key)
            update_shared_session(
                session,
                position_ms=payload.position_ms,
                state=payload.state,
                level=payload.level,
                guests_may_remote=payload.guests_may_remote,
                allow_level=True,
                allow_remote=True,
            )
            return change_title(session, payload.rating_key, rating).public()
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
    if bool(getattr(user, "is_youth", False)) and not _ceiling_covers(session, _youth_ceiling()):
        if user_id in session.declined_ids:
            return {"status": "declined"}
        from projectionist.youth.rating_gate import content_rating_allowed

        ceiling = _youth_ceiling()
        title, _stored = _title_facts(session.rating_key)
        try:
            approval_id = ensure_youth_approval(
                _db(),
                session_id=session.id,
                requester_id=user_id,
                requester_name=_display_name(user),
                owner_id=session.owner_id,
                ceiling=ceiling,
                title=title,
                content_rating=session.content_rating,
                title_above=not content_rating_allowed(session.content_rating, max_rating=ceiling),
            )
        except SharedSessionError as error:
            _raise(error)
        return {"status": "pending", "request_id": approval_id}
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


@router.get("/api/session-approvals")
def read_session_approvals(user=Depends(get_current_user_dep)) -> dict:
    """Approvals waiting on this member. A requester does not see the title."""
    return list_approvals(_db(), viewer_id=str(getattr(user, "id", "") or ""))


@router.post("/api/session-approvals/{approval_id}")
def answer_session_approval(
    approval_id: str,
    payload: DecideJoinPayload,
    user=Depends(get_current_user_dep),
) -> dict:
    """Approve tightens the room. Not now declines. Neither response names the title."""
    decision = str(payload.decision or "").strip().lower()
    if decision not in {"approve", "not_now"}:
        raise HTTPException(status_code=400, detail="Choose approve or not now.")
    actor_id = str(getattr(user, "id", "") or "")
    row = open_approval(_db(), approval_id, actor_id=actor_id)
    if row is None:
        raise HTTPException(status_code=404, detail="That request is not available.")
    session = get_shared_session(str(row["session_id"]))
    requester = _db().get_user(str(row["requester_id"]))
    still_youth = False
    if requester is not None:
        keys = set(requester.keys()) if hasattr(requester, "keys") else set()
        still_youth = "is_youth" in keys and bool(int(requester["is_youth"] or 0))
    if session is None or session.owner_id != actor_id or not still_youth:
        finish_approval(_db(), str(row["id"]), actor_id=actor_id, decision="not_now")
        raise HTTPException(status_code=404, detail="That request is not available.")
    if not finish_approval(_db(), str(row["id"]), actor_id=actor_id, decision=decision):
        raise HTTPException(status_code=404, detail="That request is not available.")
    if decision == "not_now":
        mark_declined(session, str(row["requester_id"]))
        return {"status": "declined"}
    from projectionist.youth.rating_gate import content_rating_allowed

    ceiling = str(row["ceiling"] or "")
    above = not content_rating_allowed(session.content_rating, max_rating=ceiling)
    add_guest(session, str(row["requester_id"]), youth=True)
    tighten_ceiling(session, ceiling, title_above=above)
    return {"status": "approved"}


@router.get("/api/sessions/{session_id}/captions")
def session_captions(session_id: str, language: str = "en", user=Depends(get_current_user_dep)) -> dict:
    """Cues for this device. The room's captions stay as they are."""
    session, _user_id, _screen_user = _visible(session_id, user)
    from projectionist.library.subtitle_cache import cache_path, iso2

    lang = iso2(language)
    if not re.fullmatch(r"[a-z]{2,8}", lang or ""):
        raise HTTPException(status_code=400, detail="That language is not available.")
    path = cache_path(session.rating_key, lang)
    cues: list[dict] = []
    if path is not None and path.is_file():
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            raw = ""
        cues = parse_cues(raw[:2_000_000])
    return {"language": lang, "cues": cues}


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
