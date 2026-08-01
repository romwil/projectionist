"""Confirm-gated syllabus → Plex / Projectionist collection publish handoff."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from projectionist.library.db import Database


def syllabus_publish_handoff(
    db: Database,
    *,
    user_id: str,
    list_id: str,
    settings: Any,
    confirm: bool,
    target: str = "plex",
    scoped_user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Prepare a confirm-gated publish of a course/syllabus as a Plex collection.

    ``target=projectionist`` ensures the course list is household-published.
    ``target=plex`` (default) creates a pending ``create_plex_collection`` token.
    """
    del user_id  # reserved for future per-member syllabus scoping
    course = db.get_published_list(list_id, include_items=True)
    if course is None:
        course = db.get_curated_list(list_id, user_id=None, include_items=True)
    if course is None or str(course.get("list_kind") or "") != "course":
        raise ValueError("Published course not found")

    items = list(course.get("items") or [])
    rating_keys: List[str] = []
    lib_ids = [
        int(it["library_item_id"])
        for it in items
        if it.get("library_item_id") is not None
    ]
    if lib_ids:
        placeholders = ",".join("?" for _ in lib_ids)
        with db.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT rating_key FROM library_items
                WHERE id IN ({placeholders}) AND rating_key IS NOT NULL AND rating_key != ''
                """,
                lib_ids,
            ).fetchall()
        rating_keys = [str(r["rating_key"]).strip() for r in rows if r["rating_key"]]
    # Also accept items that already carry a rating_key (future-proof).
    for it in items:
        key = str(it.get("rating_key") or "").strip()
        if key and key not in rating_keys:
            rating_keys.append(key)
    title = str(course.get("name") or "Cinema course").strip() or "Cinema course"
    media_type = "movie"
    show_keys = sum(1 for it in items if str(it.get("media_type") or "") == "show")
    if show_keys > len(items) / 2:
        media_type = "show"

    want = str(target or "plex").strip().lower()
    if want == "projectionist":
        if not confirm:
            return {
                "ok": False,
                "needs_confirm": True,
                "target": "projectionist",
                "title": title,
                "item_count": len(items),
                "message": (
                    f"Publish “{title}” to the household collection shelves? "
                    "Confirm to make it visible on What’s great / Collections."
                ),
            }
        db.set_curated_list_visibility(list_id, visibility="published")
        return {
            "ok": True,
            "target": "projectionist",
            "title": title,
            "list_id": list_id,
            "item_count": len(items),
            "message": f"“{title}” is published to the household shelves.",
        }

    # Plex collection propose (confirm-before-fleet via pending token).
    from projectionist.config_store import (
        plex_collections_configuration_error,
        resolve_plex_section,
    )

    config_error = plex_collections_configuration_error(settings)
    if config_error:
        raise ValueError(config_error)
    if not rating_keys:
        raise ValueError(
            "This syllabus has no Plex rating keys yet — sync the library, then try again."
        )
    section_id = resolve_plex_section(settings, media_type)
    if not section_id:
        raise ValueError(f"Plex {media_type} library section is not configured")

    if not confirm:
        return {
            "ok": False,
            "needs_confirm": True,
            "target": "plex",
            "title": title,
            "media_type": media_type,
            "rating_key_count": len(rating_keys),
            "message": (
                f"Create a Plex collection “{title}” with {len(rating_keys)} titles "
                "from this syllabus? Confirm to queue the fleet action."
            ),
        }

    token = uuid.uuid4().hex
    db.save_pending_action(
        token,
        "create_plex_collection",
        {
            "action": "create_plex_collection",
            "title": title,
            "media_type": media_type,
            "section_id": section_id,
            "rating_keys": rating_keys,
            "source": "syllabus_handoff",
            "list_id": list_id,
        },
        user_id=scoped_user_id,
    )
    return {
        "ok": True,
        "target": "plex",
        "title": title,
        "confirmation_token": token,
        "rating_key_count": len(rating_keys),
        "message": (
            f"Queued Plex collection “{title}” — confirm the pending action to create it."
        ),
    }


def anniversary_live_starter_suggest(
    db: Database,
    *,
    settings: Any,
    owner_user_id: str,
    confirm: bool,
    motif_hint: str = "",
) -> Dict[str, Any]:
    """Suggest (or confirm-publish) a Live starter tied to today’s On This Day rail."""
    from projectionist.library.feeds import feed_on_this_day
    from projectionist.live_channels.starter_pack import propose_starter_pack_from_db

    otd = feed_on_this_day(db, limit=8)
    items: List[Dict[str, Any]] = list(otd.get("items") or [])
    hint = str(motif_hint or "").strip()
    if not hint and items:
        # Prefer a director-ish anniversary context token, else first title.
        context = str(items[0].get("anniversary_context") or "").strip()
        title = str(items[0].get("title") or "").strip()
        hint = context.split("·")[0].strip() if context else title

    pack = propose_starter_pack_from_db(
        db,
        settings=settings,
        owner_user_id=owner_user_id,
    )
    recipes = list(pack.get("recipes") or [])
    if hint:
        lowered = hint.lower()
        ranked = []
        for recipe in recipes:
            blob = " ".join(
                str(recipe.get(k) or "")
                for k in ("name", "motif", "cluster_tag", "summary", "collection_title")
            ).lower()
            score = 1 if lowered and lowered in blob else 0
            ranked.append((score, recipe))
        ranked.sort(key=lambda pair: (-pair[0], str(pair[1].get("name") or "")))
        recipes = [r for _, r in ranked]

    pick = recipes[0] if recipes else None
    if pick is None:
        return {
            "ok": False,
            "needs_confirm": False,
            "message": "No Live starter recipes ready — open Live Channels craft first.",
            "motif_hint": hint,
            "on_this_day_count": len(items),
        }

    if not confirm:
        return {
            "ok": False,
            "needs_confirm": True,
            "motif_hint": hint,
            "recipe": pick,
            "on_this_day_count": len(items),
            "message": (
                f"Put “{pick.get('name') or 'this starter'}” on the air for today’s "
                "On This Day shelf? Confirm to publish the station."
            ),
        }

    # Publish path is owner-gated at the route; here we only return the recipe payload
    # for the existing starters/publish endpoint (confirm-gated there too).
    return {
        "ok": True,
        "needs_confirm": False,
        "motif_hint": hint,
        "recipe": pick,
        "publish_hint": "POST /api/admin/live-channels/starters/publish with confirm=true",
        "message": (
            f"Ready to publish “{pick.get('name') or 'starter'}” — "
            "confirm in Live Channels to put it on the air."
        ),
    }
