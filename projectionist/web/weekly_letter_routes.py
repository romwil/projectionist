"""Owner controls for the weekly household letter (inbox, optional email)."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from projectionist.web.auth import require_role

router = APIRouter(tags=["weekly-letter"])

_db_factory: Optional[Callable[[], Any]] = None
_settings_factory: Optional[Callable[[], Any]] = None


def _db():
    if _db_factory is None:
        raise RuntimeError("weekly letter routes not registered")
    return _db_factory()


def _settings():
    if _settings_factory is None:
        from pathlib import Path

        from projectionist.config_store import load_merged_settings
        from projectionist.web.jobs import get_job_manager

        return load_merged_settings(Path(get_job_manager().data_dir))
    return _settings_factory()


class WeeklyLetterSettingsPayload(BaseModel):
    weekly: Optional[bool] = None
    email: Optional[bool] = None


def _state(db: Any, settings: Any) -> Dict[str, Any]:
    from projectionist.mail import mail_configured
    from projectionist.notifications.weekly_letter import (
        load_letter_settings,
        week_bucket,
    )

    stored = load_letter_settings(db)
    configured = bool(mail_configured(settings))
    return {
        "weekly": bool(stored["weekly"]),
        # Email stays off unless mail is configured AND the owner opted in.
        "email": bool(stored["email"]) and configured,
        "mail_configured": configured,
        "last_week": stored["last_week"],
        "this_week": week_bucket(),
    }


@router.get("/api/admin/weekly-letter")
def get_weekly_letter(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    """Toggles plus this week's letter text (preview before it lands in the inbox)."""
    del user
    from projectionist.notifications.weekly_letter import compose_weekly_letter

    db = _db()
    return {**_state(db, _settings()), "letter": compose_weekly_letter(db)}


@router.put("/api/admin/weekly-letter")
def put_weekly_letter(
    payload: WeeklyLetterSettingsPayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    del user
    from projectionist.notifications.weekly_letter import save_letter_settings

    db = _db()
    settings = _settings()
    state = _state(db, settings)
    email = payload.email
    if email and not state["mail_configured"]:
        # Opting in without mail would silently do nothing; keep it off.
        email = False
    save_letter_settings(db, weekly=payload.weekly, email=email)
    return _state(db, settings)


@router.post("/api/admin/weekly-letter/send")
def send_weekly_letter_now(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    """Drop this week's letter in the owner inbox right now (ignores the weekly toggle)."""
    del user
    from projectionist.notifications.weekly_letter import deliver_weekly_letter

    db = _db()
    settings = _settings()
    result = deliver_weekly_letter(db, settings, force=True)
    return {**result, **_state(db, settings)}


def register_weekly_letter_routes(
    app,
    *,
    db_factory: Callable[[], Any],
    settings_factory: Optional[Callable[[], Any]] = None,
) -> None:
    global _db_factory, _settings_factory
    _db_factory = db_factory
    _settings_factory = settings_factory
    app.include_router(router)
