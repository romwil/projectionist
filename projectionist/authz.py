"""One authorization policy for REST routes, agent tools, and confirmation tokens.

Every plane that can propose or redeem a fleet action (``/api/actions/*``, the
agent ``ToolRegistry``, ``execute_confirmed_action``) asks this module instead
of keeping its own list. Adding a kind here closes it on all planes at once.

Single-owner mode (``multi_user_enabled`` off) treats every caller as owner,
matching ``require_role``.
"""

from __future__ import annotations

from typing import Optional

from projectionist.config_store import Settings

# Pending-action kinds that call Radarr/Sonarr on the owner's credentials to
# acquire a title (SEC-006, PRD-002, BD-3 option 1).
ARR_ACQUIRE_ACTIONS = frozenset({"add_radarr", "add_sonarr"})

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


def pending_action_denial(
    kind: Optional[str],
    *,
    is_owner: bool,
    is_youth: bool,
) -> Optional[str]:
    """Refusal reason when the caller may not propose or redeem ``kind``, else None."""
    name = str(kind or "")
    if is_youth and name in YOUTH_BLOCKED_PENDING_ACTIONS:
        return YOUTH_MESSAGE
    if not is_owner and name in OWNER_ONLY_PENDING_ACTIONS:
        return ARR_ACQUIRE_MESSAGE if name in ARR_ACQUIRE_ACTIONS else OWNER_ONLY_MESSAGE
    return None


def tool_denial(name: str, *, is_owner: bool, is_youth: bool) -> Optional[str]:
    """Refusal reason when the caller may not use agent tool ``name``, else None."""
    if is_youth and name in YOUTH_BLOCKED_TOOL_NAMES:
        return YOUTH_MESSAGE
    if not is_owner and name in OWNER_ONLY_TOOL_NAMES:
        if name in {"add_to_radarr", "add_to_sonarr"}:
            return ARR_ACQUIRE_MESSAGE
        return OWNER_ONLY_MESSAGE
    return None


def hidden_tool_names(*, is_owner: bool, is_youth: bool) -> frozenset[str]:
    """Agent tool names omitted from the caller's tool list."""
    hidden: set[str] = set()
    if is_youth:
        hidden |= YOUTH_BLOCKED_TOOL_NAMES
    if not is_owner:
        hidden |= OWNER_ONLY_TOOL_NAMES
    return frozenset(hidden)
