"""Client capability manifest (NAT-001).

A capability number is that feature's contract version: ``0`` absent, ``1`` the
first contract, ``2`` a breaking revision. Additive fields do not bump it.

``features.cached_art`` and ``capabilities.cached_art`` are one fact. The
signed-in feature flag is the boolean shipped with EXP-006. The capability is
``1`` while that flag is on and ``0`` when it is off.
"""

from __future__ import annotations

# First published contract. Clients branch on this number and on capabilities,
# never on the server version string.
API_CONTRACT = 3

# EXP-006 shipped in 1.41.1. Hub, title, and search art URLs point at the cache.
CACHED_ART_ENABLED = True


def client_capabilities() -> dict[str, int]:
    """Capability names a client may read on every ``GET /api/features``."""
    return {
        "device_pairing": 1,
        "throw": 1,
        "playback_engine": 1,  # ENG-003 session API, VOD fMP4 remux
        "caption_tracks": 0,  # ENG-004
        "shared_sessions": 1,  # SES-004 live channel, command authorization, clock
        "timeline": 0,  # TML-005
        "timeline_files": 1,  # TML-001 fingerprint of size, mtime, and duration
        "timeline_dialogue": 1,  # TML-002 dialogue from the subtitle cache
        "tracks": 0,  # TRK-003
        "native_sign_in": 1,  # NAT-002 device credential on every web sign-in path
        "push": 0,  # NAT-006, accepted, not shipped
        "approvals": 0,  # NAT-006, accepted, not shipped
        "cached_art": 1 if CACHED_ART_ENABLED else 0,
        # Signed-in features publish addresses.home and addresses.away.
        # Playlist URLs stay relative. The number is public; the addresses are not.
        "household_addresses": 1,
        "rooms": 1,  # SES-002 named screens; the list has no playback
        "session_object": 1,  # SES-003 owner, screen, position, level
        "session_join": 1,  # SES-005 code or owner approval, guest remote
        "youth_join": 1,  # SES-009 approval tightens the room; push waits
        "session_captions": 1,  # SES-006 handheld caption feed
        "session_handoff": 1,  # SES-007 same session, new screen
    }
