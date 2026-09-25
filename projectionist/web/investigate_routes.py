"""Episode investigation HTTP routes (v1.36.0).

Registered via ``register_investigate_routes`` so app.py stays the composition
root — same pattern as ``live_channels_routes``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from projectionist.config_store import load_merged_settings
from projectionist.web.auth import require_role

router = APIRouter(tags=["investigate"])


class InvestigateStartPayload(BaseModel):
    show_id: int = Field(ge=1)
    season: Optional[int] = Field(default=None, ge=0, le=99)
    use_vision: Optional[bool] = None


class InvestigateApplyPayload(BaseModel):
    file_ids: List[str] = Field(default_factory=list)


class InvestigateUndoPayload(BaseModel):
    apply_id: str = Field(min_length=1, max_length=64)


def _settings():
    from projectionist.web.jobs import get_job_manager

    return load_merged_settings(Path(get_job_manager().data_dir))


def _db():
    from projectionist.web.jobs import get_job_manager

    return get_job_manager().db


def _data_dir() -> Path:
    from projectionist.web.jobs import get_job_manager

    return Path(get_job_manager().data_dir)


@router.get("/api/admin/investigate/health")
def investigate_health(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.library.episode_investigate.capabilities import health_payload

    return health_payload(_settings())


@router.get("/api/admin/investigate/shows")
def investigate_shows(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.library.episode_investigate.catalog import list_investigate_shows

    items = list_investigate_shows(_db())
    return {"items": items, "total": len(items)}


@router.post("/api/admin/investigate/start")
def investigate_start(
    payload: InvestigateStartPayload, user=Depends(require_role("owner"))
) -> Dict[str, Any]:
    del user
    from projectionist.library.episode_investigate.job import start_investigate_job

    snap = start_investigate_job(
        _db(),
        _settings(),
        show_id=payload.show_id,
        season=payload.season,
        use_vision=payload.use_vision,
        data_dir=_data_dir(),
    )
    if snap.get("accepted") is False and snap.get("error"):
        raise HTTPException(status_code=400, detail=str(snap.get("error")))
    return snap


@router.get("/api/admin/investigate/status")
def investigate_status(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.library.episode_investigate.job import build_status

    return build_status()


@router.post("/api/admin/investigate/cancel")
def investigate_cancel(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.library.episode_investigate.job import cancel_job

    return cancel_job()


@router.post("/api/admin/investigate/apply")
def investigate_apply(
    payload: InvestigateApplyPayload, user=Depends(require_role("owner"))
) -> Dict[str, Any]:
    del user
    from projectionist.library.episode_investigate.job import start_apply_job

    snap = start_apply_job(_settings(), file_ids=payload.file_ids)
    if snap.get("accepted") is False and snap.get("error"):
        raise HTTPException(status_code=400, detail=str(snap.get("error")))
    return snap


@router.get("/api/admin/investigate/apply/status")
def investigate_apply_status(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.library.episode_investigate.job import build_apply_status

    return build_apply_status()


@router.post("/api/admin/investigate/apply/cancel")
def investigate_apply_cancel(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.library.episode_investigate.job import cancel_apply_job

    return cancel_apply_job()


@router.post("/api/admin/investigate/undo")
def investigate_undo(
    payload: InvestigateUndoPayload, user=Depends(require_role("owner"))
) -> Dict[str, Any]:
    del user
    from projectionist.library.episode_investigate.job import start_undo_job

    snap = start_undo_job(_settings(), apply_id=payload.apply_id)
    if snap.get("accepted") is False and snap.get("error"):
        raise HTTPException(status_code=400, detail=str(snap.get("error")))
    return snap


@router.get("/api/admin/investigate/stills/{job_id}/{file_id}/{name}")
def investigate_still(
    job_id: str,
    file_id: str,
    name: str,
    user=Depends(require_role("owner")),
) -> FileResponse:
    del user
    from projectionist.library.episode_investigate.stills import resolve_still

    path = resolve_still(_data_dir(), job_id, file_id, name)
    if path is None:
        raise HTTPException(status_code=404, detail="Still not found")
    return FileResponse(path, media_type="image/jpeg")


def register_investigate_routes(app) -> None:
    """Attach investigation routes to the FastAPI app."""
    app.include_router(router)
