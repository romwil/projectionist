"""Year in Review — snapshot program over watch-tracker rollups."""

from __future__ import annotations

REEL_SCHEMA_VERSION = 3

HONESTY_FOOTNOTE = (
    "Your Plex plays this year (this account), not the household "
    "and not only titles played inside Projectionist."
)
CONFIDENCE_NOTE = (
    "Some plays come from Plex ‘played’ marks when we didn’t see live progress."
)

__all__ = ["REEL_SCHEMA_VERSION", "HONESTY_FOOTNOTE", "CONFIDENCE_NOTE"]
