"""Live Channels — Tunarr-backed pseudo-live TV managed by Projectionist.

Owner path: flag + preflight + Docker lifecycle + craft/publish (starters,
custom recipes, collections) + manage/refill/delete + Plex attach. Household
"on now" is a separate surface (guide / Dashboard).
"""

from __future__ import annotations

from projectionist.live_channels.craft import build_craft_options, recipe_from_craft_payload
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
    "build_craft_options",
    "build_live_channels_status",
    "check_plex_pass",
    "propose_starter_pack",
    "recipe_from_craft_payload",
]
