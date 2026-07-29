"""Plex Pass / Live TV entitlement preflight (honest stub).

Plex does not expose a stable, documented “has Plex Pass” flag on the local
Media Server ``identity`` response. Machine identifier alone is insufficient.
Until we have a reliable signal (or owner confirmation in the wizard), this
module returns structured ``unknown`` rather than inventing a Pass API.
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Mapping, Optional

PlexPassStatus = Literal["unknown", "confirmed", "missing"]


def check_plex_pass(
    *,
    settings: Any = None,
    plex_client: Any = None,
    owner_confirmed: Optional[bool] = None,
) -> Dict[str, Any]:
    """Return ``{status, message, ...}`` for wizard preflight.

    - ``owner_confirmed=True`` → ``confirmed`` (explicit wizard checkbox)
    - ``owner_confirmed=False`` → ``missing``
    - otherwise → ``unknown`` (machine-id / server identity is not enough)
    """
    machine_id = ""
    friendly_name = ""
    if plex_client is not None and hasattr(plex_client, "server_identity"):
        try:
            machine_id, friendly_name = plex_client.server_identity()
        except Exception:  # noqa: BLE001
            machine_id, friendly_name = "", ""
    elif settings is not None:
        # Best-effort: only prove Plex is configured, not Pass entitlement.
        url = str(getattr(settings, "plex_url", "") or "").strip()
        token = str(getattr(settings, "plex_token", "") or "").strip()
        if not url or not token:
            return {
                "status": "unknown",
                "message": (
                    "Plex is not configured yet. Live TV / DVR in Plex typically "
                    "requires an active Plex Pass — confirm in the enable wizard."
                ),
                "machine_id": "",
                "friendly_name": "",
                "detection": "not_configured",
            }

    if owner_confirmed is True:
        return {
            "status": "confirmed",
            "message": "Owner confirmed Plex Pass / Live TV entitlement.",
            "machine_id": machine_id,
            "friendly_name": friendly_name,
            "detection": "owner_confirm",
        }
    if owner_confirmed is False:
        return {
            "status": "missing",
            "message": (
                "Owner indicated Plex Pass is not available. Live Channels needs "
                "Plex Live TV (Plex Pass) to attach the Tunarr tuner."
            ),
            "machine_id": machine_id,
            "friendly_name": friendly_name,
            "detection": "owner_confirm",
        }

    return {
        "status": "unknown",
        "message": (
            "Projectionist cannot verify Plex Pass from the server machine id alone. "
            "Confirm you have an active Plex Pass (Live TV / DVR) in the enable wizard."
        ),
        "machine_id": machine_id,
        "friendly_name": friendly_name,
        "detection": "unavailable",
    }


def plex_pass_from_mapping(data: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize a stored preflight record."""
    status = str(data.get("status") or "unknown").lower()
    if status not in {"unknown", "confirmed", "missing"}:
        status = "unknown"
    return {
        "status": status,
        "message": str(data.get("message") or ""),
        "machine_id": str(data.get("machine_id") or ""),
        "friendly_name": str(data.get("friendly_name") or ""),
        "detection": str(data.get("detection") or ""),
    }
