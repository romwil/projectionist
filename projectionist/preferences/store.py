"""Preference storage and retrieval."""

from __future__ import annotations

from typing import List, Optional

from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.models.schemas import PreferenceSignal
from projectionist.taste.clusters import (
    cluster_tokens_from_text,
    is_valid_cluster_tag,
    normalize_cluster_tag,
)


def remember_preference(
    db: Database,
    signal: PreferenceSignal,
    *,
    user_id: Optional[str] = None,
) -> None:
    weight = signal.weight
    if weight is None:
        weight = {
            "explicit": 2.0,
            "positive": 1.5,
            "negative": -1.5,
            "add": 1.0,
            "dismiss": -0.5,
        }.get(signal.signal_type, 1.0)

    lens_id = signal.lens_id or db.get_active_lens_id() or DEFAULT_LENS_ID
    # Prefer an explicit cluster_tag. Otherwise extract contentful tokens from
    # free text so sentences never become cluster labels.
    tags: List[str] = []
    raw_tag = (signal.cluster_tag or "").strip()
    if raw_tag and is_valid_cluster_tag(raw_tag):
        tags = [normalize_cluster_tag(raw_tag)]
    else:
        candidate = (signal.text or "").strip()
        if candidate and " " not in candidate and is_valid_cluster_tag(candidate):
            tags = [normalize_cluster_tag(candidate)]
        elif candidate:
            tags = cluster_tokens_from_text(candidate)[:8]
    for tag in tags:
        db.set_lens_taste_weight(
            lens_id,
            tag[:120],
            float(weight),
            explicit_lock=signal.explicit_lock if signal.explicit_lock is not None else (signal.signal_type == "explicit"),
            respect_lock=signal.explicit_lock is None,
        )

    db.add_preference(
        signal.signal_type,
        signal.text,
        weight=weight,
        tmdb_id=signal.tmdb_id,
        tvdb_id=signal.tvdb_id,
        media_type=signal.media_type,
        user_id=user_id,
    )


def preference_context(
    db: Database,
    limit: int = 20,
    lens_id: Optional[str] = None,
    *,
    user_id: Optional[str] = None,
) -> str:
    from projectionist.taste.clusters import is_valid_cluster_tag

    resolved = lens_id or db.get_active_lens_id() or DEFAULT_LENS_ID
    taste_rows = db.get_lens_taste_profile(resolved)
    lines: List[str] = []
    if taste_rows:
        clean_rows = [row for row in taste_rows if is_valid_cluster_tag(str(row["cluster_tag"]))]
        if clean_rows:
            lines.append(f"Lens taste profile ({resolved}):")
            for row in clean_rows[:limit]:
                lock = " [locked]" if int(row["explicit_lock"]) else ""
                lines.append(f"- {row['cluster_tag']} (weight={row['weight']}){lock}")
            return "\n".join(lines)

    # v1.8.29 unified memory is the source of truth for account-scoped
    # preferences.  Legacy facts remain only for pre-migration installations.
    notes = db.list_user_memory_notes(user_id, limit=limit) if user_id else []
    facts = [note for note in notes if note.get("kind") == "preference"]
    if not facts:
        facts = db.preference_facts(limit=limit, user_id=user_id)
    if not facts:
        return "No explicit preferences recorded yet."
    for fact in facts:
        if isinstance(fact, dict):
            signal_type = fact.get("metadata", {}).get("signal_type", "explicit")
            lines.append(f"- [{signal_type}] {fact['text']}")
        else:
            lines.append(f"- [{fact['signal_type']}] {fact['text']}")
    return "User preferences:\n" + "\n".join(lines)
