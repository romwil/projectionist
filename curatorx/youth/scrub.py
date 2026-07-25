"""Post-generation Youth scrub for chat reply blocks.

Deterministic, fail-closed, and scoped: drop over-ceiling / unrated cards, and
redact known blocked title strings collected from this turn's filtered tool
results. Not a general English censor.

Also used on **read/history** paths so pre-hardening persisted threads cannot
resurface blocked cards to a Youth viewer.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from curatorx.youth.rating_gate import (
    content_rating_allowed,
    resolve_youth_max_rating,
    youth_gate_active,
)

_REDACTION = "[unavailable under Youth rules]"
_MIN_TITLE_LEN = 3


def _filter_card_dicts(
    items: Sequence[Any],
    *,
    max_rating: str,
) -> List[Dict[str, Any]]:
    kept: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        rating = item.get("content_rating")
        if content_rating_allowed(rating, max_rating=max_rating):
            kept.append(dict(item))
    return kept


def _scrub_titles_from_text(text: str, titles: Sequence[str]) -> str:
    out = text
    # Longest first so "The Matrix Reloaded" wins over "The Matrix".
    for title in sorted({t.strip() for t in titles if t and t.strip()}, key=len, reverse=True):
        if len(title) < _MIN_TITLE_LEN:
            continue
        pattern = re.compile(re.escape(title), re.IGNORECASE)
        out = pattern.sub(_REDACTION, out)
    return out


def scrub_youth_chat_blocks(
    blocks: List[Dict[str, Any]],
    *,
    settings: Any,
    blocked_titles: Iterable[str] = (),
) -> List[Dict[str, Any]]:
    """Filter Youth assistant blocks before persist / done events.

    - ``title_cards`` / viewport ``action_prompt`` items: drop unrated / over-ceiling
    - ``text`` / suggested reply strings: redact titles from ``blocked_titles`` only
    """
    max_rating = resolve_youth_max_rating(settings)
    blocked = [str(t) for t in blocked_titles if t]
    out: List[Dict[str, Any]] = []

    for block in blocks:
        if not isinstance(block, Mapping):
            continue
        btype = block.get("type")
        if btype == "title_cards":
            items = _filter_card_dicts(block.get("items") or [], max_rating=max_rating)
            if items:
                out.append({**dict(block), "items": items})
            continue
        if btype == "action_prompt":
            payload = dict(block.get("payload") or {})
            items = _filter_card_dicts(payload.get("items") or [], max_rating=max_rating)
            if not items:
                continue
            out.append({**dict(block), "payload": {**payload, "items": items}})
            continue
        if btype == "text" and blocked:
            content = str(block.get("content") or "")
            out.append({**dict(block), "content": _scrub_titles_from_text(content, blocked)})
            continue
        if btype == "suggested_replies" and blocked:
            payload = dict(block.get("payload") or {})
            replies = payload.get("replies") or []
            if isinstance(replies, list):
                scrubbed = [
                    _scrub_titles_from_text(str(r), blocked) if isinstance(r, str) else r
                    for r in replies
                ]
                out.append({**dict(block), "payload": {**payload, "replies": scrubbed}})
                continue
        out.append(dict(block))
    return out


def scrub_youth_history_messages(
    messages: Sequence[Mapping[str, Any]],
    *,
    user: Any,
    settings: Any,
) -> List[Dict[str, Any]]:
    """Re-apply the Youth card gate when loading persisted chat history.

    Fail-closed: missing / empty / NR / unrecognized ``content_rating`` and
    over-ceiling cards are dropped from ``title_cards`` and viewport
    ``action_prompt`` blocks. Non-Youth viewers get messages unchanged.
    """
    if not youth_gate_active(user):
        return [dict(m) for m in messages]
    out: List[Dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        entry = dict(message)
        blocks = entry.get("blocks")
        if isinstance(blocks, list):
            entry["blocks"] = scrub_youth_chat_blocks(blocks, settings=settings)
        out.append(entry)
    return out
