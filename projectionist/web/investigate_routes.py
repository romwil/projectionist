"""Episode investigation HTTP routes (v1.36.0 + Identify v1.36.1).

Registered via ``register_investigate_routes`` so app.py stays the composition
root — same pattern as ``live_channels_routes``.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from projectionist.config_store import AcrcloudSettings, load_merged_settings, save_settings, Settings
from projectionist.web.auth import require_role

router = APIRouter(tags=["investigate"])


class InvestigateStartPayload(BaseModel):
    show_id: int = Field(ge=1)
    season: Optional[int] = Field(default=None, ge=0, le=99)
    use_vision: Optional[bool] = None


class InvestigateApplyPayload(BaseModel):
    file_ids: List[str] = Field(default_factory=list)
    create_opt_in: List[str] = Field(default_factory=list)


class IdentifySettingsPayload(BaseModel):
    host: str = ""
    access_key: str = ""
    access_secret: str = ""


class IdentifyTestPayload(BaseModel):
    path: str = ""
    file_id: str = ""


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

    snap = start_apply_job(
        _settings(),
        file_ids=payload.file_ids,
        create_opt_in=payload.create_opt_in,
    )
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


@router.get("/api/admin/investigate/identify/settings")
def identify_settings(user=Depends(require_role("owner"))) -> Dict[str, Any]:
    del user
    from projectionist.library.episode_investigate.acrcloud import DEFAULT_HOST
    from projectionist.library.episode_investigate.capabilities import acrcloud_config

    creds = acrcloud_config(_settings())
    return {
        "host": str(creds.get("host") or ""),
        "default_host": DEFAULT_HOST,
        "access_key_set": bool(creds.get("access_key")),
        "access_secret_set": bool(creds.get("access_secret")),
        "available": bool(creds.get("available")),
        "source": {
            "host": creds.get("host_source") or "",
            "access_key": creds.get("access_key_source") or "",
            "access_secret": creds.get("access_secret_source") or "",
        },
    }


@router.put("/api/admin/investigate/identify/settings")
def identify_settings_save(
    payload: IdentifySettingsPayload, user=Depends(require_role("owner"))
) -> Dict[str, Any]:
    del user
    from projectionist.library.episode_investigate.acrcloud import normalize_identify_host
    from projectionist.library.episode_investigate.capabilities import acrcloud_config

    data_dir = _data_dir()
    current = load_merged_settings(data_dir)
    existing = getattr(current, "acrcloud", AcrcloudSettings())
    host = str(payload.host or "").strip()
    if host:
        try:
            host = normalize_identify_host(host)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
    else:
        host = str(existing.host or "").strip()
    access_key = str(payload.access_key or "").strip() or str(existing.access_key or "")
    access_secret = str(payload.access_secret or "").strip() or str(existing.access_secret or "")
    updated = Settings.from_mapping(
        {
            **asdict(current),
            "acrcloud": {
                "host": host,
                "access_key": access_key,
                "access_secret": access_secret,
            },
        }
    )
    save_settings(data_dir, updated)
    creds = acrcloud_config(load_merged_settings(data_dir))
    return {
        "ok": True,
        "host": str(creds.get("host") or host),
        "access_key_set": bool(creds.get("access_key")),
        "access_secret_set": bool(creds.get("access_secret")),
        "available": bool(creds.get("available")),
        "source": {
            "host": creds.get("host_source") or "",
            "access_key": creds.get("access_key_source") or "",
            "access_secret": creds.get("access_secret_source") or "",
        },
    }


@router.post("/api/admin/investigate/identify/test")
def identify_test(
    payload: IdentifyTestPayload, user=Depends(require_role("owner"))
) -> Dict[str, Any]:
    del user
    from projectionist.library.episode_investigate.acrcloud import test_identify_clip
    from projectionist.library.episode_investigate.job import build_status

    path = str(payload.path or "").strip()
    if not path and payload.file_id:
        snap = build_status()
        result = snap.get("result") if isinstance(snap.get("result"), dict) else {}
        for row in result.get("rows") or []:
            if str(row.get("id") or "") == str(payload.file_id):
                path = str(row.get("path") or "")
                break
    snap = test_identify_clip(settings=_settings(), path=path, dest_dir=_data_dir() / "investigate" / "identify-test")
    if snap.get("renamed"):
        snap["renamed"] = False
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
