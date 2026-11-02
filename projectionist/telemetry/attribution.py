"""Tie an in-app Play to a recommendation the product already made (GRO-014).

The client may claim a source (``chat:<assistant message id>`` or
``share:<user_recommendations id>``). The claim only counts when the stored
recommendation surfaced this exact rating key to this caller. Anything else
records the play with empty attribution — never inferred from Plex history.
"""

from __future__ import annotations

import json
from typing import Any, Optional, Tuple

REC_SOURCES = ("chat", "share")
_MAX_REC_LEN = 128


def parse_rec_claim(raw: Optional[str]) -> Optional[Tuple[str, str]]:
    text = str(raw or "").strip()
    if not text or len(text) > _MAX_REC_LEN or ":" not in text:
        return None
    source, _, rec_id = text.partition(":")
    source = source.strip().lower()
    rec_id = rec_id.strip()
    if source not in REC_SOURCES or not rec_id:
        return None
    return source, rec_id


def _card_keys(item: Any) -> set[str]:
    if not isinstance(item, dict):
        return set()
    keys = set()
    for field in ("rating_key", "plex_rating_key", "play_rating_key"):
        value = item.get(field)
        if value not in (None, ""):
            keys.add(str(value))
    return keys


def _chat_card_matches(
    db: Any, message_id: str, rating_key: str, *, user_id: Optional[str]
) -> bool:
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT m.role, m.blocks_json, s.user_id AS owner_id
            FROM chat_messages m JOIN chat_sessions s ON s.id = m.session_id
            WHERE m.id = ?
            """,
            (message_id,),
        ).fetchone()
    if row is None or str(row["role"]) != "assistant":
        return False
    if user_id is not None and str(row["owner_id"] or "") != str(user_id):
        return False
    try:
        blocks = json.loads(row["blocks_json"] or "[]")
    except (TypeError, ValueError):
        return False
    for block in blocks if isinstance(blocks, list) else []:
        if not isinstance(block, dict) or block.get("type") != "title_cards":
            continue
        for item in block.get("items") or []:
            if rating_key in _card_keys(item):
                return True
    return False


def _share_matches(db: Any, rec_id: str, rating_key: str, *, user_id: Optional[str]) -> bool:
    if not user_id:
        return False
    with db.connect() as conn:
        row = conn.execute(
            "SELECT to_user_id, rating_key FROM user_recommendations WHERE id = ?",
            (rec_id,),
        ).fetchone()
    if row is None:
        return False
    return str(row["to_user_id"]) == str(user_id) and str(row["rating_key"] or "") == rating_key


def resolve_play_attribution(
    db: Any,
    *,
    rating_key: str,
    rec: Optional[str],
    user_id: Optional[str],
    scoped_user_id: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Return ``(rec_source, rec_id)`` when verified, else ``(None, None)``.

    ``scoped_user_id`` is the chat-partition owner (None on single-owner installs,
    where every thread belongs to the owner). ``user_id`` is the caller's account id.
    """
    claim = parse_rec_claim(rec)
    if claim is None:
        return None, None
    source, rec_id = claim
    key = str(rating_key or "").strip()
    if not key:
        return None, None
    try:
        if source == "chat" and _chat_card_matches(db, rec_id, key, user_id=scoped_user_id):
            return source, rec_id
        if source == "share" and _share_matches(db, rec_id, key, user_id=user_id):
            return source, rec_id
    except Exception:  # noqa: BLE001
        return None, None
    return None, None
