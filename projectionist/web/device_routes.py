"""Apple TV pairing, revoke, and throw.

Unsigned issue / rotate / pending poll. Claim, list, revoke, and throw use
the signed-in household session. The TV reads its intent with the device bearer.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from projectionist.devices.pairing import (
    DEVICE_REVOKED_DETAIL,
    INTENT_NOT_TV_DETAIL,
    REVOKE_FORBIDDEN_DETAIL,
    THROW_REVOKED_DETAIL,
    THROW_UNPAIRED_DETAIL,
    TITLE_HIDDEN_DETAIL,
    TITLE_MISSING_DETAIL,
    YOUTH_STATION_DETAIL,
    YOUTH_TITLE_DETAIL,
    DevicePairError,
    claim_pair,
    device_for_credential,
    get_device,
    issue_pair,
    list_devices,
    poll_pending,
    revoke_device,
    rotate_pair,
    store_intent,
    take_intent,
)
from projectionist.web.auth import _bearer_token, get_current_user_dep, row_to_current_user
from projectionist.web.rate_limit import enforce_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(tags=["devices"])

_STATION_ID = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_NO_STORE = {"Cache-Control": "no-store"}
_THROWER_STATION_DETAIL = "This channel’s current program is above your youth rating limit."


class PairIssuePayload(BaseModel):
    label: Optional[str] = None


class PairRotatePayload(BaseModel):
    pending_id: str = ""


class PairClaimPayload(BaseModel):
    code: str = ""


class ThrowPayload(BaseModel):
    kind: str = ""
    media_type: str = ""
    item_id: str = ""
    id_type: str = "rating_key"
    station_id: str = ""


def _db():
    from projectionist.web.jobs import get_job_manager

    return get_job_manager().db


def _settings():
    from pathlib import Path

    from projectionist.config_store import load_merged_settings
    from projectionist.web.jobs import get_job_manager

    return load_merged_settings(Path(get_job_manager().data_dir))


def _json(payload: Dict[str, Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=_NO_STORE)


def _raise_pair(error: DevicePairError) -> None:
    raise HTTPException(status_code=error.status_code, detail=error.detail) from error


def _viewer(row: Any) -> Dict[str, Any]:
    if row is None:
        return {"is_youth": False}
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    flag = row["is_youth"] if "is_youth" in keys else 0
    try:
        youth = bool(int(flag or 0))
    except (TypeError, ValueError):
        youth = bool(flag)
    return {"is_youth": youth}


def _member_brief(db: Any, user_id: str) -> Optional[Dict[str, Any]]:
    row = db.get_user(user_id)
    if row is None:
        return None
    user = row_to_current_user(row)
    return {
        "id": user.id,
        "display_name": user.display_name,
        "role": user.role,
        "is_youth": user.is_youth,
    }


@router.post("/api/devices/pair/issue")
def pair_issue(request: Request, payload: Optional[PairIssuePayload] = None) -> JSONResponse:
    """Unsigned TV. Short code, expiry in minutes, and a pending id. No credential."""
    enforce_rate_limit(request, bucket="device_pair_issue", limit=30, window_seconds=60)
    body = payload or PairIssuePayload()
    try:
        issued = issue_pair(_db(), label=body.label)
    except DevicePairError as error:
        _raise_pair(error)
        raise
    return _json(issued)


@router.post("/api/devices/pair/rotate")
def pair_rotate(request: Request, payload: PairRotatePayload) -> JSONResponse:
    """New code for this pending TV. The previous code is dead."""
    enforce_rate_limit(request, bucket="device_pair_rotate", limit=30, window_seconds=60)
    try:
        result = rotate_pair(_db(), payload.pending_id)
    except DevicePairError as error:
        _raise_pair(error)
        raise
    return _json(result["body"], int(result["http"]))


@router.get("/api/devices/pair/pending/{pending_id}")
def pair_pending(pending_id: str) -> JSONResponse:
    """Pending, the credential once after claim, or issue-again."""
    result = poll_pending(_db(), pending_id)
    body = dict(result["body"])
    if body.get("status") == "claimed":
        user_id = str(body.pop("user_id", "") or "")
        member = _member_brief(_db(), user_id)
        if member is not None:
            body["member"] = member
    return _json(body, int(result["http"]))


@router.post("/api/devices/pair/claim")
def pair_claim(
    request: Request,
    payload: PairClaimPayload,
    user=Depends(get_current_user_dep),
) -> JSONResponse:
    """Logged-in web session consumes the code once and binds that member."""
    enforce_rate_limit(request, bucket="device_pair_claim", limit=20, window_seconds=60)
    try:
        claimed = claim_pair(_db(), code=payload.code, user_id=str(user.id))
    except DevicePairError as error:
        _raise_pair(error)
        raise
    logger.info("Apple TV %s claimed by user %s", claimed.get("device_id"), user.id)
    return _json(claimed)


@router.get("/api/devices")
def devices_list(user=Depends(get_current_user_dep)) -> JSONResponse:
    """Active paired TVs the signed-in household can throw to."""
    owner = str(getattr(user, "role", "") or "") == "owner"
    devices = []
    for device in list_devices(_db()):
        device["can_revoke"] = owner or device["user_id"] == str(user.id)
        devices.append(device)
    return _json({"devices": devices})


@router.post("/api/devices/{device_id}/revoke")
def devices_revoke(device_id: str, user=Depends(get_current_user_dep)) -> JSONResponse:
    """Drop a lost Apple TV. Its next member call fails in plain language."""
    device = get_device(_db(), device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=THROW_UNPAIRED_DETAIL)
    owner = str(getattr(user, "role", "") or "") == "owner"
    if not owner and device["user_id"] != str(user.id):
        raise HTTPException(status_code=403, detail=REVOKE_FORBIDDEN_DETAIL)
    try:
        revoke_device(_db(), device["id"])
    except DevicePairError as error:
        _raise_pair(error)
        raise
    logger.info("Apple TV %s revoked by user %s", device["id"], user.id)
    return _json({"status": "revoked", "device_id": device["id"]})


def _require_title(payload: ThrowPayload, thrower: Any, paired_row: Any) -> Dict[str, str]:
    media_type = str(payload.media_type or "").strip().lower()
    item_id = str(payload.item_id or "").strip()
    id_type = str(payload.id_type or "rating_key").strip().lower() or "rating_key"
    if id_type != "rating_key":
        raise HTTPException(status_code=400, detail="Apple TV throw uses a library rating key.")
    if media_type not in {"movie", "show"}:
        raise HTTPException(status_code=400, detail="Say whether this is a movie or a show.")
    if not item_id or ".." in item_id or len(item_id) > 128:
        raise HTTPException(status_code=400, detail="A library title is required.")
    settings = _settings()
    row = _db().library_item_by_rating_key(item_id)
    thrower_youth = bool(getattr(thrower, "is_youth", False))
    if row is None or str(row["media_type"] or "").lower() != media_type:
        raise HTTPException(
            status_code=404,
            detail=TITLE_HIDDEN_DETAIL if thrower_youth else TITLE_MISSING_DETAIL,
        )
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    rating = str(row["content_rating"] or "") if "content_rating" in keys else ""
    detail = {"content_rating": rating}
    from projectionist.youth.apply import title_allowed_for_user

    if not title_allowed_for_user(detail, user=thrower, settings=settings):
        raise HTTPException(status_code=404, detail=TITLE_HIDDEN_DETAIL)
    if not title_allowed_for_user(detail, user=_viewer(paired_row), settings=settings):
        raise HTTPException(status_code=403, detail=YOUTH_TITLE_DETAIL)
    return {"media_type": media_type, "item_id": item_id, "id_type": "rating_key"}


def _require_station(payload: ThrowPayload, thrower: Any, paired_row: Any) -> Dict[str, str]:
    station_id = str(payload.station_id or "").strip()
    if not _STATION_ID.match(station_id):
        raise HTTPException(status_code=400, detail="A live station is required.")
    paired_youth = bool(_viewer(paired_row).get("is_youth"))
    thrower_youth = bool(getattr(thrower, "is_youth", False))
    if not paired_youth and not thrower_youth:
        return {"station_id": station_id}
    settings = _settings()
    if not bool(getattr(settings.features, "live_channels_enabled", False)):
        raise HTTPException(status_code=400, detail="Live TV is not on.")
    from projectionist.live_channels.guide import build_on_now_snapshot, youth_allows_channel_now
    from projectionist.youth.rating_gate import resolve_youth_max_rating

    try:
        snap = build_on_now_snapshot(settings, youth_max_rating=None)
    except Exception as error:  # noqa: BLE001
        logger.info("Apple TV station throw could not read the lineup: %s", error)
        raise HTTPException(
            status_code=400, detail="The lineup isn't available right now."
        ) from error
    channels = snap.get("channels") if isinstance(snap, dict) else None
    target = next(
        (channel for channel in channels or [] if str(channel.get("id")) == station_id),
        None,
    )
    if target is None:
        raise HTTPException(status_code=404, detail="That station is not in the lineup.")
    if not youth_allows_channel_now(target, max_rating=resolve_youth_max_rating(settings)):
        detail = YOUTH_STATION_DETAIL if paired_youth else _THROWER_STATION_DETAIL
        raise HTTPException(status_code=403, detail=detail)
    return {"station_id": station_id}


@router.post("/api/devices/{device_id}/throw")
def devices_throw(
    device_id: str,
    payload: ThrowPayload,
    user=Depends(get_current_user_dep),
) -> JSONResponse:
    """Queue one title or station for this paired TV. The TV still acts as its member."""
    device = get_device(_db(), device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=THROW_UNPAIRED_DETAIL)
    if device["revoked"]:
        raise HTTPException(status_code=409, detail=THROW_REVOKED_DETAIL)
    kind = str(payload.kind or "").strip().lower()
    paired_row = _db().get_user(device["user_id"])
    if kind == "title":
        stored = _require_title(payload, user, paired_row)
    elif kind == "station":
        stored = _require_station(payload, user, paired_row)
    else:
        raise HTTPException(status_code=400, detail="Send a library title or a live station.")
    try:
        intent_id = store_intent(_db(), device["id"], kind=kind, payload=stored)
    except DevicePairError as error:
        _raise_pair(error)
        raise
    return _json({"status": "queued", "device_id": device["id"], "intent_id": intent_id})


@router.get("/api/devices/me/intent")
def devices_my_intent(request: Request, user=Depends(get_current_user_dep)) -> JSONResponse:
    """The paired TV's bearer. One intent, then empty until the next throw."""
    token = _bearer_token(request)
    if not token:
        raise HTTPException(status_code=400, detail=INTENT_NOT_TV_DETAIL)
    device = device_for_credential(_db(), token)
    if device is None:
        raise HTTPException(status_code=401, detail=DEVICE_REVOKED_DETAIL)
    if device["user_id"] != str(user.id):
        raise HTTPException(status_code=401, detail="Authentication required")
    intent = take_intent(_db(), device["id"])
    return _json({"intent": intent})


def register_device_routes(app) -> None:
    """Attach Apple TV pairing and throw routes."""
    app.include_router(router)
