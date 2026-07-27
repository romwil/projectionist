"""Optional multi-user auth (inactive when features.multi_user_enabled=false).

Supports three authentication methods:
  - **Plex** — PIN-based OAuth flow via plex.tv (original, default).
  - **Local password** — simple username/password stored with salted HMAC hash.
  - **OIDC** — redirect-based OpenID Connect flow for identity providers
    common in homelabs (Authelia, Authentik, Keycloak, etc.).

All three methods produce the same signed session cookie; downstream
middleware is method-agnostic.
"""

from __future__ import annotations

import hashlib
import hmac as _hmac
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional

import httpx
from fastapi import Depends, HTTPException, Request, Response
from starlette.responses import JSONResponse

from projectionist.config_store import Settings, load_merged_settings
from projectionist.connectors.plex_account import (
    create_plex_pin,
    fetch_plex_account,
    fetch_plex_pin,
    get_or_create_client_id,
)
from projectionist.connectors.seerr import SeerrClient
from projectionist.config_store import seerr_configuration_error
from projectionist.library.db import BOOTSTRAP_OWNER_ID, Database
from projectionist.web.rate_limit import enforce_rate_limit
from projectionist.web.session_tokens import (
    DEFAULT_TTL_SECONDS,
    SESSION_COOKIE_NAME,
    create_session_token,
    parse_session_token,
)

_API_AUTH_ALLOWLIST_EXACT = frozenset(
    {
        "/api/health",
        "/api/features",
        "/api/access-requests",
        "/api/guest/tour",
        "/api/invites/validate",
        "/api/invites/redeem/local",
    }
)
_API_AUTH_ALLOWLIST_PREFIXES = ("/api/auth/", "/api/webhooks/", "/mcp")
PLEX_PIN_NONCE_COOKIE = "plex_pin_nonce"
PLEX_PIN_NONCE_TTL_SECONDS = 1800

_pin_bindings_lock = threading.Lock()
_pin_bindings: Dict[str, Dict[str, Any]] = {}

logger = logging.getLogger(__name__)

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
    ui_font_size: str = "medium"
    ui_theme: str = "system"
    is_youth: bool = False
    notification_email: Optional[str] = None
    notify_channel_inbox: bool = True
    notify_channel_email: bool = False
    newsletter_opt_in: bool = False
    nudge_opt_in: bool = False

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
            "ui_font_size": self.ui_font_size or "medium",
            "ui_theme": self.ui_theme or "system",
            "is_youth": self.is_youth,
            "notification_email": self.notification_email,
            "notify_channel_inbox": self.notify_channel_inbox,
            "notify_channel_email": self.notify_channel_email,
            "newsletter_opt_in": self.newsletter_opt_in,
            "nudge_opt_in": self.nudge_opt_in,
        }


_ROLE_RANK = {"guest": 0, "member": 1, "owner": 2}


def row_to_current_user(row) -> CurrentUser:
    from projectionist.web.avatars import resolve_avatar_url

    keys = set(row.keys()) if hasattr(row, "keys") else set()
    avatar_url = None
    if "avatar_url" in keys and row["avatar_url"] is not None:
        avatar_url = str(row["avatar_url"])
    preferred_name = None
    if "preferred_name" in keys and row["preferred_name"] is not None:
        preferred_name = str(row["preferred_name"]).strip() or None
    ui_font_size = "medium"
    if "ui_font_size" in keys and row["ui_font_size"] is not None:
        cleaned = str(row["ui_font_size"]).strip().lower()
        if cleaned in {"small", "medium", "large"}:
            ui_font_size = cleaned
    ui_theme = "system"
    if "ui_theme" in keys and row["ui_theme"] is not None:
        cleaned_theme = str(row["ui_theme"]).strip().lower()
        if cleaned_theme in {"lights_up", "lights_down", "system"}:
            ui_theme = cleaned_theme
    is_youth = bool(int(row["is_youth"])) if "is_youth" in keys and row["is_youth"] is not None else False
    notification_email = None
    if "notification_email" in keys and row["notification_email"] is not None:
        notification_email = str(row["notification_email"]).strip() or None
    notify_channel_inbox = True
    if "notify_channel_inbox" in keys and row["notify_channel_inbox"] is not None:
        notify_channel_inbox = bool(int(row["notify_channel_inbox"]))
    notify_channel_email = False
    if "notify_channel_email" in keys and row["notify_channel_email"] is not None:
        notify_channel_email = bool(int(row["notify_channel_email"]))
    newsletter_opt_in = False
    if "newsletter_opt_in" in keys and row["newsletter_opt_in"] is not None:
        newsletter_opt_in = bool(int(row["newsletter_opt_in"]))
    nudge_opt_in = False
    if "nudge_opt_in" in keys and row["nudge_opt_in"] is not None:
        nudge_opt_in = bool(int(row["nudge_opt_in"]))
    user_id = str(row["id"])
    return CurrentUser(
        id=user_id,
        display_name=str(row["display_name"] or "User"),
        role=str(row["role"]),  # type: ignore[arg-type]
        email=str(row["email"]) if row["email"] is not None else None,
        plex_user_id=str(row["plex_user_id"]) if row["plex_user_id"] is not None else None,
        seerr_user_id=int(row["seerr_user_id"]) if row["seerr_user_id"] is not None else None,
        avatar_url=resolve_avatar_url(user_id, avatar_url),
        preferred_name=preferred_name,
        ui_font_size=ui_font_size,
        ui_theme=ui_theme,
        is_youth=is_youth,
        notification_email=notification_email,
        notify_channel_inbox=notify_channel_inbox,
        notify_channel_email=notify_channel_email,
        newsletter_opt_in=newsletter_opt_in,
        nudge_opt_in=nudge_opt_in,
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


# --- First-owner setup (review finding H2) ------------------------------------------
#
# When multi-user auth is enabled there is a window where the *first* account to
# log in claims the owner role. On a shared LAN a neighbor could race it. Rather
# than a claim code (which risks locking the operator out), Projectionist lets
# the owner credential be injected into the container via environment variables —
# a natural fit for an Unraid CA template field. When set, the owner account is
# seeded up front, so ownership is never up for grabs and the operator always
# holds the credential (no lockout). When unset, the legacy trusted-LAN behavior
# is preserved (first login claims owner).

DEFAULT_OWNER_USERNAME = "owner"
MIN_OWNER_PASSWORD_LENGTH = 8


def resolve_owner_credentials() -> tuple[str, str]:
    """Return (username, password) for the env-injected owner.

    ``password`` is empty when ``PROJECTIONIST_OWNER_PASSWORD`` /
    ``CURATORX_OWNER_PASSWORD`` is not set. The password is never persisted in
    plaintext — only its salted hash lands in the users table when seeded.
    """
    from projectionist.envcompat import branded_env

    username = (branded_env("OWNER_USERNAME") or "").strip() or DEFAULT_OWNER_USERNAME
    password = branded_env("OWNER_PASSWORD") or ""
    return username, password


def env_owner_password_configured() -> bool:
    from projectionist.envcompat import branded_env

    return bool((branded_env("OWNER_PASSWORD") or "").strip())


def has_real_owner(db: Database) -> bool:
    """True when a non-bootstrap account already holds the owner role."""
    return _has_real_owner(db)


def resolve_new_user_role(db: Database) -> str:
    """Role for a brand-new account.

    ``member`` when a real owner already exists (e.g. an env-seeded owner);
    otherwise ``owner`` (legacy trusted-LAN first-login behavior).
    """
    return "member" if has_real_owner(db) else "owner"


def seed_env_owner(db: Database) -> Optional[str]:
    """Ensure the env-injected owner account exists; return its user id or None.

    Idempotent and safe to call on every startup and whenever multi-user is
    enabled. Keeps the injected credential authoritative for the owner account
    (so rotating ``PROJECTIONIST_OWNER_PASSWORD`` and restarting resets the
    password — a recovery path that avoids lockout). Never clobbers a different
    existing owner.
    """
    username, password = resolve_owner_credentials()
    if not password:
        return None
    if len(password) < MIN_OWNER_PASSWORD_LENGTH:
        logger.warning(
            "PROJECTIONIST_OWNER_PASSWORD is set but shorter than %d characters; "
            "refusing to seed a weak owner.",
            MIN_OWNER_PASSWORD_LENGTH,
        )
        return None

    existing = db.get_user_by_display_name(username)
    if existing is not None:
        user_id = str(existing["id"])
        changed = False
        if str(existing["role"]) != "owner":
            db.update_user_role(user_id, "owner")
            changed = True
        stored_hash = existing["password_hash"] if "password_hash" in existing.keys() else None
        if not _verify_password(password, str(stored_hash or "")):
            db.update_user_password(user_id, _hash_password(password))
            changed = True
        if changed:
            logger.info("Owner account '%s' updated from PROJECTIONIST_OWNER_PASSWORD.", username)
        return user_id

    if has_real_owner(db):
        logger.warning(
            "PROJECTIONIST_OWNER_PASSWORD is set but a different owner already exists; "
            "skipping seed of '%s'.",
            username,
        )
        return None

    user_id = f"local-{secrets.token_hex(12)}"
    db.create_local_user(
        user_id=user_id,
        display_name=username,
        password_hash=_hash_password(password),
        role="owner",
    )
    logger.info("Seeded owner account '%s' from PROJECTIONIST_OWNER_PASSWORD.", username)
    return user_id


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

    from projectionist.web.jobs import get_job_manager

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
    from projectionist.web.jobs import get_job_manager

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


def _bind_pin_nonce(
    pin_id: int,
    response: Response,
    request: Request,
    *,
    invite_token: Optional[str] = None,
) -> None:
    _purge_expired_pin_bindings()
    nonce = secrets.token_urlsafe(32)
    binding: Dict[str, Any] = {
        "pin_id": int(pin_id),
        "expires_at": time.time() + PLEX_PIN_NONCE_TTL_SECONDS,
        "consumed": False,
    }
    cleaned_invite = str(invite_token or "").strip()
    if cleaned_invite:
        binding["invite_token"] = cleaned_invite
    with _pin_bindings_lock:
        _pin_bindings[nonce] = binding
    response.set_cookie(
        key=PLEX_PIN_NONCE_COOKIE,
        value=nonce,
        httponly=True,
        samesite="lax",
        max_age=PLEX_PIN_NONCE_TTL_SECONDS,
        path="/",
        secure=_cookie_should_be_secure(request),
    )


def _require_pin_nonce(pin_id: int, request: Request, *, consume: bool = False) -> Optional[str]:
    """Validate PIN nonce; return optional invite_token stored on the binding."""
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
        invite_token = str(binding.get("invite_token") or "").strip() or None
        if consume:
            binding["consumed"] = True
    return invite_token


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


def start_plex_pin_login(
    request: Request,
    response: Response,
    *,
    invite_token: Optional[str] = None,
) -> dict[str, object]:
    """Create a plex.tv PIN and auth URL for Overseerr-style sign-in."""
    enforce_rate_limit(request, bucket="auth_plex_pin_start", limit=10, window_seconds=60)
    _ensure_plex_login_enabled()
    try:
        pin = create_plex_pin(get_or_create_client_id(_data_dir()))
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not start Plex login: {error}") from error
    _bind_pin_nonce(int(pin["id"]), response, request, invite_token=invite_token)
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
    invite_token = _require_pin_nonce(pin_id, request, consume=False)
    client_id = get_or_create_client_id(_data_dir())
    try:
        pin = fetch_plex_pin(int(pin_id), client_id)
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Could not check Plex login: {error}") from error

    auth_token = pin.get("authToken") or pin.get("auth_token")
    if not auth_token:
        return None
    invite_token = _require_pin_nonce(pin_id, request, consume=True)
    return authenticate_plex_user(str(auth_token), db, invite_token=invite_token)


def _has_real_owner(db: Database) -> bool:
    """True when a non-bootstrap owner exists (Plex / local / OIDC household owner)."""
    for user in db.list_users(limit=200):
        if user.get("role") != "owner":
            continue
        if str(user.get("id") or "") == BOOTSTRAP_OWNER_ID:
            continue
        return True
    return False


def authenticate_plex_user(
    auth_token: str,
    db: Database,
    *,
    invite_token: Optional[str] = None,
) -> CurrentUser:
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
    invite_for_new = None
    if existing is not None:
        if _user_is_disabled(existing):
            raise HTTPException(status_code=403, detail="This account has been disabled")
        user_id = str(existing["id"])
        role = str(existing["role"])
    else:
        user_id = f"plex-{plex_user_id}"
        # First real household owner bootstraps regardless of invite-only
        # (bootstrap-owner alone does not count).
        if not _has_real_owner(db):
            role = "owner"
            invite_for_new = None
        else:
            from projectionist.invites import assert_identity_not_denied, require_invite_or_open

            try:
                assert_identity_not_denied(db, email=email, plex_user_id=plex_user_id)
            except ValueError as error:
                raise HTTPException(status_code=403, detail=str(error)) from error

            try:
                invite_for_new = require_invite_or_open(
                    settings, db, raw_token=invite_token, method="plex"
                )
            except ValueError as error:
                raise HTTPException(status_code=403, detail=str(error)) from error

            if invite_for_new is not None:
                role = str(invite_for_new["role"])
            else:
                role = "member"

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

    # Prefer an existing local upload over re-pointing at a brittle Plex CDN URL.
    from projectionist.web.avatars import (
        cache_remote_avatar,
        find_local_avatar_file,
        local_avatar_api_path,
        resolve_avatar_url,
    )

    stored_avatar = avatar_url
    if find_local_avatar_file(user_id):
        stored_avatar = local_avatar_api_path(user_id)
    elif avatar_url:
        cached = cache_remote_avatar(user_id, avatar_url)
        if cached:
            stored_avatar = cached

    if existing is None and invite_for_new is not None and role != "owner":
        from projectionist.invites import provision_from_invite

        try:
            provisioned = provision_from_invite(
                db,
                settings,
                invite=invite_for_new,
                method="plex",
                user_id=user_id,
                display_name=display_name,
                email=email,
                plex_user_id=plex_user_id,
                avatar_url=stored_avatar,
                seerr_user_id=seerr_user_id,
                seerr_permissions=seerr_permissions,
            )
            user_row = provisioned["user"]
        except ValueError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error
    else:
        user_row = db.upsert_plex_user(
            user_id=user_id,
            display_name=display_name,
            email=email,
            plex_user_id=plex_user_id,
            role=role,
            avatar_url=stored_avatar,
            seerr_user_id=seerr_user_id,
            seerr_permissions=seerr_permissions,
        )
    try:
        from projectionist.watchlist.crypto import encrypt_plex_token
        from projectionist.watchlist.plex_sync import maybe_pull_on_login

        db.set_user_plex_token_enc(str(user_row["id"]), encrypt_plex_token(cleaned))
        maybe_pull_on_login(db, settings, user_id=str(user_row["id"]))
    except Exception:
        logger.debug("Could not persist/sync Plex watchlist token", exc_info=True)
    resolved_avatar = resolve_avatar_url(str(user_row["id"]), user_row.get("avatar_url"))
    return CurrentUser(
        id=str(user_row["id"]),
        display_name=str(user_row["display_name"]),
        role=str(user_row["role"]),  # type: ignore[arg-type]
        email=user_row.get("email"),
        plex_user_id=user_row.get("plex_user_id"),
        seerr_user_id=user_row.get("seerr_user_id"),
        avatar_url=resolved_avatar,
        is_youth=bool(user_row.get("is_youth", False)),
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


# ---------------------------------------------------------------------------
# Local password auth
# ---------------------------------------------------------------------------

_PASSWORD_HASH_ITERATIONS = 600_000
_PASSWORD_SALT_BYTES = 32


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Derive a salted password hash using PBKDF2-HMAC-SHA256.

    Returns ``<hex-salt>$<hex-hash>`` — constant-time comparison is used on
    verification so timing attacks against the hash are not practical.
    """
    if salt is None:
        salt = secrets.token_bytes(_PASSWORD_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PASSWORD_HASH_ITERATIONS,
    )
    return f"{salt.hex()}${derived.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    """Constant-time verification of a password against a stored hash."""
    if "$" not in stored_hash:
        return False
    salt_hex, expected_hex = stored_hash.split("$", 1)
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _PASSWORD_HASH_ITERATIONS,
    )
    return _hmac.compare_digest(derived.hex(), expected_hex)


def _ensure_local_login_enabled() -> Settings:
    settings = _settings()
    if not settings.features.multi_user_enabled:
        raise HTTPException(status_code=400, detail="Multi-user auth is not enabled")
    # An env-injected owner credential implies local login for that account, so
    # a bare Unraid CA setup (owner password only) works without also toggling
    # the local-login flag.
    if not settings.auth.local_login_enabled and not env_owner_password_configured():
        raise HTTPException(status_code=400, detail="Local password login is not enabled")
    return settings


def _count_local_users(db: Database) -> int:
    """Count users created via local-password auth (excludes bootstrap owner)."""
    users = db.list_users(limit=200)
    return sum(1 for u in users if u.get("auth_method") == "local")


def register_local_user(
    *,
    username: str,
    password: str,
    db: Database,
    requesting_user: Optional[CurrentUser] = None,
) -> CurrentUser:
    """Create a local-password account.

    Rules:
      - While ownership is unclaimed (no real owner yet) anyone may register a
        bootstrap account with no session. Whether it becomes ``owner`` follows
        the owner-existence gate (legacy first-user-is-owner, unless an owner
        has already been seeded — e.g. via ``PROJECTIONIST_OWNER_PASSWORD``).
      - Once a real owner exists, only that owner can create further accounts.
    """
    _ensure_local_login_enabled()

    username = username.strip()
    if not username or len(username) < 2:
        raise HTTPException(status_code=400, detail="Username must be at least 2 characters")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    existing = db.get_user_by_display_name(username)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Username already taken")

    if has_real_owner(db):
        if requesting_user is None or requesting_user.role != "owner":
            raise HTTPException(status_code=403, detail="Only the owner can create local accounts")

    role = resolve_new_user_role(db)
    user_id = f"local-{secrets.token_hex(12)}"
    password_hash = _hash_password(password)

    user_row = db.create_local_user(
        user_id=user_id,
        display_name=username,
        password_hash=password_hash,
        role=role,
    )
    return row_to_current_user_from_dict(user_row)


def authenticate_local_user(
    *,
    username: str,
    password: str,
    db: Database,
    request: Request,
) -> CurrentUser:
    """Validate credentials and return the authenticated user."""
    enforce_rate_limit(request, bucket="auth_local_login", limit=10, window_seconds=60)
    _ensure_local_login_enabled()

    row = db.get_user_by_display_name(username.strip())
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if _user_is_disabled(row):
        raise HTTPException(status_code=403, detail="This account has been disabled")

    stored_hash = row["password_hash"]
    if not stored_hash or not _verify_password(password, str(stored_hash)):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return row_to_current_user(row)


def row_to_current_user_from_dict(d: dict) -> CurrentUser:
    """Build CurrentUser from a dict (as returned by db._row_to_user)."""
    font = str(d.get("ui_font_size") or "medium").strip().lower()
    if font not in {"small", "medium", "large"}:
        font = "medium"
    theme = str(d.get("ui_theme") or "system").strip().lower()
    if theme not in {"lights_up", "lights_down", "system"}:
        theme = "system"
    return CurrentUser(
        id=str(d["id"]),
        display_name=str(d.get("display_name") or "User"),
        role=str(d.get("role", "member")),  # type: ignore[arg-type]
        email=d.get("email"),
        plex_user_id=d.get("plex_user_id"),
        seerr_user_id=d.get("seerr_user_id"),
        avatar_url=d.get("avatar_url"),
        preferred_name=d.get("preferred_name"),
        ui_font_size=font,
        ui_theme=theme,
        is_youth=bool(d.get("is_youth", False)),
    )


# ---------------------------------------------------------------------------
# OIDC auth
# ---------------------------------------------------------------------------

_oidc_state_lock = threading.Lock()
_oidc_states: Dict[str, Dict[str, Any]] = {}
OIDC_STATE_TTL_SECONDS = 600


def _ensure_oidc_enabled() -> Settings:
    settings = _settings()
    if not settings.features.multi_user_enabled:
        raise HTTPException(status_code=400, detail="Multi-user auth is not enabled")
    if not settings.auth.oidc_enabled:
        raise HTTPException(status_code=400, detail="OIDC login is not enabled")
    if not settings.auth.oidc_issuer_url or not settings.auth.oidc_client_id:
        raise HTTPException(status_code=400, detail="OIDC is not fully configured")
    return settings


def _oidc_discovery_url(issuer: str) -> str:
    return issuer.rstrip("/") + "/.well-known/openid-configuration"


def _purge_expired_oidc_states() -> None:
    now = time.time()
    with _oidc_state_lock:
        expired = [k for k, v in _oidc_states.items() if float(v.get("expires_at", 0)) < now]
        for k in expired:
            _oidc_states.pop(k, None)


def clear_oidc_states() -> None:
    """Test helper."""
    with _oidc_state_lock:
        _oidc_states.clear()


def start_oidc_authorize(
    request: Request,
    *,
    invite_token: Optional[str] = None,
) -> dict[str, str]:
    """Build the OIDC authorization redirect URL with a CSRF state parameter."""
    enforce_rate_limit(request, bucket="auth_oidc_start", limit=10, window_seconds=60)
    settings = _ensure_oidc_enabled()

    discovery_url = _oidc_discovery_url(settings.auth.oidc_issuer_url)
    try:
        disc = httpx.get(discovery_url, timeout=10).json()
    except Exception as error:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Could not fetch OIDC discovery document: {error}",
        ) from error

    authorization_endpoint = disc.get("authorization_endpoint", "")
    if not authorization_endpoint:
        raise HTTPException(status_code=502, detail="OIDC discovery missing authorization_endpoint")

    state = secrets.token_urlsafe(32)
    _purge_expired_oidc_states()
    state_payload: Dict[str, Any] = {
        "expires_at": time.time() + OIDC_STATE_TTL_SECONDS,
        "token_endpoint": disc.get("token_endpoint", ""),
        "userinfo_endpoint": disc.get("userinfo_endpoint", ""),
    }
    cleaned_invite = str(invite_token or "").strip()
    if cleaned_invite:
        state_payload["invite_token"] = cleaned_invite
    with _oidc_state_lock:
        _oidc_states[state] = state_payload

    redirect_uri = settings.auth.oidc_redirect_uri or ""
    params = (
        f"?response_type=code"
        f"&client_id={settings.auth.oidc_client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&scope=openid%20profile%20email"
        f"&state={state}"
    )
    return {"authorize_url": authorization_endpoint + params, "state": state}


def handle_oidc_callback(
    *,
    code: str,
    state: str,
    db: Database,
    request: Request,
) -> CurrentUser:
    """Exchange the authorization code for tokens, resolve user identity."""
    enforce_rate_limit(request, bucket="auth_oidc_callback", limit=10, window_seconds=60)
    settings = _ensure_oidc_enabled()

    _purge_expired_oidc_states()
    with _oidc_state_lock:
        state_data = _oidc_states.pop(state, None)

    if state_data is None:
        raise HTTPException(status_code=401, detail="Invalid or expired OIDC state")

    token_endpoint = state_data.get("token_endpoint", "")
    userinfo_endpoint = state_data.get("userinfo_endpoint", "")
    invite_token = str(state_data.get("invite_token") or "").strip() or None

    if not token_endpoint:
        raise HTTPException(status_code=502, detail="OIDC token endpoint unknown")

    redirect_uri = settings.auth.oidc_redirect_uri or ""
    try:
        token_resp = httpx.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": settings.auth.oidc_client_id,
                "client_secret": settings.auth.oidc_client_secret,
            },
            timeout=10,
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="OIDC token exchange failed") from error

    access_token = token_data.get("access_token", "")
    if not access_token:
        raise HTTPException(status_code=502, detail="OIDC token response missing access_token")

    if not userinfo_endpoint:
        raise HTTPException(status_code=502, detail="OIDC userinfo endpoint unknown")

    try:
        userinfo_resp = httpx.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()
    except Exception as error:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="Failed to fetch OIDC user info") from error

    sub = str(userinfo.get("sub") or "").strip()
    if not sub:
        raise HTTPException(status_code=502, detail="OIDC user info missing sub claim")

    display_name = str(
        userinfo.get("preferred_username")
        or userinfo.get("name")
        or userinfo.get("email")
        or sub
    ).strip()
    email = userinfo.get("email")
    email_str = str(email) if email else None

    existing = db.get_user_by_oidc_sub(sub)
    if existing is not None:
        if _user_is_disabled(existing):
            raise HTTPException(status_code=403, detail="This account has been disabled")
        return row_to_current_user(existing)

    from projectionist.invites import (
        assert_identity_not_denied,
        provision_from_invite,
        require_invite_or_open,
    )

    if db.count_users_with_role("owner") == 0 or not _has_real_owner(db):
        user_row = db.upsert_oidc_user(
            oidc_sub=sub,
            display_name=display_name,
            email=email_str,
            role="owner",
        )
        return row_to_current_user_from_dict(user_row)

    try:
        assert_identity_not_denied(db, email=email_str, oidc_sub=sub)
    except ValueError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error

    try:
        invite_for_new = require_invite_or_open(
            settings, db, raw_token=invite_token, method="oidc"
        )
    except ValueError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error

    if invite_for_new is not None:
        try:
            provisioned = provision_from_invite(
                db,
                settings,
                invite=invite_for_new,
                method="oidc",
                user_id=f"oidc-{sub}",
                display_name=display_name,
                email=email_str,
                oidc_sub=sub,
            )
            return row_to_current_user_from_dict(provisioned["user"])
        except ValueError as error:
            raise HTTPException(status_code=403, detail=str(error)) from error

    user_row = db.upsert_oidc_user(
        oidc_sub=sub,
        display_name=display_name,
        email=email_str,
        role="member",
    )
    return row_to_current_user_from_dict(user_row)


def available_auth_methods(settings: Settings) -> List[str]:
    """Return the list of configured auth methods for the features endpoint."""
    methods: List[str] = []
    if settings.auth.plex_login_enabled:
        methods.append("plex")
    if settings.auth.local_login_enabled:
        methods.append("local")
    if settings.auth.oidc_enabled and settings.auth.oidc_issuer_url and settings.auth.oidc_client_id:
        methods.append("oidc")
    return methods
