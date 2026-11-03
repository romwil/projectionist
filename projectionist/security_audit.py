"""Owner-visible security audit trail (SEC-012).

One row per meaningful auth or admin action. Rows carry ids, event names, and
changed field *names*. Never secret values, passwords, tokens, or message text.
Writes never raise into the request path.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Mapping, Optional

logger = logging.getLogger(__name__)

SIGN_IN = "sign_in"
SIGN_IN_FAILED = "sign_in_failed"
SIGN_OUT_EVERYWHERE = "sign_out_everywhere"
PASSWORD_CHANGE = "password_change"
PASSWORD_RESET = "password_reset"
INVITE_CREATE = "invite_create"
INVITE_REVOKE = "invite_revoke"
INVITE_REDEEM = "invite_redeem"
ACCESS_REQUEST_APPROVE = "access_request_approve"
ACCESS_REQUEST_DENY = "access_request_deny"
ACCOUNT_CREATE = "account_create"
ROLE_CHANGE = "role_change"
ACCOUNT_DISABLE = "account_disable"
YOUTH_CHANGE = "youth_change"
AUTOCONFIRM_CHANGE = "autoconfirm_change"
AUTOCONFIRM_ADD = "autoconfirm_add"
ACCOUNT_DELETE = "account_delete"
SETTINGS_SAVE = "settings_save"
SECRET_REVEAL = "secret_reveal"
MCP_KEY_ROTATE = "mcp_key_rotate"
MCP_KEY_CLEAR = "mcp_key_clear"
HOUSEHOLD_BACKUP = "household_backup"

AUDIT_EVENTS = (
    SIGN_IN,
    SIGN_IN_FAILED,
    SIGN_OUT_EVERYWHERE,
    PASSWORD_CHANGE,
    PASSWORD_RESET,
    INVITE_CREATE,
    INVITE_REVOKE,
    INVITE_REDEEM,
    ACCESS_REQUEST_APPROVE,
    ACCESS_REQUEST_DENY,
    ACCOUNT_CREATE,
    ROLE_CHANGE,
    ACCOUNT_DISABLE,
    YOUTH_CHANGE,
    AUTOCONFIRM_CHANGE,
    AUTOCONFIRM_ADD,
    ACCOUNT_DELETE,
    SETTINGS_SAVE,
    SECRET_REVEAL,
    MCP_KEY_ROTATE,
    MCP_KEY_CLEAR,
    HOUSEHOLD_BACKUP,
)

_SECRET_HINTS = ("password", "token", "secret", "api_key", "apikey", "credential", "key_value")
_MAX_DETAIL_STR = 200
_MAX_DETAIL_LIST = 40


def _scrub(detail: Mapping[str, Any]) -> Dict[str, Any]:
    clean: Dict[str, Any] = {}
    for key, value in detail.items():
        name = str(key)
        if any(hint in name.lower() for hint in _SECRET_HINTS):
            continue
        if isinstance(value, (list, tuple)):
            clean[name] = [str(v)[:_MAX_DETAIL_STR] for v in list(value)[:_MAX_DETAIL_LIST]]
        elif isinstance(value, (bool, int, float)) or value is None:
            clean[name] = value
        else:
            clean[name] = str(value)[:_MAX_DETAIL_STR]
    return clean


def audit(
    db: Any,
    event: str,
    *,
    actor_id: Optional[str] = None,
    target_id: Optional[str] = None,
    outcome: str = "ok",
    **detail: Any,
) -> None:
    """Record one audit row. Failures are logged and swallowed."""
    try:
        db.record_security_event(
            event,
            actor_id=actor_id,
            target_id=target_id,
            outcome=outcome,
            detail=_scrub(detail),
        )
    except Exception:  # noqa: BLE001
        logger.debug("Security audit write failed for %s", event, exc_info=True)


def changed_setting_names(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    """Dotted names of settings that differ. Names only; values never leave this function."""
    names: list[str] = []

    def _walk(prefix: str, a: Any, b: Any) -> None:
        if isinstance(a, Mapping) and isinstance(b, Mapping):
            for key in sorted(set(a) | set(b)):
                _walk(f"{prefix}.{key}" if prefix else str(key), a.get(key), b.get(key))
            return
        if a != b:
            names.append(prefix)

    _walk("", before, after)
    return names
