"""Owner house letter, seasonal preview, gift queue, and trust diary routes."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from projectionist.web.auth import require_role

router = APIRouter(tags=["house"])

_db_factory: Optional[Callable[[], Any]] = None
_settings_factory: Optional[Callable[[], Any]] = None


def _db():
    if _db_factory is None:
        raise RuntimeError("house routes not registered")
    return _db_factory()


def _settings():
    if _settings_factory is None:
        from pathlib import Path

        from projectionist.config_store import load_merged_settings
        from projectionist.web.jobs import get_job_manager

        return load_merged_settings(Path(get_job_manager().data_dir))
    return _settings_factory()


class GiftEnqueuePayload(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    library_item_id: int = Field(ge=1)
    why: Optional[str] = Field(default=None, max_length=400)
    scheduled_for: Optional[float] = None


class SeasonalVetoPayload(BaseModel):
    scope_id: str = Field(min_length=1, max_length=64)
    library_item_id: int = Field(ge=1)


@router.get("/api/admin/house/letter")
def house_letter(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.house.letter import compose_house_letter

    return compose_house_letter(_db())


@router.get("/api/admin/house/seasonal-preview")
def house_seasonal_preview(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.house.seasonal import preview_upcoming_rails

    return preview_upcoming_rails(_db())


@router.post("/api/admin/house/seasonal-preview/veto")
def house_seasonal_veto(
    payload: SeasonalVetoPayload, user=Depends(require_role("owner"))
) -> Dict[str, Any]:
    del user
    from projectionist.house.seasonal import veto_rail_title

    try:
        return veto_rail_title(_db(), payload.scope_id, payload.library_item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/admin/house/seasonal-preview/veto/{scope_id}/{library_item_id}")
def house_seasonal_restore(
    scope_id: str,
    library_item_id: int,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    del user
    from projectionist.house.seasonal import restore_rail_title

    try:
        return restore_rail_title(_db(), scope_id, library_item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/admin/house/gifts")
def house_gifts(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.house.gifts import list_gifts

    return list_gifts(_db())


@router.post("/api/admin/house/gifts")
def house_gifts_enqueue(
    payload: GiftEnqueuePayload, user=Depends(require_role("owner"))
) -> Dict[str, Any]:
    from projectionist.house.gifts import enqueue_gift

    try:
        gift = enqueue_gift(
            _db(),
            user_id=payload.user_id,
            library_item_id=payload.library_item_id,
            why=payload.why,
            scheduled_for=payload.scheduled_for,
            created_by=str(getattr(user, "id", None) or "owner"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": gift}


@router.delete("/api/admin/house/gifts/{gift_id}")
def house_gifts_remove(gift_id: str, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.house.gifts import remove_gift

    deleted = remove_gift(_db(), gift_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Gift not found")
    return {"ok": True, "id": gift_id}


@router.post("/api/admin/house/gifts/{gift_id}/deliver")
def house_gifts_deliver(gift_id: str, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.house.gifts import deliver_gift

    try:
        return deliver_gift(_db(), _settings(), gift_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/admin/house/trust-diary")
def house_trust_diary(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.house.trust_diary import collect_trust_diary

    jobs = []
    try:
        from projectionist.web.jobs import get_job_manager

        jobs = [job.to_dict() for job in get_job_manager().list_jobs()]
    except Exception:  # noqa: BLE001
        jobs = []
    return collect_trust_diary(_db(), jobs=jobs)


def register_house_routes(
    app,
    *,
    db_factory: Callable[[], Any],
    settings_factory: Optional[Callable[[], Any]] = None,
) -> None:
    global _db_factory, _settings_factory
    _db_factory = db_factory
    _settings_factory = settings_factory
    app.include_router(router)
