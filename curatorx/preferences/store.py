"""Preference storage and retrieval."""

from __future__ import annotations

from typing import List, Optional

from curatorx.library.db import DEFAULT_LENS_ID, Database
from curatorx.models.schemas import PreferenceSignal


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
    cluster_tag = (signal.cluster_tag or signal.text or "").strip()
    if cluster_tag:
        db.set_lens_taste_weight(
            lens_id,
            cluster_tag[:120],
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
    resolved = lens_id or db.get_active_lens_id() or DEFAULT_LENS_ID
    taste_rows = db.get_lens_taste_profile(resolved)
    lines: List[str] = []
    if taste_rows:
        lines.append(f"Lens taste profile ({resolved}):")
        for row in taste_rows[:limit]:
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
