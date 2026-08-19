"""SETUP_MODE → ACTIVE_MODE one-way ratchet and cinematic wizard commit."""

from __future__ import annotations

import json
import logging
import secrets
from typing import Any, Dict, Mapping, Optional

from fastapi import HTTPException, Request

from projectionist.config_store import Settings, save_settings
from projectionist.library.db import Database
from projectionist.web.auth import (
    _hash_password,
    has_real_owner,
    row_to_current_user_from_dict,
)
from projectionist.web.ingress import (
    classify_request,
    sanitize_detection_snapshot,
    snapshot_contains_secrets,
)
from projectionist.web.rate_limit import trust_proxy_headers

logger = logging.getLogger(__name__)

SETUP_STATE_KEY = "setup_state"
SETUP_SNAPSHOT_KEY = "ingress_detection_snapshot"
RECOVERY_KEY_HASH_KEY = "recovery_key_hash"
SETUP_STATE_SETUP = "setup"
SETUP_STATE_ACTIVE = "active"

SETUP_API_ALLOWLIST_EXACT = frozenset(
    {
        ("GET", "/api/health"),
        ("GET", "/api/features"),
        ("GET", "/api/setup/handshake"),
        ("POST", "/api/setup/handshake"),
        ("POST", "/api/setup/commit"),
        ("POST", "/api/setup/test/plex"),
        ("POST", "/api/setup/test/tmdb"),
    }
)


def _env_setup_state() -> Optional[str]:
    from projectionist.envcompat import branded_env

    raw = (branded_env("SETUP_STATE") or "").strip().lower()
    if raw in {SETUP_STATE_SETUP, SETUP_STATE_ACTIVE}:
        return raw
    return None


def resolve_setup_state(db: Database) -> str:
    """Return setup | active. Existing households with a real owner skip the wizard."""
    forced = _env_setup_state()
    if forced:
        return forced
    stored = str(db.get_config(SETUP_STATE_KEY) or "").strip().lower()
    if stored == SETUP_STATE_ACTIVE:
        return SETUP_STATE_ACTIVE
    if stored == SETUP_STATE_SETUP:
        if has_real_owner(db):
            db.set_config(SETUP_STATE_KEY, SETUP_STATE_ACTIVE)
            return SETUP_STATE_ACTIVE
        return SETUP_STATE_SETUP
    if has_real_owner(db):
        db.set_config(SETUP_STATE_KEY, SETUP_STATE_ACTIVE)
        return SETUP_STATE_ACTIVE
    db.set_config(SETUP_STATE_KEY, SETUP_STATE_SETUP)
    return SETUP_STATE_SETUP


def is_setup_mode(db: Database) -> bool:
    return resolve_setup_state(db) == SETUP_STATE_SETUP


def is_active_mode(db: Database) -> bool:
    return resolve_setup_state(db) == SETUP_STATE_ACTIVE


def is_setup_public_path(method: str, path: str) -> bool:
    cleaned = (path or "").split("?", 1)[0]
    key = (str(method or "GET").upper(), cleaned)
    return key in SETUP_API_ALLOWLIST_EXACT


def setup_endpoint_locked(path: str) -> bool:
    """True when this path is a SETUP_MODE wizard endpoint that must 404 after commit."""
    cleaned = (path or "").split("?", 1)[0]
    return cleaned in {
        "/api/setup/handshake",
        "/api/setup/commit",
    }


def persist_detection_snapshot(db: Database, snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    sanitized = sanitize_detection_snapshot(snapshot)
    if snapshot_contains_secrets(sanitized):
        logger.error("Refusing to persist ingress snapshot that looks like credentials")
        raise ValueError("Detection snapshot must not contain secrets")
    db.set_config(SETUP_SNAPSHOT_KEY, json.dumps(sanitized, sort_keys=True))
    return sanitized


def load_detection_snapshot(db: Database) -> Optional[Dict[str, Any]]:
    raw = db.get_config(SETUP_SNAPSHOT_KEY)
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return sanitize_detection_snapshot(payload)


def handshake_payload(request: Request, db: Database, *, persist: bool = True) -> Dict[str, Any]:
    classified = classify_request(request)
    snapshot = classified["snapshot"]
    if persist and is_setup_mode(db):
        snapshot = persist_detection_snapshot(db, snapshot)
    else:
        stored = load_detection_snapshot(db)
        if stored:
            snapshot = stored
    halt = bool(classified["halt"])
    message = ""
    if halt:
        message = (
            "Direct public exposure detected on port 8788. "
            "Please complete initial setup via your local network or a trusted tunnel."
        )
    elif classified["classification"] == "public_failsafe":
        message = (
            "This process is reachable through Docker NAT. "
            "We pre-selected Public Household — confirm TLS at your reverse proxy."
        )
    elif classified["classification"] == "proxy":
        message = "We detected a trusted TLS edge proxy. Public Household is recommended."
    else:
        message = "This looks like a private network. You can stay LAN-only or lock down for a public domain."
    return {
        "setup_state": resolve_setup_state(db),
        "classification": classified["classification"],
        "preselect_profile": classified["preselect_profile"],
        "halt": halt,
        "message": message,
        "trusted_proxy": classified["trusted_proxy"],
        "snapshot": snapshot,
        "peer_class": classified["peer_class"],
    }


def resolve_commit_invite_only(profile: str, invite_only: Optional[bool]) -> bool:
    """Public Household is always invite-only. Private defaults off unless opted in."""
    if str(profile or "").strip().lower() == "public":
        return True
    if invite_only is None:
        return False
    return bool(invite_only)


def resolve_commit_trust_proxy(profile: str, trust_proxy: bool) -> bool:
    """Private Household never enables trusted forwarded headers from a leftover true."""
    if str(profile or "").strip().lower() != "public":
        return False
    return bool(trust_proxy)


def resolve_commit_household_domain(profile: str, household_domain: str) -> str:
    """Private Household does not persist a public-path household domain."""
    if str(profile or "").strip().lower() != "public":
        return ""
    return str(household_domain or "").strip()


def _generate_recovery_key() -> str:
    return secrets.token_urlsafe(32)


def commit_setup(
    request: Request,
    db: Database,
    settings: Settings,
    data_dir,
    *,
    profile: str,
    username: str,
    password: str,
    household_domain: str = "",
    trust_proxy: bool = False,
    allow_access_requests: Optional[bool] = None,
    invite_only: Optional[bool] = None,
    plex_pin_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Create the master owner, persist posture, and lock ACTIVE_MODE."""
    if is_active_mode(db):
        raise HTTPException(status_code=404, detail="Not found")

    cleaned_profile = str(profile or "").strip().lower()
    if cleaned_profile not in {"private", "public"}:
        raise HTTPException(status_code=400, detail="Choose Private Household or Public Household")

    resolved_trust_proxy = resolve_commit_trust_proxy(cleaned_profile, trust_proxy)
    resolved_household_domain = resolve_commit_household_domain(cleaned_profile, household_domain)

    # Halt on the real peer. Body profile=public / trust_proxy is not a WAN bypass.
    halt_classified = classify_request(request)
    if halt_classified["halt"]:
        raise HTTPException(
            status_code=403,
            detail=halt_classified.get("message")
            or (
                "Direct public exposure detected on port 8788. "
                "Please complete initial setup via your local network or a trusted tunnel."
            ),
        )

    classified = classify_request(
        request, trusted_proxy=resolved_trust_proxy or trust_proxy_headers()
    )

    name = str(username or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Username must be at least 2 characters")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    if db.get_user_by_display_name(name) is not None:
        raise HTTPException(status_code=409, detail="Username already taken")

    persist_detection_snapshot(db, classified["snapshot"])

    multi_user = True
    resolved_invite_only = resolve_commit_invite_only(cleaned_profile, invite_only)
    resolved_access_requests = (
        True if allow_access_requests is None else bool(allow_access_requests)
    )

    recovery = _generate_recovery_key()
    db.set_config(RECOVERY_KEY_HASH_KEY, _hash_password(recovery))

    user_id = f"local-{secrets.token_hex(12)}"
    user_row = db.create_local_user(
        user_id=user_id,
        display_name=name,
        password_hash=_hash_password(password),
        role="owner",
    )

    settings.features.multi_user_enabled = multi_user
    settings.features.invite_only = resolved_invite_only
    settings.features.open_auto_provision = False
    settings.features.guest_tour_enabled = False
    settings.features.household_profile = cleaned_profile
    settings.features.trust_proxy_headers = resolved_trust_proxy
    settings.features.access_requests_enabled = resolved_access_requests
    settings.auth.local_login_enabled = True
    settings.household_domain = resolved_household_domain
    settings.onboarding_complete = False
    save_settings(data_dir, settings)

    db.set_config(SETUP_STATE_KEY, SETUP_STATE_ACTIVE)

    logger.info(
        "Setup committed profile=%s multi_user=%s invite_only=%s trust_proxy=%s",
        cleaned_profile,
        multi_user,
        resolved_invite_only,
        bool(settings.features.trust_proxy_headers),
    )
    del plex_pin_id  # optional Plex bind is a post-login Settings action

    return {
        "setup_state": SETUP_STATE_ACTIVE,
        "profile": cleaned_profile,
        "recovery_key": recovery,
        "user": row_to_current_user_from_dict(user_row).to_dict(),
        "posture": {
            "multi_user_enabled": multi_user,
            "invite_only": resolved_invite_only,
            "access_requests_enabled": resolved_access_requests,
            "trust_proxy_headers": bool(settings.features.trust_proxy_headers),
            "household_domain": settings.household_domain,
            "classification": classified["classification"],
        },
    }
