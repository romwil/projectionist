"""Concierge consented find → request acquisition path (Seerr/arr)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from curatorx.config_store import Settings, seerr_configuration_error
from curatorx.library.db import Database


def _library_hit(
    db: Database,
    *,
    media_type: str,
    tmdb_id: Optional[int],
    tvdb_id: Optional[int],
    title: str,
) -> Optional[Dict[str, Any]]:
    with db.connect() as conn:
        if media_type == "show" and tvdb_id is not None:
            row = conn.execute(
                "SELECT * FROM library_items WHERE media_type = 'show' AND tvdb_id = ? LIMIT 1",
                (int(tvdb_id),),
            ).fetchone()
            if row:
                return dict(row)
        if tmdb_id is not None:
            row = conn.execute(
                "SELECT * FROM library_items WHERE media_type = ? AND tmdb_id = ? LIMIT 1",
                (media_type, int(tmdb_id)),
            ).fetchone()
            if row:
                return dict(row)
        cleaned = str(title or "").strip()
        if cleaned:
            row = conn.execute(
                """
                SELECT * FROM library_items
                WHERE media_type = ? AND title = ? COLLATE NOCASE
                LIMIT 1
                """,
                (media_type, cleaned),
            ).fetchone()
            if row:
                return dict(row)
    return None


def build_acquire_path(
    db: Database,
    settings: Settings,
    *,
    title: str,
    media_type: str = "movie",
    tmdb_id: Optional[int] = None,
    tvdb_id: Optional[int] = None,
    user_id: Optional[str] = None,
    seerr_user_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Build an explicit find → availability → request path with consent gate.

    Step 3 only creates a pending confirmation token when Seerr is configured and
    the title is not already in the library. The caller must still confirm.
    """
    cleaned_type = "show" if str(media_type).lower() in {"show", "tv", "series"} else "movie"
    cleaned_title = str(title or "").strip() or "Untitled"
    steps: List[Dict[str, Any]] = []

    steps.append(
        {
            "step": 1,
            "action": "find",
            "status": "done",
            "label": "Find the title",
            "detail": f"Located {cleaned_title}"
            + (f" (TMDB {tmdb_id})" if tmdb_id is not None else "")
            + (f" (TVDB {tvdb_id})" if tvdb_id is not None else ""),
        }
    )

    owned = _library_hit(
        db,
        media_type=cleaned_type,
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
        title=cleaned_title,
    )
    if owned:
        steps.append(
            {
                "step": 2,
                "action": "availability",
                "status": "in_library",
                "label": "Check availability",
                "detail": "Already in your library — no request needed.",
            }
        )
        steps.append(
            {
                "step": 3,
                "action": "request",
                "status": "skipped",
                "label": "Request via Seerr",
                "detail": "Skipped because the title is already here.",
            }
        )
        return {
            "title": cleaned_title,
            "media_type": cleaned_type,
            "tmdb_id": tmdb_id,
            "tvdb_id": tvdb_id,
            "availability": "in_library",
            "steps": steps,
            "confirmation_token": None,
            "requires_consent": False,
        }

    seerr_error = seerr_configuration_error(settings)
    if seerr_error:
        steps.append(
            {
                "step": 2,
                "action": "availability",
                "status": "not_requestable",
                "label": "Check availability",
                "detail": "Not in the library. Seerr is not configured for requests.",
            }
        )
        steps.append(
            {
                "step": 3,
                "action": "request",
                "status": "blocked",
                "label": "Request via Seerr",
                "detail": seerr_error,
            }
        )
        return {
            "title": cleaned_title,
            "media_type": cleaned_type,
            "tmdb_id": tmdb_id,
            "tvdb_id": tvdb_id,
            "availability": "not_here_yet",
            "steps": steps,
            "confirmation_token": None,
            "requires_consent": False,
            "error": seerr_error,
        }

    if tmdb_id is None:
        steps.append(
            {
                "step": 2,
                "action": "availability",
                "status": "incomplete",
                "label": "Check availability",
                "detail": "Need a TMDB id before a Seerr request can be proposed.",
            }
        )
        steps.append(
            {
                "step": 3,
                "action": "request",
                "status": "blocked",
                "label": "Request via Seerr",
                "detail": "Provide tmdb_id (and tvdb_id for shows) to continue.",
            }
        )
        return {
            "title": cleaned_title,
            "media_type": cleaned_type,
            "tmdb_id": None,
            "tvdb_id": tvdb_id,
            "availability": "not_here_yet",
            "steps": steps,
            "confirmation_token": None,
            "requires_consent": False,
        }

    if settings.seerr.require_linked_user_for_requests and not seerr_user_id:
        steps.append(
            {
                "step": 2,
                "action": "availability",
                "status": "requestable",
                "label": "Check availability",
                "detail": "Not in the library — requestable once Seerr is linked.",
            }
        )
        steps.append(
            {
                "step": 3,
                "action": "request",
                "status": "blocked",
                "label": "Request via Seerr",
                "detail": "Link your Seerr account before requesting.",
            }
        )
        return {
            "title": cleaned_title,
            "media_type": cleaned_type,
            "tmdb_id": tmdb_id,
            "tvdb_id": tvdb_id,
            "availability": "requestable",
            "steps": steps,
            "confirmation_token": None,
            "requires_consent": False,
            "error": "Seerr account must be linked before requesting",
        }

    steps.append(
        {
            "step": 2,
            "action": "availability",
            "status": "requestable",
            "label": "Check availability",
            "detail": "Not in the library — requestable via Seerr with your explicit OK.",
        }
    )

    pending_payload: Dict[str, Any] = {
        "action": "request_seerr",
        "media_type": cleaned_type,
        "tmdb_id": int(tmdb_id),
        "title": cleaned_title,
    }
    if tvdb_id is not None:
        pending_payload["tvdb_id"] = int(tvdb_id)
    if seerr_user_id is not None:
        pending_payload["seerr_user_id"] = int(seerr_user_id)

    token = uuid.uuid4().hex
    db.save_pending_action(token, "request_seerr", pending_payload, user_id=user_id)
    steps.append(
        {
            "step": 3,
            "action": "request",
            "status": "awaiting_consent",
            "label": "Request via Seerr",
            "detail": "Confirm to place the Seerr request. Nothing is sent until you approve.",
            "confirmation_token": token,
        }
    )
    return {
        "title": cleaned_title,
        "media_type": cleaned_type,
        "tmdb_id": tmdb_id,
        "tvdb_id": tvdb_id,
        "availability": "requestable",
        "steps": steps,
        "confirmation_token": token,
        "requires_consent": True,
    }
