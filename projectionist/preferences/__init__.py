"""Preferences package."""

from projectionist.preferences.purge import suggest_purge_candidates
from projectionist.preferences.store import preference_context, remember_preference

__all__ = ["preference_context", "remember_preference", "suggest_purge_candidates"]
