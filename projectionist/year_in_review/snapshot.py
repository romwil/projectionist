"""Build and persist Year in Review reel snapshots."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from projectionist.library.db import Database
from projectionist.watch_tracker.rollups import build_year_rollup
from projectionist.year_in_review import REEL_SCHEMA_VERSION
from projectionist.year_in_review.chapters import assemble_chapters
from projectionist.year_in_review.recap import build_recap
from projectionist.year_in_review.signals import collect_social_signals

logger = logging.getLogger(__name__)


def get_snapshot(db: Database, *, user_id: str, year: int) -> Optional[Dict[str, Any]]:
    with db.connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM year_in_review_snapshots
            WHERE user_id = ? AND year = ?
            """,
            (user_id, int(year)),
        ).fetchone()
    if row is None:
        return None
    reel: Dict[str, Any] = {}
    try:
        parsed = json.loads(str(row["reel_json"] or "{}"))
        if isinstance(parsed, dict):
            reel = parsed
    except (TypeError, ValueError, json.JSONDecodeError):
        reel = {}
    return {
        "user_id": str(row["user_id"]),
        "year": int(row["year"]),
        "schema_version": int(row["schema_version"]),
        "status": str(row["status"]),
        "reel": reel,
        "generated_at": float(row["generated_at"]),
        "notified_at": float(row["notified_at"]) if row["notified_at"] is not None else None,
    }


def save_snapshot(
    db: Database,
    *,
    user_id: str,
    year: int,
    status: str,
    reel: Dict[str, Any],
    notified_at: Optional[float] = None,
) -> Dict[str, Any]:
    now = time.time()
    payload = json.dumps(reel, separators=(",", ":"), sort_keys=True)

    def _write() -> None:
        with db.connect() as conn:
            conn.execute(
                """
                INSERT INTO year_in_review_snapshots (
                    user_id, year, schema_version, status, reel_json, generated_at, notified_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, year) DO UPDATE SET
                    schema_version = excluded.schema_version,
                    status = excluded.status,
                    reel_json = excluded.reel_json,
                    generated_at = excluded.generated_at,
                    notified_at = COALESCE(excluded.notified_at, year_in_review_snapshots.notified_at)
                """,
                (
                    user_id,
                    int(year),
                    REEL_SCHEMA_VERSION,
                    status,
                    payload,
                    now,
                    notified_at,
                ),
            )

    db.run_write(_write, label="save_yir_snapshot")
    return get_snapshot(db, user_id=user_id, year=year) or {
        "user_id": user_id,
        "year": int(year),
        "status": status,
        "reel": reel,
        "generated_at": now,
        "notified_at": notified_at,
        "schema_version": REEL_SCHEMA_VERSION,
    }


def mark_notified(db: Database, *, user_id: str, year: int) -> None:
    now = time.time()

    def _write() -> None:
        with db.connect() as conn:
            conn.execute(
                """
                UPDATE year_in_review_snapshots
                SET notified_at = ?
                WHERE user_id = ? AND year = ?
                """,
                (now, user_id, int(year)),
            )

    db.run_write(_write, label="mark_yir_notified")


def build_reel_for_user(
    db: Database,
    *,
    user_id: str,
    year: int,
    status_hint: str = "ready",
) -> Dict[str, Any]:
    """Compute rollup + chapters and persist a snapshot."""
    user_row = db.get_user(user_id)
    if user_row is None:
        raise ValueError(f"User not found: {user_id}")
    user = db._row_to_user(user_row)
    if str(user.get("role") or "") == "guest":
        raise ValueError("Guests do not receive Year in Review")

    display_name = str(user.get("preferred_name") or user.get("display_name") or "friend").strip()
    rollup = build_year_rollup(db, user_id=user_id, year=year)
    signals = collect_social_signals(db, user_id=user_id, year=year)
    ctx = {"display_name": display_name, **signals}

    if not rollup.has_enough_data and rollup.completion_count <= 0:
        status = "empty"
        chapters: List[Dict[str, Any]] = []
    elif status_hint == "tease" and not rollup.has_enough_data:
        status = "tease"
        chapters = assemble_chapters(rollup, ctx)[:3] if rollup.completion_count else []
    elif not rollup.has_enough_data:
        status = "empty"
        chapters = []
    else:
        status = "ready" if status_hint != "tease" else "tease"
        chapters = assemble_chapters(rollup, ctx)
        if status == "tease":
            chapters = chapters[:3]

    reel = {
        "schema_version": REEL_SCHEMA_VERSION,
        "year": int(year),
        "user_id": user_id,
        "display_name": display_name,
        "status": status,
        "honesty": {
            "footnote": "Finishes attributed to you — not the whole household.",
            "confidence_note": (
                "Some finishes come from Plex ‘played’ marks when we didn’t see progress."
            ),
        },
        "rollup": rollup.as_dict(),
        "recap": build_recap(rollup, ctx) if status == "ready" else None,
        "chapters": chapters,
        "path": f"/year-in-review/{int(year)}",
    }
    return save_snapshot(db, user_id=user_id, year=year, status=status, reel=reel)
