"""Deliver Year in Review inbox + email notifications."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.notifications.service import deliver_notification
from projectionist.year_in_review.snapshot import build_reel_for_user, mark_notified

logger = logging.getLogger(__name__)


def prior_calendar_year(now: Optional[float] = None) -> int:
    dt = datetime.fromtimestamp(now or datetime.now(tz=timezone.utc).timestamp(), tz=timezone.utc)
    return int(dt.year) - 1


def current_calendar_year(now: Optional[float] = None) -> int:
    dt = datetime.fromtimestamp(now or datetime.now(tz=timezone.utc).timestamp(), tz=timezone.utc)
    return int(dt.year)


def in_tease_window(now: Optional[float] = None) -> bool:
    """Late Dec soft tease: Dec 20–31."""
    dt = datetime.fromtimestamp(now or datetime.now(tz=timezone.utc).timestamp(), tz=timezone.utc)
    return dt.month == 12 and dt.day >= 20


def in_drop_window(now: Optional[float] = None) -> bool:
    """Early Jan full drop: Jan 1–14 for prior year."""
    dt = datetime.fromtimestamp(now or datetime.now(tz=timezone.utc).timestamp(), tz=timezone.utc)
    return dt.month == 1 and dt.day <= 14


def _ready_path(year: int, status: Optional[str]) -> Optional[str]:
    if status in ("ready", "tease"):
        return f"/year-in-review/{int(year)}"
    return None


def deliver_year_in_review(
    db: Database,
    settings: Settings,
    *,
    year: int,
    user_ids: Optional[Sequence[str]] = None,
    status_hint: str = "ready",
    force: bool = False,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Generate snapshots and notify opted-in non-guest users with Plex mapping.

    When ``force`` is True (owner self-test), skip opt-in / Plex-mapping gates and
    still create the inbox notification so the test path matches production delivery.
    """
    _ = now  # reserved for clock injection by callers / tests
    skipped_disabled = 0
    skipped_opt_out = 0
    skipped_guest = 0
    skipped_unmapped = 0
    skipped_empty = 0
    skipped_missing = 0
    delivered = 0
    emailed = 0
    generated = 0
    targeted = 0
    last_status: Optional[str] = None
    last_path: Optional[str] = None

    candidates: List[Dict[str, Any]] = []
    if user_ids is None:
        candidates = list(db.list_users(limit=500))
    else:
        seen: set[str] = set()
        for raw in user_ids:
            uid = str(raw or "").strip()
            if not uid or uid in seen:
                continue
            seen.add(uid)
            row = db.get_user(uid)
            if row is None:
                skipped_missing += 1
                continue
            candidates.append(db._row_to_user(row))

    for user in candidates:
        if user.get("disabled"):
            skipped_disabled += 1
            continue
        if str(user.get("role") or "") == "guest":
            skipped_guest += 1
            continue
        targeted += 1
        if not user.get("year_in_review_opt_in") and not force:
            skipped_opt_out += 1
            continue
        if not user.get("plex_user_id") and not force:
            skipped_unmapped += 1
            continue
        uid = str(user["id"])
        try:
            snap = build_reel_for_user(db, user_id=uid, year=year, status_hint=status_hint)
        except Exception:  # noqa: BLE001
            logger.exception("YIR generate failed for %s", uid)
            continue
        generated += 1
        last_status = str(snap.get("status") or "")
        last_path = _ready_path(year, last_status)
        if snap.get("status") == "empty":
            skipped_empty += 1
            continue
        preferred = str(user.get("preferred_name") or user.get("display_name") or "there").strip()
        path = f"/year-in-review/{int(year)}"
        if status_hint == "tease":
            title = f"Your {year} reel is almost ready"
            body = (
                f"Hi {preferred},\n\n"
                f"Projectionist is lining up a short Year in Review for {year}. "
                f"Peek early at {path} when you’re ready — the full drop lands in January.\n"
            )
        else:
            title = f"Your {year} Year in Review is ready"
            body = (
                f"Hi {preferred},\n\n"
                f"Your private {year} cinema reel is ready. "
                f"Open {path} inside Projectionist to watch it.\n\n"
                "These chapters use your tracked completions — not household Plex totals.\n"
            )
        result = deliver_notification(
            db,
            settings,
            user_id=uid,
            kind="year-in-review",
            title=title,
            body=body,
            payload={"year": int(year), "path": path, "status": snap.get("status")},
            related_id=f"yir-{year}",
            email_subject=title,
            year=int(year),
            force_inbox=force,
        )
        if result.get("notification"):
            delivered += 1
            mark_notified(db, user_id=uid, year=year)
        if result.get("emailed"):
            emailed += 1

    return {
        "year": int(year),
        "status_hint": status_hint,
        "status": last_status,
        "path": last_path,
        "generated": generated,
        "delivered": delivered,
        "emailed": emailed,
        "targeted": targeted,
        "skipped_opt_out": skipped_opt_out,
        "skipped_disabled": skipped_disabled,
        "skipped_guest": skipped_guest,
        "skipped_unmapped": skipped_unmapped,
        "skipped_empty": skipped_empty,
        "skipped_missing": skipped_missing,
    }
