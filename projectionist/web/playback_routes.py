"""Household library Play — auth’d Plex HLS session proxy."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from projectionist.config_store import Settings
from projectionist.library.playback import (
    PlaybackError,
    YouthBlockedError,
    get_session,
    iter_chunked,
    proxy_session_asset,
    report_progress,
    seek_playback,
    start_playback,
    stop_playback,
    validate_rating_key,
    validate_session_id,
)
from projectionist.web.auth import get_current_user_dep

router = APIRouter(tags=["library-playback"])

_settings_factory: Optional[Callable[[], Settings]] = None
_db_factory: Optional[Callable[[], Any]] = None
_safe_error_detail_fn: Optional[Callable[..., str]] = None


def _settings() -> Settings:
    if _settings_factory is None:
        raise RuntimeError("playback routes not registered")
    return _settings_factory()


def _db():
    if _db_factory is None:
        raise RuntimeError("playback routes not registered")
    return _db_factory()


def _safe_error_detail(error: Exception, context: str = "") -> str:
    if _safe_error_detail_fn is None:
        raise RuntimeError("playback routes not registered")
    return _safe_error_detail_fn(error, context)


def _user_id(user: Any) -> str:
    return str(getattr(user, "id", "") or "")


def _raise_playback(error: Exception, context: str) -> None:
    if isinstance(error, PlaybackError):
        raise HTTPException(status_code=error.status_code, detail=error.message) from error
    raise HTTPException(status_code=502, detail=_safe_error_detail(error, context)) from error


class PlaybackStartPayload(BaseModel):
    rating_key: str = ""
    start_over: bool = False


class PlaybackSeekPayload(BaseModel):
    offset_ms: int = Field(default=0, ge=0)


class PlaybackProgressPayload(BaseModel):
    state: str = "playing"
    time_ms: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=0, ge=0)


class PlaybackStopPayload(BaseModel):
    time_ms: Optional[int] = Field(default=None, ge=0)
    duration_ms: Optional[int] = Field(default=None, ge=0)


@router.post("/api/library/playback/start")
def library_playback_start(
    payload: PlaybackStartPayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Start a Plex universal HLS session for a movie or episode (show keys resolve)."""
    try:
        key = validate_rating_key(payload.rating_key)
        return start_playback(
            _db(),
            _settings(),
            rating_key=key,
            user=user,
            start_over=bool(payload.start_over),
        )
    except (PlaybackError, YouthBlockedError) as error:
        _raise_playback(error, "Could not start playback")
        raise
    except Exception as error:  # noqa: BLE001
        _raise_playback(error, "Could not start playback")
        raise


@router.post("/api/library/playback/{session_id}/seek")
def library_playback_seek(
    session_id: str,
    payload: PlaybackSeekPayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Restart the Plex transcode at ``offset_ms`` (large VOD jumps)."""
    try:
        session = get_session(validate_session_id(session_id), user_id=_user_id(user))
        return seek_playback(session, int(payload.offset_ms or 0))
    except PlaybackError as error:
        _raise_playback(error, "Could not seek")
        raise
    except Exception as error:  # noqa: BLE001
        _raise_playback(error, "Could not seek")
        raise


@router.post("/api/library/playback/{session_id}/progress")
def library_playback_progress(
    session_id: str,
    payload: PlaybackProgressPayload,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Throttled Plex timeline + local ``view_offset_ms``. No now-watching feed."""
    try:
        session = get_session(validate_session_id(session_id), user_id=_user_id(user))
        return report_progress(
            _db(),
            session,
            state=str(payload.state or "playing"),
            time_ms=int(payload.time_ms or 0),
            duration_ms=int(payload.duration_ms or 0),
        )
    except PlaybackError as error:
        _raise_playback(error, "Could not record progress")
        raise
    except Exception as error:  # noqa: BLE001
        _raise_playback(error, "Could not record progress")
        raise


@router.post("/api/library/playback/{session_id}/stop")
def library_playback_stop(
    session_id: str,
    payload: Optional[PlaybackStopPayload] = None,
    user=Depends(get_current_user_dep),
) -> Dict[str, Any]:
    """Stop the Plex transcode and write a final timeline."""
    body = payload or PlaybackStopPayload()
    try:
        session = get_session(validate_session_id(session_id), user_id=_user_id(user))
        return stop_playback(
            _db(),
            session,
            time_ms=body.time_ms,
            duration_ms=body.duration_ms,
        )
    except PlaybackError as error:
        _raise_playback(error, "Could not stop playback")
        raise
    except Exception as error:  # noqa: BLE001
        _raise_playback(error, "Could not stop playback")
        raise


@router.get("/api/library/playback/{session_id}/index.m3u8")
@router.get("/api/library/playback/{session_id}/master.m3u8")
def library_playback_master(
    session_id: str,
    user=Depends(get_current_user_dep),
):
    """Auth’d HLS master playlist (session cookie; no PMS leak)."""
    return _playback_stream_response(session_id, "index.m3u8", user=user)


@router.get("/api/library/playback/{session_id}/{path:path}")
def library_playback_path(
    session_id: str,
    path: str,
    user=Depends(get_current_user_dep),
):
    """Auth’d HLS media playlist / segment proxy."""
    return _playback_stream_response(session_id, path, user=user)


def _playback_stream_response(session_id: str, relative_path: str, *, user):
    try:
        session = get_session(validate_session_id(session_id), user_id=_user_id(user))
        asset = proxy_session_asset(session, relative_path)
    except PlaybackError as error:
        _raise_playback(error, "Library stream unavailable")
        raise
    except Exception as error:  # noqa: BLE001
        _raise_playback(error, "Library stream unavailable")
        raise
    return StreamingResponse(
        iter_chunked(asset["body"]),
        media_type=str(asset.get("media_type") or "application/octet-stream"),
        status_code=int(asset.get("status") or 200),
        headers={
            "Cache-Control": "no-store",
            "Access-Control-Expose-Headers": "Content-Type",
        },
    )


def register_playback_routes(
    app,
    *,
    settings_factory: Callable[[], Settings],
    db_factory: Callable[[], Any],
    safe_error_detail: Callable[..., str],
) -> None:
    """Attach library playback routes to the FastAPI app."""
    global _settings_factory, _db_factory, _safe_error_detail_fn
    _settings_factory = settings_factory
    _db_factory = db_factory
    _safe_error_detail_fn = safe_error_detail
    app.include_router(router)
