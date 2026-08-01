"""Library API audience sanitization (members → public schema)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from projectionist.config_store import Settings
from projectionist.privacy import sanitize

# Bound saved gap/recommend rails so a bad chat→save cannot blow up /library/:id.
SAVED_LIBRARY_RAIL_LIMIT = 12


def library_audience(settings: Settings, user: Any) -> str:
    """Members get public schema when multi-user is on; owners/single-user keep internal."""
    if settings.features.multi_user_enabled and getattr(user, "role", "owner") != "owner":
        return "member"
    return "owner"


def sanitize_library_payload(payload: Any, *, settings: Settings, user: Any) -> Any:
    return sanitize(
        payload,
        audience=library_audience(settings, user),  # type: ignore[arg-type]
        settings=settings,
    )


def sanitize_saved_rail_items(
    items: Any,
    *,
    limit: int = SAVED_LIBRARY_RAIL_LIMIT,
) -> List[Dict[str, Any]]:
    """De-dupe and bound title cards for saved-library rails.

    Fail closed on missing title or missing tmdb/tvdb id so invented gap junk
    never persists or re-renders as an unbounded poster strip.
    """
    if not isinstance(items, list):
        return []
    cap = max(1, int(limit or SAVED_LIBRARY_RAIL_LIMIT))
    kept: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for raw in items:
        if not isinstance(raw, Mapping):
            continue
        title = str(raw.get("title") or "").strip()
        if not title:
            continue
        try:
            tmdb_id = int(raw.get("tmdb_id") or 0)
        except (TypeError, ValueError):
            tmdb_id = 0
        try:
            tvdb_id = int(raw.get("tvdb_id") or 0)
        except (TypeError, ValueError):
            tvdb_id = 0
        if tmdb_id <= 0 and tvdb_id <= 0:
            continue
        media_type = str(raw.get("media_type") or "").strip().lower() or "movie"
        key = (
            f"{media_type}:tmdb:{tmdb_id}"
            if tmdb_id > 0
            else f"{media_type}:tvdb:{tvdb_id}"
        )
        if key in seen:
            continue
        seen.add(key)
        kept.append(dict(raw))
        if len(kept) >= cap:
            break
    return kept


def normalize_saved_library_content(content: Any) -> Any:
    """Harden title_cards / recommendation rails inside a saved-page payload."""
    if not isinstance(content, Mapping):
        return content
    blocks = content.get("blocks")
    if not isinstance(blocks, list):
        return dict(content)
    cleaned_blocks: List[Any] = []
    for block in blocks:
        if not isinstance(block, Mapping):
            cleaned_blocks.append(block)
            continue
        block_type = str(block.get("type") or "")
        if block_type == "title_cards":
            items = sanitize_saved_rail_items(block.get("items"))
            if not items:
                continue
            cleaned_blocks.append({**dict(block), "items": items})
            continue
        if block_type == "action_prompt" and block.get("action") == "open_viewport":
            payload = block.get("payload")
            if isinstance(payload, Mapping):
                items = sanitize_saved_rail_items(payload.get("items"))
                if not items:
                    continue
                cleaned_blocks.append(
                    {
                        **dict(block),
                        "payload": {**dict(payload), "items": items},
                    }
                )
            else:
                cleaned_blocks.append(dict(block))
            continue
        cleaned_blocks.append(dict(block))
    return {**dict(content), "blocks": cleaned_blocks}
