"""Live Channels — Tunarr-backed pseudo-live TV managed by Projectionist.

Phase 2: setup certification, preflight, Docker lifecycle, publish starters,
Plex attach checklist, and broadcast health strip. Household "on now" is a
separate surface (guide / Dashboard).
"""

from __future__ import annotations

from projectionist.live_channels.plex_pass import check_plex_pass
from projectionist.live_channels.recipes import (
    ChannelRecipe,
    ProgrammingMode,
    apply_youth_gate_to_items,
)
from projectionist.live_channels.starter_pack import propose_starter_pack
from projectionist.live_channels.status import build_live_channels_status

__all__ = [
    "ChannelRecipe",
    "ProgrammingMode",
    "apply_youth_gate_to_items",
    "build_live_channels_status",
    "check_plex_pass",
    "propose_starter_pack",
]
