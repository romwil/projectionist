"""Optional multi-user auth (inactive when features.multi_user_enabled=false)."""

from __future__ import annotations

import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Literal, Optional

from fastapi import Depends, HTTPException, Request, Response
from starlette.responses import JSONResponse

from curatorx.config_store import Settings, load_merged_settings
from curatorx.connectors.plex_account import (
    create_plex_pin,
    fetch_plex_account,
    fetch_plex_pin,
    get_or_create_client_id,
)
from curatorx.connectors.seerr import SeerrClient
from curatorx.config_store import seerr_configuration_error
from curatorx.library.db import BOOTSTRAP_OWNER_ID, Database
from curatorx.web.rate_limit import enforce_rate_limit
from curatorx.web.session_tokens import (
    DEFAULT_TTL_SECONDS,
    SESSION_COOKIE_NAME,
    create_session_token,
    parse_session_token,
)

_API_AUTH_ALLOWLIST_EXACT = frozenset({"/api/health", "/api/features"})
_API_AUTH_ALLOWLIST_PREFIXES = ("/api/auth/", "/api/webhooks/", "/mcp")
PLEX_PIN_NONCE_COOKIE = "plex_pin_nonce"
PLEX_PIN_NONCE_TTL_SECONDS = 1800

_pin_bindings_lock = threading.Lock()
_pin_bindings: Dict[str, Dict[str, Any]] = {}

UserRole = Literal["owner", "member", "guest"]


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", "/config"))


def _settings() -> Settings:
    return load_merged_settings(_data_dir())


@dataclass(frozen=True)
class CurrentUser:
    id: str
    display_name: str
    role: UserRole
    email: Optional[str] = None
    plex_user_id: Optional[str] = None
    seerr_user_id: Optional[int] = None
    avatar_url: Optional[str] = None
    preferred_name: Optional[str] = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "preferred_name": self.preferred_name,
            "role": self.role,
            "email": self.email,
            "plex_user_id": self.plex_user_id,
            "seerr_user_id": self.seerr_user_id,
            "avatar_url": self.avatar_url,
        }


_ROLE_RANK = {"guest": 0, "member": 1, "owner": 2}


def row_to_current_user(row) -> CurrentUser:
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    avatar_url = None
    if "avatar_url" in keys and row["avatar_url"] is not None:
        avatar_url = str(row["avatar_url"])
    preferred_name = None
    if "preferred_name" in keys and row["preferred_name"] is not None:
        preferred_name = str(row["preferred_name"]).strip() or None
    return CurrentUser(
        id=str(row["id"]),
        display_name=str(row["display_name"] or "User"),
        role=str(row["role"]),  # type: ignore[arg-type]
        email=str(row["email"]) if row["email"] is not None else None,
        plex_user_id=str(row["plex_user_id"]) if row["plex_user_id"] is not None else None,
        seerr_user_id=int(row["seerr_user_id"]) if row["seerr_user_id"] is not None else None,
        avatar_url=avatar_url,
        preferred_name=preferred_name,
    )


def bootstrap_owner(db: Optional[Database] = None) -> CurrentUser:
    if db is not None:
        # Read first — avoid a write on every /api/features hit once owner exists.
        row = db.get_user(BOOTSTRAP_OWNER_ID)
        if row is None:
            db.ensure_bootstrap_owner()
            row = db.get_user(BOOTSTRAP_OWNER_ID)
        if row is not None:
            return row_to_current_user(row)
    return CurrentUser(id=BOOTSTRAP_OWNER_ID, display_name="Owner", role="owner")


def _cookie_should_be_secure(request: Optional[Request]) -> bool:
    if request is None:
        return False
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    return forwarded == "https"


def set_session_cookie(
    response: Response,
    user_id: str,
    request: Optional[Request] = None,
) -> None:
    token = create_session_token(user_id)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=DEFAULT_TTL_SECONDS,
        path="/",
        secure=_cookie_should_be_secure(request),
    )


def clear_session_cookie(response: Response, request: Optional[Request] = None) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        secure=_cookie_should_be_secure(request),
    )


def is_public_api_path(path: str) -> bool:
    """Paths that stay reachable without a session when multi-user is enabled."""
    cleaned = (path or "").split("?", 1)[0]
    if cleaned in _API_AUTH_ALLOWLIST_EXACT:
        return True
    return any(cleaned.startswith(prefix) for prefix in _API_AUTH_ALLOWLIST_PREFIXES)


def _user_is_disabled(row) -> bool:
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    if "disabled" not in keys or row["disabled"] is None:
        return False
    return bool(int(row["disabled"]))


def _user_from_session(request: Request, db: Database) -> Optional[CurrentUser]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    user_id = parse_session_token(token)
    if not user_id:
        return None
    row = db.get_user(user_id)
    if row is None:
        return None
    if _user_is_disabled(row):
        return None
    return row_to_current_user(row)


async def multi_user_api_auth_middleware(request: Request, call_next):
    """Require a valid session for /api/* when multi-user auth is enabled."""
    path = request.url.path
    if path.startswith("/mcp"):
        return await call_next(request)
    if not path.startswith("/api/") or is_public_api_path(path):
        return await call_next(request)

    settings = _settings()
    if not settings.features.multi_user_enabled:
        return await call_next(request)

    from curatorx.web.jobs import get_job_manager

    user = _user_from_session(request, get_job_manager().db)
    if user is None:
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    return await call_next(request)


def get_current_user(request: Request, db: Optional[Database] = None) -> CurrentUser:
    settings = _settings()
    if not settings.features.multi_user_enabled:
        return bootstrap_owner(db)
    if db is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    user = _user_from_session(request, db)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def try_get_current_user(request: Request, db: Optional[Database] = None) -> Optional[CurrentUser]:
    settings = _settings()
    if not settings.features.multi_user_enabled:
        return bootstrap_owner(db)
    if db is None:
        return None
    return _user_from_session(request, db)


def get_current_user_dep(request: Request) -> CurrentUser:
    from curatorx.web.jobs import get_job_manager

    return get_current_user(request, get_job_manager().db)


def require_role(minimum_role: UserRole) -> Callable[..., CurrentUser]:
    def dependency(user: CurrentUser = Depends(get_current_user_dep)) -> CurrentUser:
        settings = _settings()
        if not settings.features.multi_user_enabled:
            return user
        if _ROLE_RANK.get(user.role, 0) < _ROLE_RANK.get(minimum_role, 99):
            raise HTTPException(status_code=403, detail=f"Requires {minimum_role} role")
        return user

    return dependency


def _plex_profile_fields(profile: dict[str, object]) -> tuple[str, str, Optional[str], Optional[str]]:
    plex_user_id = str(profile.get("id") or profile.get("uuid") or "").strip()
    if not plex_user_id:
        raise HTTPException(status_code=400, detail="Plex account response missing user id")
    display_name = str(profile.get("title") or profile.get("username") or "Plex User").strip()
    email_raw = profile.get("email")
    email = str(email_raw).strip() if email_raw else None
    thumb_raw = profile.get("thumb")
    avatar_url = str(thumb_raw).strip() if thumb_raw else None
    return plex_user_id, display_name, email, avatar_url


def _bridge_seerr_on_login(
    settings: Settings,
    auth_token: str,
) -> tuple[Optional[int], Optional[int]]:
    if not settings.features.seerr_enabled or not settings.seerr.link_on_login:
        return None, None
    if seerr_configuration_error(settings):
        return None, None
    client = SeerrClient(settings.seerr.url, settings.seerr.api_key)
    payload = client.link_plex_user(auth_token)
    seerr_user_id = payload.get("id")
    permissions = payload.get("permissions")
    return (
        int(seerr_user_id) if seerr_user_id is not None else None,
        int(permissions) if permissions is not None else None,
    )


def _ensure_plex_login_enabled() -> Settings:
    settings = _settings()
    if not settings.features.multi_user_enabled:
        raise HTTPException(status_code=400, detail="Multi-user auth is not enabled")
    if not settings.auth.plex_login_enabled:
        raise HTTPException(status_code=400, detail="Plex login is not enabled")
    return settings


def _purge_expired_pin_bindings() -> None:
    now = time.time()
    with _pin_bindings_lock:
        expired = [key for key, value in _pin_bindings.items() if float(value.get("expires_at", 0)) < now]
        for key in expired:
            _pin_bindings.pop(key, None)


def _bind_pin_nonce(pin_id: int, response: Response, request: Request) -> None:
    _purge_expired_pin_bindings()
    nonce = secrets.token_urlsafe(32)
    with _pin_bindings_lock:
        _pin_bindings[nonce] = {
            "pin_id": int(pin_id),
            "expires_at": time.time() + PLEX_PIN_NONCE_TTL_SECONDS,
            "consumed": False,
        }
    response.set_cookie(
        key=PLEX_PIN_NONCE_COOKIE,
        value=nonce,
        httponly=True,
        samesite="lax",
        max_age=PLEX_PIN_NONCE_TTL_SECONDS,
        path="/",
        secure=_cookie_should_be_secure(request),
    )


def _require_pin_nonce(pin_id: int, request: Request, *, consume: bool = False) -> None:
    nonce = (request.cookies.get(PLEX_PIN_NONCE_COOKIE) or "").strip()
    if not nonce:
        raise HTTPException(status_code=401, detail="Plex PIN session cookie missing")
    _purge_expired_pin_bindings()
    with _pin_bindings_lock:
        binding = _pin_bindings.get(nonce)
        if binding is None:
            raise HTTPException(status_code=401, detail="Plex PIN session expired")
        if int(binding.get("pin_id") or -1) != int(pin_id):
            raise HTTPException(status_code=403, detail="Plex PIN does not match login session")
        if binding.get("consumed"):
            raise HTTPException(status_code=409, detail="Plex PIN already consumed")
        if consume:
            binding["consumed"] = True


def clear_pin_nonce_cookie(response: Response, request: Optional[Request] = None) -> None:
    response.delete_cookie(
        key=PLEX_PIN_NONCE_COOKIE,
        path="/",
        secure=_cookie_should_be_secure(request),
    )


def clear_pin_bindings() -> None:
    """Test helper."""
    with _pin_bindings_lock:
        _pin_bindings.clear()


def start_plex_pin_login(request: Request, response: Response) -> dict[str, object]:
    """Create a plex.tv PIN and auth URL for Overseerr-style sign-in."""
    enforce_rate_limit(request, bucket="auth_plex_pin_start", limit=10, window_seconds=60)
    _ensure_plex_login_enabled()
    try:
        pin = create_plex_pin(get_or_create_client_id(_data_dir()))
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not start Plex login: {error}") from error
    _bind_pin_nonce(int(pin["id"]), response, request)
    return {
        "id": pin["id"],
        "code": pin["code"],
        "auth_url": pin["auth_url"],
        "expires_in": pin.get("expires_in"),
        "expires_at": pin.get("expires_at"),
    }


def poll_plex_pin_login(pin_id: int, request: Request, db: Database) -> Optional[CurrentUser]:
    """Poll plex.tv PIN once. Returns CurrentUser when authorized, else None."""
    enforce_rate_limit(request, bucket="auth_plex_pin_poll", limit=60, window_seconds=60)
    _ensure_plex_login_enabled()
    _require_pin_nonce(pin_id, request, consume=False)
    client_id = get_or_create_client_id(_data_dir())
    try:
        pin = fetch_plex_pin(int(pin_id), client_id)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not check Plex login: {error}") from error

    auth_token = pin.get("authToken") or pin.get("auth_token")
    if not auth_token:
        return None
    _require_pin_nonce(pin_id, request, consume=True)
    return authenticate_plex_user(str(auth_token), db)


def authenticate_plex_user(auth_token: str, db: Database) -> CurrentUser:
    settings = _ensure_plex_login_enabled()

    cleaned = str(auth_token or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="auth_token is required")

    try:
        profile = fetch_plex_account(cleaned)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Invalid Plex token") from error

    plex_user_id, display_name, email, avatar_url = _plex_profile_fields(profile)
    existing = db.get_user_by_plex_id(plex_user_id)
    if existing is not None:
        if _user_is_disabled(existing):
            raise HTTPException(status_code=403, detail="This account has been disabled")
        user_id = str(existing["id"])
        role = str(existing["role"])
    else:
        user_id = f"plex-{plex_user_id}"
        role = "owner" if db.count_users_with_plex_id() == 0 else "member"

    seerr_user_id: Optional[int] = None
    seerr_permissions: Optional[int] = None
    try:
        seerr_user_id, seerr_permissions = _bridge_seerr_on_login(settings, cleaned)
    except Exception:
        seerr_user_id = None
        seerr_permissions = None

    if existing is not None and seerr_user_id is None:
        if existing["seerr_user_id"] is not None:
            seerr_user_id = int(existing["seerr_user_id"])
        if existing["seerr_permissions"] is not None:
            seerr_permissions = int(existing["seerr_permissions"])

    user_row = db.upsert_plex_user(
        user_id=user_id,
        display_name=display_name,
        email=email,
        plex_user_id=plex_user_id,
        role=role,
        avatar_url=avatar_url,
        seerr_user_id=seerr_user_id,
        seerr_permissions=seerr_permissions,
    )
    return CurrentUser(
        id=str(user_row["id"]),
        display_name=str(user_row["display_name"]),
        role=str(user_row["role"]),  # type: ignore[arg-type]
        email=user_row.get("email"),
        plex_user_id=user_row.get("plex_user_id"),
        seerr_user_id=user_row.get("seerr_user_id"),
        avatar_url=user_row.get("avatar_url"),
    )


def sync_user_seerr_from_token(user_id: str, auth_token: str, db: Database) -> dict[str, object]:
    settings = _settings()
    config_error = seerr_configuration_error(settings)
    if config_error:
        raise HTTPException(status_code=400, detail=config_error)
    row = db.get_user(user_id)
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    client = SeerrClient(settings.seerr.url, settings.seerr.api_key)
    try:
        payload = client.link_plex_user(auth_token)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(error)) from error
    seerr_user_id = payload.get("id")
    if seerr_user_id is None:
        raise HTTPException(status_code=400, detail="Seerr did not return a user id")
    permissions = payload.get("permissions")
    return db.update_user_seerr(
        user_id,
        seerr_user_id=int(seerr_user_id),
        seerr_permissions=int(permissions) if permissions is not None else None,
    )
