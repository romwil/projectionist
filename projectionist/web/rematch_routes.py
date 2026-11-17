"""Rematch studio HTTP routes (v1.36.2+).

Registered via ``register_rematch_routes`` so app.py stays the composition root.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from projectionist.config_store import load_merged_settings
from projectionist.web.auth import require_role

router = APIRouter(tags=["rematch"])


class RematchSkipPayload(BaseModel):
    item_id: int = Field(ge=1)
    skipped: bool = True


class RematchRetryPayload(BaseModel):
    item_id: int = Field(ge=1)


class RematchConfirmPayload(BaseModel):
    item_id: int = Field(ge=1)
    confirm: bool = False


class RematchRecheckPayload(BaseModel):
    item_ids: Optional[List[int]] = None


def _settings():
    from projectionist.web.jobs import get_job_manager

    return load_merged_settings(Path(get_job_manager().data_dir))


def _db():
    from projectionist.web.jobs import get_job_manager

    return get_job_manager().db


@router.get("/api/admin/rematch/scan")
def rematch_scan(
    include_skipped: bool = False,
    user=Depends(require_role("owner")),
) -> Dict[str, Any]:
    del user
    from projectionist.library.rematch import scan_identity_mismatches

    return scan_identity_mismatches(_db(), _settings(), include_skipped=include_skipped)


@router.post("/api/admin/rematch/skip")
def rematch_skip(
    payload: RematchSkipPayload, user=Depends(require_role("owner"))
) -> Dict[str, Any]:
    del user
    from projectionist.library.rematch import set_skipped

    ids = set_skipped(_db(), payload.item_id, skipped=payload.skipped)
    return {"ok": True, "item_id": payload.item_id, "skipped": payload.skipped, "skipped_ids": ids}


@router.post("/api/admin/rematch/retry")
def rematch_retry(
    payload: RematchRetryPayload, user=Depends(require_role("owner"))
) -> Dict[str, Any]:
    del user
    from projectionist.library.rematch import retry_register_title

    try:
        return retry_register_title(_db(), _settings(), payload.item_id)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/api/admin/rematch/recheck")
def rematch_recheck(
    payload: RematchRecheckPayload, user=Depends(require_role("owner"))
) -> Dict[str, Any]:
    del user
    from projectionist.library.rematch import recheck_path_conflicts

    try:
        return recheck_path_conflicts(_db(), _settings(), payload.item_ids)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/api/admin/rematch/adopt-radarr")
def rematch_adopt_radarr(
    payload: RematchConfirmPayload, user=Depends(require_role("owner"))
) -> Dict[str, Any]:
    del user
    from projectionist.library.rematch import adopt_radarr_identity

    try:
        result = adopt_radarr_identity(
            _db(), _settings(), payload.item_id, confirm=payload.confirm
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    from projectionist.library.rematch import _sync_register_item_outcome

    if result.get("ok"):
        _sync_register_item_outcome(
            payload.item_id,
            outcome=str(result.get("outcome") or "adopted_radarr"),
            message=str(result.get("message") or ""),
        )
    return result


@router.post("/api/admin/rematch/adopt-plex")
def rematch_adopt_plex(
    payload: RematchConfirmPayload, user=Depends(require_role("owner"))
) -> Dict[str, Any]:
    del user
    from projectionist.library.rematch import adopt_plex_identity

    try:
        result = adopt_plex_identity(
            _db(), _settings(), payload.item_id, confirm=payload.confirm
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    from projectionist.library.rematch import _sync_register_item_outcome

    if result.get("ok"):
        _sync_register_item_outcome(
            payload.item_id,
            outcome=str(result.get("outcome") or "adopted_plex"),
            message=str(result.get("message") or ""),
        )
    return result


@router.get("/api/admin/rematch/repairs")
def rematch_repairs(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.library.radarr_register import build_status
    from projectionist.library.rematch import PLEX_RADARR_REMATCH_API_NOTE, collect_repair_misses
    from projectionist.library.sonarr_missing import build_status as sonarr_status

    register = build_status()
    try:
        missing = sonarr_status()
    except Exception:  # noqa: BLE001
        missing = {}
    items = collect_repair_misses(
        register_items=register.get("items") if isinstance(register, dict) else None,
        sonarr_status=missing if isinstance(missing, dict) else None,
    )
    return {"items": items, "total": len(items), "api_note": PLEX_RADARR_REMATCH_API_NOTE}


def register_rematch_routes(app) -> None:
    """Attach rematch studio routes to the FastAPI app."""
    app.include_router(router)
