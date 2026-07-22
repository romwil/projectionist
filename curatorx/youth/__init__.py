"""Youth-facing safety: content-rating gate, engagement presets, chat guardrails."""

from __future__ import annotations

from curatorx.youth.rating_gate import (
    DEFAULT_YOUTH_MAX_RATING,
    allowed_rating_labels,
    content_rating_allowed,
    filter_items_for_youth,
    normalize_content_rating,
    rating_rank,
    resolve_youth_max_rating,
    youth_gate_active,
)

__all__ = [
    "DEFAULT_YOUTH_MAX_RATING",
    "allowed_rating_labels",
    "content_rating_allowed",
    "filter_items_for_youth",
    "normalize_content_rating",
    "rating_rank",
    "resolve_youth_max_rating",
    "youth_gate_active",
]
