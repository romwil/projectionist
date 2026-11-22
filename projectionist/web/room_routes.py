"""Room list and rename (SES-002)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from projectionist.sessions.rooms import RoomError, list_rooms, rename_room
from projectionist.web.auth import get_current_user_dep

router = APIRouter(tags=["rooms"])


class RoomNamePayload(BaseModel):
    name: str = Field(default="", max_length=80)


def _db():
    from projectionist.web.jobs import get_job_manager

    return get_job_manager().db


def _raise(error: RoomError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from error


@router.get("/api/rooms")
def rooms_list(user=Depends(get_current_user_dep)) -> dict:
    """Named screens in this household. What is playing is not on this list."""
    del user
    return {"rooms": list_rooms(_db())}


@router.patch("/api/rooms/{room_id}")
def rooms_rename(
    room_id: str,
    payload: RoomNamePayload,
    user=Depends(get_current_user_dep),
) -> dict:
    owner = str(getattr(user, "role", "") or "") == "owner"
    try:
        return rename_room(
            _db(),
            room_id,
            payload.name,
            user_id=str(getattr(user, "id", "") or ""),
            is_owner=owner,
        )
    except RoomError as error:
        _raise(error)


def register_room_routes(app) -> None:
    app.include_router(router)
