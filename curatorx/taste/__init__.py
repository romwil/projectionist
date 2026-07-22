"""Member taste profile helpers and weekly For-you rail builder."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Sequence

from curatorx.config_store import Settings
from curatorx.digest.service import current_week_start
from curatorx.library.db import DEFAULT_LENS_ID, Database
from curatorx.library.query import row_to_query_item

logger = logging.getLogger(__name__)

# Hard cap on optional LLM polish calls per weekly fan-out run.
MAX_LLM_WHY_CALLS = 5
DEFAULT_RAIL_SIZE = 8


def _persona_voice_line(db: Database, *, for_guest: bool = False) -> str:
    try:
        personas = db.list_persona_templates()
    except Exception:  # noqa: BLE001
        personas = []
    default = None
    guest = None
    for persona in personas or []:
        if not isinstance(persona, dict):
            continue
        if persona.get("is_default"):
            default = persona
        name = str(persona.get("name") or "").lower()
        if "guest" in name or "host" in name or "concierge" in name:
            guest = persona
    chosen = guest if for_guest and guest else default or (personas[0] if personas else None)
    if not chosen:
        return "Your curator lined up a few picks from your shelves."
    name = str(chosen.get("name") or "Your curator").strip()
    return f"{name} picked these with your taste in mind."


def _template_why(title: str, cluster: str, *, persona_name: str = "Your curator") -> str:
    tag = cluster.strip() or "favorites"
    return f"{persona_name} thinks {title} fits your {tag} lean — unwatched and worth a look."


def build_member_taste_payload(
    db: Database,
    *,
    user_id: Optional[str],
    lens_id: str = DEFAULT_LENS_ID,
    limit: int = 40,
) -> Dict[str, Any]:
    clusters = db.get_effective_taste_profile(user_id, lens_id=lens_id, limit=limit)
    overrides = db.get_user_taste_overrides(user_id) if user_id else []
    return {
        "lens_id": lens_id or DEFAULT_LENS_ID,
        "clusters": clusters,
        "override_count": len(overrides),
        "tunable": bool(user_id),
    }


def _top_clusters(db: Database, user_id: Optional[str], *, limit: int = 5) -> List[str]:
    profile = db.get_effective_taste_profile(user_id, limit=max(limit * 3, 12))
    # Prefer weights clearly above neutral 0.5
    ranked = sorted(profile, key=lambda c: float(c.get("weight") or 0.5), reverse=True)
    tags = [str(c["cluster_tag"]) for c in ranked if float(c.get("weight") or 0) >= 0.55]
    if not tags:
        tags = [str(c["cluster_tag"]) for c in ranked[:limit]]
    return tags[:limit]


def _pick_unwatched_for_clusters(
    db: Database,
    clusters: Sequence[str],
    *,
    limit: int = DEFAULT_RAIL_SIZE,
) -> List[Dict[str, Any]]:
    if not clusters:
        return []
    picks: List[Dict[str, Any]] = []
    seen_ids: set[int] = set()
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM library_items
            WHERE COALESCE(view_count, 0) = 0
            ORDER BY COALESCE(vote_average, 0) DESC, title ASC
            LIMIT 400
            """
        ).fetchall()
    lowered = [c.lower() for c in clusters]
    for row in rows:
        item_id = int(row["id"])
        if item_id in seen_ids:
            continue
        blob_parts = []
        for col in ("genres", "keywords"):
            if col not in row.keys():
                continue
            raw = row[col]
            if not raw:
                continue
            try:
                parsed = json.loads(raw) if isinstance(raw, str) else raw
            except (json.JSONDecodeError, TypeError):
                parsed = raw
            if isinstance(parsed, list):
                blob_parts.extend(str(x).lower() for x in parsed)
            else:
                blob_parts.append(str(parsed).lower())
        blob = " ".join(blob_parts)
        matched = next((c for c in lowered if c and c in blob), None)
        if not matched:
            continue
        item = row_to_query_item(row)
        item["matched_cluster"] = matched
        picks.append(item)
        seen_ids.add(item_id)
        if len(picks) >= limit:
            break
    return picks


def build_weekly_rail_for_user(
    db: Database,
    settings: Optional[Settings] = None,
    *,
    user: Dict[str, Any],
    now: Optional[float] = None,
    llm_budget: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """Build (and persist) a persona-voiced weekly rail for one member."""
    del settings  # reserved for future LLM polish settings
    user_id = str(user["id"])
    role = str(user.get("role") or "member")
    for_guest = role == "guest"
    voice = _persona_voice_line(db, for_guest=for_guest)
    persona_name = voice.split(" ", 1)[0] if voice else "Your curator"
    clusters = _top_clusters(db, user_id)
    picks = _pick_unwatched_for_clusters(db, clusters, limit=DEFAULT_RAIL_SIZE)
    items: List[Dict[str, Any]] = []
    for pick in picks:
        title = str(pick.get("title") or "Untitled")
        cluster = str(pick.get("matched_cluster") or (clusters[0] if clusters else "favorites"))
        why = _template_why(title, cluster, persona_name=persona_name)
        # Optional LLM polish reserved — budget tracked but templates are the v1 path.
        if llm_budget is not None and llm_budget.get("remaining", 0) > 0:
            # Keep template why; decrement only if a future LLM call succeeds.
            pass
        items.append(
            {
                "id": pick.get("id"),
                "title": title,
                "year": pick.get("year"),
                "media_type": pick.get("media_type") or "movie",
                "tmdb_id": pick.get("tmdb_id"),
                "tvdb_id": pick.get("tvdb_id"),
                "rating_key": pick.get("rating_key"),
                "poster_url": pick.get("poster_url") or "",
                "genres": pick.get("genres") or [],
                "why": why,
                "matched_cluster": cluster,
            }
        )
    preferred = str(user.get("preferred_name") or user.get("display_name") or "you").strip()
    title = f"For you this week, {preferred}"
    ts = time.time() if now is None else float(now)
    bucket = int(current_week_start(ts))
    return db.save_user_weekly_rail(
        user_id=user_id,
        week_bucket=bucket,
        title=title,
        voice_line=voice,
        items=items,
    )


def deliver_member_weekly_rails(
    db: Database,
    settings: Settings,
    *,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Fan out weekly rails to non-disabled members (hard LLM cap)."""
    users = db.list_users(limit=500)
    llm_budget = {"remaining": MAX_LLM_WHY_CALLS, "used": 0}
    built = 0
    empty = 0
    for user in users:
        if user.get("disabled"):
            continue
        role = str(user.get("role") or "member")
        if role == "guest":
            continue
        rail = build_weekly_rail_for_user(
            db, settings, user=user, now=now, llm_budget=llm_budget
        )
        if rail.get("items"):
            built += 1
        else:
            empty += 1
    return {
        "built": built,
        "empty": empty,
        "llm_calls_used": llm_budget["used"],
        "llm_cap": MAX_LLM_WHY_CALLS,
    }


def feed_for_you_weekly(
    db: Database,
    *,
    user_id: str,
    limit: int = DEFAULT_RAIL_SIZE,
) -> Dict[str, Any]:
    """Explore feed shape for the member's latest weekly rail."""
    rail = db.get_latest_user_weekly_rail(user_id)
    if not rail:
        return {
            "feed": "for-you",
            "items": [],
            "total": 0,
            "note": "Your personalized weekly rail appears after the next curator pass.",
            "mode": "weekly_for_you",
            "empty": True,
        }
    items = list(rail.get("items") or [])[: max(1, int(limit))]
    return {
        "feed": "for-you",
        "items": items,
        "total": len(items),
        "note": None if items else "Quiet week — tune your taste or rate a few titles.",
        "mode": "weekly_for_you",
        "title": rail.get("title"),
        "voice_line": rail.get("voice_line"),
        "week_bucket": rail.get("week_bucket"),
        "rail_id": rail.get("id"),
    }
