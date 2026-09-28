"""Named-member whisper inbox HTTP routes (v1.36.5).

Registered via ``register_whisper_routes`` so app.py stays the composition root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from projectionist.config_store import load_merged_settings
from projectionist.web.auth import get_current_user_dep

router = APIRouter(tags=["whisper"])


class WhisperSeenPayload(BaseModel):
    ids: List[str] = Field(default_factory=list)
    all_unread: bool = False


def _settings():
    from projectionist.web.jobs import get_job_manager

    return load_merged_settings(Path(get_job_manager().data_dir))


def _db():
    from projectionist.web.jobs import get_job_manager

    return get_job_manager().db


def _user_mapping(user: Any) -> Dict[str, Any]:
    getter = getattr(user, "to_dict", None)
    if callable(getter):
        data = getter()
        if isinstance(data, dict):
            return data
    return {
        "id": getattr(user, "id", ""),
        "display_name": getattr(user, "display_name", ""),
        "preferred_name": getattr(user, "preferred_name", None),
        "role": getattr(user, "role", "member"),
        "disabled": False,
        "is_youth": bool(getattr(user, "is_youth", False)),
    }


@router.get("/api/whispers")
def list_whispers(
    unread_only: bool = False,
    limit: int = 20,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """This member's whisper inbox. Not owner-only Good News."""
    from projectionist.notifications.whisper import inbox_payload_for_user

    return inbox_payload_for_user(
        _db(),
        _settings(),
        _user_mapping(user),
        unread_only=unread_only,
        limit=min(max(1, int(limit)), 50),
    )


@router.post("/api/whispers/seen")
def mark_whispers_seen_route(
    payload: WhisperSeenPayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    from projectionist.notifications.whisper import mark_whispers_seen

    updated = mark_whispers_seen(
        _db(),
        user.id,
        notification_ids=payload.ids or None,
        all_unread=payload.all_unread,
    )
    return {"updated": updated}


def register_whisper_routes(app) -> None:
    """Attach whisper inbox routes to the FastAPI app."""
    app.include_router(router)
