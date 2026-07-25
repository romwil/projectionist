"""Helpers for human-facing recommendation rationale on title cards."""

from __future__ import annotations

# Internal pipeline / lookup labels — never show these as "Why this?".
PIPELINE_RECOMMENDATION_REASONS = frozenset(
    {
        "tmdb title match",
        "tmdb search",
        "missing from your collection",
    }
)


def sanitize_recommendation_reason(reason: str | None) -> str:
    """Return curator rationale suitable for UI, or empty if missing/pipeline-only."""
    text = str(reason or "").strip()
    if not text:
        return ""
    if text.casefold() in PIPELINE_RECOMMENDATION_REASONS:
        return ""
    return text
