"""Bidirectional CuratorX pin ↔ Plex Discover watchlist sync."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Mapping, Optional

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.watchlist.crypto import decrypt_plex_token
from curatorx.watchlist import plex_discover

logger = logging.getLogger(__name__)


def resolve_account_token(
    db: Database,
    settings: Settings,
    *,
    user_id: Optional[str],
) -> Dict[str, Any]:
    """Resolve the Discover account token for a user.

    Prefer encrypted Sign-in-with-Plex token. Fall back to server ``plex_token``
    only when multi-user is off (may not match the intended Discover account).
    """
    resolved_user_id = user_id
    if resolved_user_id is None:
        users = db.list_users(limit=1)
        resolved_user_id = users[0]["id"] if users else None

    token = None
    source = None
    if resolved_user_id:
        enc = db.get_user_plex_token_enc(str(resolved_user_id))
        token = decrypt_plex_token(enc)
        if token:
            source = "plex_token_enc"

    if not token and not settings.features.multi_user_enabled:
        fallback = str(settings.plex_token or "").strip()
        if fallback:
            token = fallback
            source = "server_plex_token"

    return {
        "user_id": resolved_user_id,
        "token": token,
        "source": source,
        "has_account_token": source == "plex_token_enc",
    }


def get_watchlist_sync_status(
    db: Database,
    settings: Settings,
    *,
    user_id: Optional[str],
) -> Dict[str, Any]:
    resolved = resolve_account_token(db, settings, user_id=user_id)
    scoped_id = resolved.get("user_id")
    prefs = db.get_watchlist_sync_prefs(scoped_id) if scoped_id else {}
    enabled = bool(prefs.get("watchlist_sync_enabled", True))
    pull_on_login = bool(prefs.get("watchlist_pull_on_login", True))
    push_on_pin = bool(prefs.get("watchlist_push_on_pin", True))
    last_synced_at = prefs.get("watchlist_last_synced_at")
    token_ok = bool(resolved.get("token"))
    message = None
    if not token_ok:
        message = "Re-sign in with Plex to sync your Discover watchlist."
    elif resolved.get("source") == "server_plex_token":
        message = (
            "Using the server Plex token. Prefer Sign in with Plex so sync uses your "
            "personal Discover watchlist."
        )
    return {
        "enabled": enabled,
        "pull_on_login": pull_on_login,
        "push_on_pin": push_on_pin,
        "last_synced_at": last_synced_at,
        "has_plex_token": token_ok,
        "has_account_token": bool(resolved.get("has_account_token")),
        "token_source": resolved.get("source"),
        "message": message,
        "bidirectional": True,
        "limitations": [
            "Push requires titles to resolve on Plex Discover (TMDB/TVDB match).",
            "Server library plex_token is not reliable for Discover watchlist when accounts differ.",
            "Named Plex Lists are out of scope (separate from watchlist).",
        ],
    }


def update_watchlist_sync_settings(
    db: Database,
    *,
    user_id: Optional[str],
    enabled: Optional[bool] = None,
    pull_on_login: Optional[bool] = None,
    push_on_pin: Optional[bool] = None,
) -> Dict[str, Any]:
    if not user_id:
        raise ValueError("user_id is required for watchlist sync settings")
    return db.update_watchlist_sync_prefs(
        user_id,
        enabled=enabled,
        pull_on_login=pull_on_login,
        push_on_pin=push_on_pin,
    )


def sync_watchlist_with_plex(
    db: Database,
    settings: Settings,
    *,
    user_id: Optional[str],
    direction: str = "both",
) -> Dict[str, Any]:
    """Pull from Plex and/or push local-only pins.

    ``direction``: ``both`` | ``pull`` | ``push``
    """
    status = get_watchlist_sync_status(db, settings, user_id=user_id)
    if not status["enabled"]:
        return {**status, "ok": False, "reason": "disabled", "pulled": 0, "pushed": 0, "errors": []}
    resolved = resolve_account_token(db, settings, user_id=user_id)
    token = resolved.get("token")
    # Multi-user pins are scoped to the caller; single-user pins use NULL.
    scoped_id = user_id if settings.features.multi_user_enabled else None

    if not token:
        return {
            **status,
            "ok": False,
            "reason": "missing_token",
            "pulled": 0,
            "pushed": 0,
            "errors": ["missing_token"],
        }

    pulled = 0
    pushed = 0
    errors: list[str] = []
    mode = (direction or "both").strip().lower()

    if mode in {"both", "pull"}:
        try:
            remote = plex_discover.fetch_watchlist(token)
        except Exception as error:  # noqa: BLE001
            logger.warning("Watchlist pull failed: %s", error)
            errors.append(f"pull:{error}")
            remote = []
        for item in remote:
            try:
                db.add_watchlist_pin(
                    pin_id=str(uuid.uuid4()),
                    user_id=scoped_id,
                    tmdb_id=item.get("tmdb_id"),
                    tvdb_id=item.get("tvdb_id"),
                    media_type=str(item["media_type"]),
                    title=str(item["title"]),
                    plex_rating_key=item.get("plex_rating_key"),
                )
                pulled += 1
            except ValueError:
                continue
            except Exception as error:  # noqa: BLE001
                errors.append(f"pull_item:{error}")

    if mode in {"both", "push"} and status.get("push_on_pin", True):
        local_pins = db.list_watchlist_pins(user_id=scoped_id)
        try:
            remote_keys = {
                str(item.get("plex_rating_key") or "")
                for item in plex_discover.fetch_watchlist(token)
                if item.get("plex_rating_key")
            }
        except Exception:  # noqa: BLE001
            remote_keys = set()
        for pin in local_pins:
            key = pin.get("plex_rating_key")
            if key and key in remote_keys:
                continue
            result = push_pin_to_plex(db, settings, pin, user_id=user_id, token=token)
            if result.get("synced"):
                pushed += 1
            elif result.get("reason") and result["reason"] not in {"disabled", "push_disabled"}:
                errors.append(f"push:{result.get('reason')}")

    stamp_user = resolved.get("user_id") or user_id
    if stamp_user:
        db.mark_watchlist_synced(stamp_user)

    return {
        **get_watchlist_sync_status(db, settings, user_id=user_id),
        "ok": not errors or pulled > 0 or pushed > 0,
        "reason": None if not errors else "partial",
        "pulled": pulled,
        "pushed": pushed,
        "errors": errors[:20],
    }


def push_pin_to_plex(
    db: Database,
    settings: Settings,
    pin: Mapping[str, Any],
    *,
    user_id: Optional[str],
    token: Optional[str] = None,
) -> Dict[str, Any]:
    status = get_watchlist_sync_status(db, settings, user_id=user_id)
    if not status["enabled"] or not status.get("push_on_pin", True):
        return {"synced": False, "reason": "push_disabled"}
    resolved = resolve_account_token(db, settings, user_id=user_id)
    account_token = token or resolved.get("token")
    if not account_token:
        return {"synced": False, "reason": "missing_token"}

    rating_key = pin.get("plex_rating_key")
    if not rating_key:
        rating_key = plex_discover.resolve_discover_rating_key(
            account_token,
            title=str(pin.get("title") or ""),
            media_type=str(pin.get("media_type") or "movie"),
            tmdb_id=pin.get("tmdb_id"),
            tvdb_id=pin.get("tvdb_id"),
        )
        if rating_key and pin.get("id"):
            db.set_watchlist_pin_plex_rating_key(str(pin["id"]), rating_key)
    if not rating_key:
        return {"synced": False, "reason": "unresolved_discover_id"}
    try:
        plex_discover.add_to_watchlist(account_token, rating_key)
    except Exception as error:  # noqa: BLE001
        logger.info("Push watchlist pin failed: %s", error)
        return {"synced": False, "reason": "plex_error", "detail": str(error)}
    return {"synced": True, "plex_rating_key": rating_key}


def remove_pin_from_plex(
    db: Database,
    settings: Settings,
    pin: Mapping[str, Any],
    *,
    user_id: Optional[str],
) -> Dict[str, Any]:
    status = get_watchlist_sync_status(db, settings, user_id=user_id)
    if not status["enabled"] or not status.get("push_on_pin", True):
        return {"synced": False, "reason": "push_disabled"}
    resolved = resolve_account_token(db, settings, user_id=user_id)
    token = resolved.get("token")
    if not token:
        return {"synced": False, "reason": "missing_token"}
    rating_key = pin.get("plex_rating_key")
    if not rating_key:
        rating_key = plex_discover.resolve_discover_rating_key(
            token,
            title=str(pin.get("title") or ""),
            media_type=str(pin.get("media_type") or "movie"),
            tmdb_id=pin.get("tmdb_id"),
            tvdb_id=pin.get("tvdb_id"),
        )
    if not rating_key:
        return {"synced": False, "reason": "unresolved_discover_id"}
    try:
        plex_discover.remove_from_watchlist(token, rating_key)
    except Exception as error:  # noqa: BLE001
        logger.info("Remove watchlist pin from Plex failed: %s", error)
        return {"synced": False, "reason": "plex_error", "detail": str(error)}
    return {"synced": True, "plex_rating_key": rating_key}


def maybe_pull_on_login(db: Database, settings: Settings, *, user_id: str) -> None:
    prefs = db.get_watchlist_sync_prefs(user_id)
    if not prefs.get("watchlist_sync_enabled", True) or not prefs.get("watchlist_pull_on_login", True):
        return
    try:
        sync_watchlist_with_plex(db, settings, user_id=user_id, direction="pull")
    except Exception:  # noqa: BLE001
        logger.debug("Watchlist pull-on-login failed for user=%s", user_id, exc_info=True)
