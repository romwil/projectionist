"""One authorization policy for REST routes, agent tools, and confirmation tokens.

Every plane that can propose or redeem a fleet action (``/api/actions/*``, the
agent ``ToolRegistry``, ``execute_confirmed_action``) asks this module instead
of keeping its own list. Adding a kind here closes it on all planes at once.

Single-owner mode (``multi_user_enabled`` off) treats every caller as owner,
matching ``require_role``.

An adult member account can carry ``autoconfirm_adds`` (owner-set, off by
default, never on Youth). With it on, that member may propose *and* redeem
Radarr/Sonarr adds; every other owner-only kind stays owner-only.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from projectionist.config_store import Settings

# Pending-action kinds that call Radarr/Sonarr on the owner's credentials to
# acquire a title (SEC-006, PRD-002, BD-3 option 1).
ARR_ACQUIRE_ACTIONS = frozenset({"add_radarr", "add_sonarr"})

# Agent tools that propose ``ARR_ACQUIRE_ACTIONS``.
ARR_ACQUIRE_TOOL_NAMES = frozenset({"add_to_radarr", "add_to_sonarr"})

# Pending-action kinds only an owner may propose or redeem.
OWNER_ONLY_PENDING_ACTIONS = frozenset(
    {
        "remove_arr",
        "mark_bad_media",
        "create_plex_collection",
        "add_to_plex_collection",
    }
    | ARR_ACQUIRE_ACTIONS
)

# Youth accounts never see an acquisition confirm, Seerr included.
YOUTH_BLOCKED_PENDING_ACTIONS = OWNER_ONLY_PENDING_ACTIONS | frozenset({"request_seerr"})

# Agent tools whose REST equivalent requires the owner role, or that change
# *arr / Seerr / Plex state on the owner's credentials.
OWNER_ONLY_TOOL_NAMES = frozenset(
    {
        "add_to_radarr",
        "add_to_sonarr",
        "approve_seerr_request",
        "remove_from_arr",
        "mark_bad_media",
        "create_plex_collection",
        "add_to_plex_collection",
        "suggest_purge_candidates",
    }
)

YOUTH_BLOCKED_TOOL_NAMES = OWNER_ONLY_TOOL_NAMES | frozenset(
    {"request_via_seerr", "propose_acquire_path"}
)

OWNER_ONLY_MESSAGE = "Only the household owner can do that."
ARR_ACQUIRE_MESSAGE = (
    "Only the household owner can add titles to Radarr or Sonarr. Ask them to add it."
)
YOUTH_MESSAGE = "This action is not available on Youth accounts."


def acts_as_owner(settings: Settings, role: Optional[str]) -> bool:
    """True when the caller holds owner capability for fleet actions."""
    if not settings.features.multi_user_enabled:
        return True
    return str(role or "").strip().lower() == "owner"


def autoconfirms_adds(
    settings: Settings,
    *,
    role: Optional[str],
    is_youth: bool,
    account: Optional[Mapping[str, Any]],
) -> bool:
    """True when this adult member's Radarr/Sonarr adds skip the owner's confirm.

    ``account`` is the caller's current user row, read fresh so an owner turning
    the setting off takes effect on the next request. Owners never need it,
    Youth never get it, and single-owner mode has no members.
    """
    if not settings.features.multi_user_enabled or is_youth or not account:
        return False
    if str(role or "").strip().lower() != "member":
        return False
    if str(account.get("role") or "").lower() != "member":
        return False
    if account.get("is_youth") or account.get("disabled"):
        return False
    return bool(account.get("autoconfirm_adds"))


def pending_action_denial(
    kind: Optional[str],
    *,
    is_owner: bool,
    is_youth: bool,
    autoconfirm_adds: bool = False,
) -> Optional[str]:
    """Refusal reason when the caller may not propose or redeem ``kind``, else None."""
    name = str(kind or "")
    if is_youth and name in YOUTH_BLOCKED_PENDING_ACTIONS:
        return YOUTH_MESSAGE
    if not is_owner and autoconfirm_adds and name in ARR_ACQUIRE_ACTIONS:
        return None
    if not is_owner and name in OWNER_ONLY_PENDING_ACTIONS:
        return ARR_ACQUIRE_MESSAGE if name in ARR_ACQUIRE_ACTIONS else OWNER_ONLY_MESSAGE
    return None


def tool_denial(
    name: str, *, is_owner: bool, is_youth: bool, autoconfirm_adds: bool = False
) -> Optional[str]:
    """Refusal reason when the caller may not use agent tool ``name``, else None."""
    if is_youth and name in YOUTH_BLOCKED_TOOL_NAMES:
        return YOUTH_MESSAGE
    if not is_owner and autoconfirm_adds and name in ARR_ACQUIRE_TOOL_NAMES:
        return None
    if not is_owner and name in OWNER_ONLY_TOOL_NAMES:
        if name in ARR_ACQUIRE_TOOL_NAMES:
            return ARR_ACQUIRE_MESSAGE
        return OWNER_ONLY_MESSAGE
    return None


def hidden_tool_names(
    *, is_owner: bool, is_youth: bool, autoconfirm_adds: bool = False
) -> frozenset[str]:
    """Agent tool names omitted from the caller's tool list."""
    hidden: set[str] = set()
    if is_youth:
        hidden |= YOUTH_BLOCKED_TOOL_NAMES
    if not is_owner:
        hidden |= OWNER_ONLY_TOOL_NAMES
        if autoconfirm_adds and not is_youth:
            hidden -= ARR_ACQUIRE_TOOL_NAMES
    return frozenset(hidden)


def caller_autoconfirms_adds(
    db: Any,
    settings: Settings,
    *,
    user_id: Optional[str],
    role: Optional[str],
    is_youth: bool,
) -> bool:
    """``autoconfirms_adds`` for a signed-in caller, reading their row from ``db``."""
    if not user_id or not settings.features.multi_user_enabled:
        return False
    if is_youth or str(role or "").strip().lower() != "member":
        return False
    try:
        row = db.get_user(user_id)
    except Exception:  # noqa: BLE001
        return False
    if row is None:
        return False
    return autoconfirms_adds(settings, role=role, is_youth=is_youth, account=dict(row))
