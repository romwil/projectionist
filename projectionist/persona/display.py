"""The one name members see for the agent (GRO-014).

Same rule as ``frontend/src/lib/curatorName.ts``: the owner's curator name when
set, else the default voice as the persona picker shows it (nickname, else
name), else "Your curator".
"""

from __future__ import annotations

from typing import Any, Dict, Optional

DEFAULT_CURATOR_NAME = "Curator"
GENERIC_CURATOR_NAME = "Your curator"


def voice_label(voice: Optional[Dict[str, Any]]) -> str:
    if not isinstance(voice, dict):
        return ""
    return str(voice.get("nickname") or "").strip() or str(voice.get("name") or "").strip()


def default_voice(db: Any) -> Optional[Dict[str, Any]]:
    try:
        voices = db.list_persona_templates() or []
    except Exception:  # noqa: BLE001
        return None
    voices = [v for v in voices if isinstance(v, dict)]
    return next((v for v in voices if v.get("is_default")), voices[0] if voices else None)


def curator_display_name(curator_name: Optional[str], voice: Optional[Dict[str, Any]] = None) -> str:
    named = str(curator_name or "").strip()
    if named and named != DEFAULT_CURATOR_NAME:
        return named
    return voice_label(voice) or GENERIC_CURATOR_NAME


def in_sentence(name: str) -> str:
    """Lower-case the generic name when it is not the first word."""
    return "your curator" if name == GENERIC_CURATOR_NAME else name
