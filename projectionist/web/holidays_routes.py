"""Admin Holidays calendar + rail curation routes (Phase B1 / B1b / B2)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from projectionist.library.feeds import build_seasonal_rail_snapshot, feed_seasonal_spotlight
from projectionist.library.query import LibraryFilters, query_library
from projectionist.web.auth import require_role

router = APIRouter(tags=["holidays"])

_db_factory: Optional[Callable[[], Any]] = None


def _db():
    if _db_factory is None:
        raise RuntimeError("holidays routes not registered")
    return _db_factory()


class HolidayCreatePayload(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["fixed", "movable"] = "fixed"
    month: Optional[int] = Field(default=None, ge=1, le=12)
    day: Optional[int] = Field(default=None, ge=1, le=31)
    movable_rule: Optional[Literal["arbor_day", "labor_day", "thanksgiving"]] = None
    pre_shoulder_days: int = Field(default=7, ge=0, le=90)
    post_shoulder_days: int = Field(default=7, ge=0, le=90)
    search_terms: List[str] = Field(default_factory=list)
    enabled: bool = True
    schedule_publish: bool = True
    id: Optional[str] = Field(default=None, max_length=64)


class HolidayUpdatePayload(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    kind: Optional[Literal["fixed", "movable"]] = None
    month: Optional[int] = Field(default=None, ge=1, le=12)
    day: Optional[int] = Field(default=None, ge=1, le=31)
    movable_rule: Optional[Literal["arbor_day", "labor_day", "thanksgiving"]] = None
    pre_shoulder_days: Optional[int] = Field(default=None, ge=0, le=90)
    post_shoulder_days: Optional[int] = Field(default=None, ge=0, le=90)
    search_terms: Optional[List[str]] = None
    enabled: Optional[bool] = None
    schedule_publish: Optional[bool] = None


class RailTitlePayload(BaseModel):
    library_item_id: int = Field(ge=1)
    curation: Literal["pin", "include", "exclude"]
    pin_position: Optional[int] = Field(default=None, ge=0, le=500)


class RailPinOrderPayload(BaseModel):
    library_item_ids: List[int] = Field(default_factory=list)


@router.get("/api/admin/holidays")
def list_holidays(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    db = _db()
    items = db.list_holiday_observances(include_disabled=True)
    schedule = db.list_holiday_schedule(horizon_days=60)
    return {"items": items, "schedule": schedule, "total": len(items)}


@router.post("/api/admin/holidays")
def create_holiday(
    payload: HolidayCreatePayload, user=Depends(require_role("owner"))
) -> Dict[str, Any]:
    del user
    try:
        item = _db().create_holiday_observance(payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item}


@router.post("/api/admin/holidays/restore-defaults")
def restore_holiday_defaults(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    result = _db().restore_holiday_defaults()
    items = _db().list_holiday_observances(include_disabled=True)
    return {"ok": True, **result, "items": items}


@router.get("/api/admin/holidays/{observance_id}")
def get_holiday(observance_id: str, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    item = _db().get_holiday_observance(observance_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return {"item": item}


@router.patch("/api/admin/holidays/{observance_id}")
def update_holiday(
    observance_id: str,
    payload: HolidayUpdatePayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    del user
    patch = {key: value for key, value in payload.model_dump().items() if value is not None}
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        item = _db().update_holiday_observance(observance_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if item is None:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return {"item": item}


@router.delete("/api/admin/holidays/{observance_id}")
def delete_holiday(observance_id: str, user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    deleted = _db().delete_holiday_observance(observance_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return {"ok": True, "id": observance_id}


@router.get("/api/admin/holidays/{observance_id}/rail")
def holiday_rail_preview(
    observance_id: str,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Preview the rail for one observance/season scope with curation applied."""
    del user
    from projectionist.library.feeds import preview_holiday_rail

    try:
        return preview_holiday_rail(_db(), observance_id, limit=12)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/api/admin/holidays/{observance_id}/rail/titles")
def set_holiday_rail_title(
    observance_id: str,
    payload: RailTitlePayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    del user
    db = _db()
    if db.get_holiday_observance(observance_id) is None and not observance_id.startswith(
        "season:"
    ):
        raise HTTPException(status_code=404, detail="Holiday not found")
    try:
        title = db.set_holiday_rail_title(
            observance_id,
            payload.library_item_id,
            curation=payload.curation,
            pin_position=payload.pin_position,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": title, "curation": db.list_holiday_rail_titles(observance_id)}


@router.delete("/api/admin/holidays/{observance_id}/rail/titles/{library_item_id}")
def clear_holiday_rail_title(
    observance_id: str,
    library_item_id: int,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    del user
    cleared = _db().clear_holiday_rail_title(observance_id, library_item_id)
    if not cleared:
        raise HTTPException(status_code=404, detail="Curation entry not found")
    return {"ok": True, "curation": _db().list_holiday_rail_titles(observance_id)}


@router.put("/api/admin/holidays/{observance_id}/rail/pins")
def reorder_holiday_rail_pins(
    observance_id: str,
    payload: RailPinOrderPayload,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    del user
    curation = _db().reorder_holiday_rail_pins(observance_id, payload.library_item_ids)
    return {"curation": curation}


@router.get("/api/admin/holidays-library-search")
def holiday_library_search(
    q: str = "",
    limit: int = 12,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    """Search owned library titles for the rail curation panel."""
    del user
    query = (q or "").strip()
    if not query:
        return {"items": [], "total": 0}
    filters = LibraryFilters(query=query, limit=max(1, min(int(limit or 12), 48)))
    result = query_library(_db(), filters)
    return {"items": result.get("items") or [], "total": int(result.get("total") or 0)}


@router.get("/api/admin/holidays-schedule")
def holiday_schedule(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    db = _db()
    return {
        "schedule": db.list_holiday_schedule(horizon_days=90),
        "today": feed_seasonal_spotlight(db, limit=12),
    }


@router.post("/api/admin/holidays-schedule/refresh")
def refresh_seasonal_rail_schedule(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    """Force B2 materialization of today's seasonal Explore rail."""
    del user
    return build_seasonal_rail_snapshot(_db(), limit=12)


def register_holidays_routes(app, *, db_factory: Callable[[], Any]) -> None:
    global _db_factory
    _db_factory = db_factory
    app.include_router(router)
