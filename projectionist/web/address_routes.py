"""Owner setting for the public base URL (the away address)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from projectionist.config_store import Settings, save_settings
from projectionist.public_url import PublicBaseUrlError, normalize_public_base_url
from projectionist.web.addresses import stored_public_base_url
from projectionist.web.auth import require_role

router = APIRouter(tags=["network"])

_settings_factory: Callable[[], Settings] | None = None
_data_dir_factory: Callable[[], Path] | None = None


class PublicBaseUrlPayload(BaseModel):
    public_base_url: str = Field(default="", max_length=2000)


def _settings() -> Settings:
    if _settings_factory is None:
        raise RuntimeError("address routes not registered")
    return _settings_factory()


def _dir() -> Path:
    if _data_dir_factory is None:
        raise RuntimeError("address routes not registered")
    return Path(_data_dir_factory())


def _save_public_base_url(value: str) -> str:
    from dataclasses import asdict

    existing = _settings()
    current = asdict(existing)
    network = dict(current.get("network") or {})
    network["public_base_url"] = value
    current["network"] = network
    updated = Settings.from_mapping(current)
    save_settings(_dir(), updated)
    return stored_public_base_url(updated)


@router.get("/api/network/public-base-url")
def get_public_base_url(user=Depends(require_role("owner"))) -> dict[str, Any]:
    """The away address. Empty until the owner sets one."""
    del user
    return {"public_base_url": stored_public_base_url(_settings())}


@router.put("/api/network/public-base-url")
def put_public_base_url(
    payload: PublicBaseUrlPayload,
    user=Depends(require_role("owner")),
) -> dict[str, Any]:
    """Set or clear the away address. The next features response picks it up."""
    del user
    try:
        cleaned = normalize_public_base_url(payload.public_base_url)
    except PublicBaseUrlError as error:
        raise HTTPException(status_code=400, detail=error.detail) from error
    return {"public_base_url": _save_public_base_url(cleaned)}


def register_address_routes(
    app,
    *,
    settings_factory: Callable[[], Settings],
    data_dir_factory: Callable[[], Path],
) -> None:
    """Attach the away-address routes. Call once from the app factory."""
    global _settings_factory, _data_dir_factory
    _settings_factory = settings_factory
    _data_dir_factory = data_dir_factory
    app.include_router(router)
