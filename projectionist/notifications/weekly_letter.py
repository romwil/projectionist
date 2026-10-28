"""The weekly household letter — prose, not dashboard tiles.

Composed from the library index, delivered once a week to the owner's existing
notifications inbox (kind ``digest``), and optionally emailed over the same mail
transport as the newsletters when the owner opts in.
"""

from __future__ import annotations

import shutil
import time
import uuid
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.library.health import STALE_ADD_DAYS

DEAD_WEIGHT_LIMIT = 6
LETTER_TITLE = "A letter about the house"
LETTER_CONFIG_KEY = "weekly_letter_settings"
LETTER_NEWSLETTER_ID = "house-letter"

logger = logging.getLogger(__name__)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def format_hours(ms: int) -> str:
    hours = max(0, int(ms or 0)) / 3_600_000.0
    if hours <= 0:
        return "no timed hours"
    if hours < 1:
        return "less than an hour"
    if hours < 10:
        return f"{hours:.1f} hours"
    return f"{int(round(hours))} hours"


def format_bytes(size: int) -> str:
    value = max(0, int(size or 0))
    if value <= 0:
        return "an unknown amount of disk"
    units = (("TB", 1024**4), ("GB", 1024**3), ("MB", 1024**2), ("KB", 1024))
    for label, step in units:
        if value >= step:
            amount = value / step
            rounded = round(amount)
            # Whole numbers stay "2 TB" / "38 TB". A tenth stays a tenth so
            # 37.6 TB of movies cannot collapse into a 38 TB volume label.
            if abs(amount - rounded) < 0.05:
                return f"{int(rounded)} {label}"
            return f"{amount:.1f} {label}"
    return f"{value} bytes"


def volume_capacity_bytes(settings: Optional[Settings] = None) -> int:
    """Filesystem capacity of configured media roots, de-duplicated by device.

    Returns 0 when we cannot see a real volume — omit "the disks hold" rather
    than pretending library-used is how much the disks hold.
    """
    if settings is None:
        return 0
    paths: List[str] = []
    for attr in ("movies_root", "tv_root", "radarr_root_folder", "sonarr_root_folder"):
        raw = str(getattr(settings, attr, "") or "").strip()
        if raw:
            paths.append(raw)
    totals: Dict[int, int] = {}
    for raw in paths:
        path = Path(raw)
        try:
            if not path.exists():
                continue
            st = path.stat()
            usage = shutil.disk_usage(path)
        except OSError:
            continue
        prev = totals.get(st.st_dev, 0)
        if int(usage.total) > prev:
            totals[st.st_dev] = int(usage.total)
    return int(sum(totals.values()))


def disk_sentence(stats: Dict[str, Any]) -> str:
    """Capacity vs library used — never reuse one number as the other."""
    capacity = int(stats.get("capacity_bytes") or 0)
    movie_bytes = int(stats.get("movie_bytes") or 0)
    show_bytes = int(stats.get("show_bytes") or 0)

    used_parts: List[str] = []
    if movie_bytes > 0:
        used_parts.append(f"movies take {format_bytes(movie_bytes)}")
    if show_bytes > 0:
        used_parts.append(f"shows take {format_bytes(show_bytes)}")

    if not used_parts and capacity <= 0:
        return (
            "I cannot see file sizes yet, so I will not guess at disk. After the next sync "
            "I can tell you what the movies and shows actually weigh."
        )

    sentences: List[str] = []
    if capacity > 0:
        sentences.append(f"The disks hold {format_bytes(capacity)}.")
    if used_parts:
        used = "; ".join(used_parts)
        sentences.append(used[:1].upper() + used[1:] + ".")
    return " ".join(sentences)


def _title_label(row: Dict[str, Any]) -> str:
    title = str(row.get("title") or "Untitled").strip() or "Untitled"
    year = row.get("year")
    return f"{title} ({year})" if year else title


def gather_house_stats(
    db: Database,
    *,
    now: Optional[float] = None,
    settings: Optional[Settings] = None,
    capacity_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    """Unwatched hours, dead weight, and disk — the letter's facts."""
    ts = time.time() if now is None else float(now)
    stale_cutoff = ts - STALE_ADD_DAYS * 86400
    with db.connect() as conn:
        totals = conn.execute(
            """
            SELECT
              COUNT(*) AS total,
              SUM(CASE WHEN view_count IS NULL OR view_count = 0 THEN 1 ELSE 0 END) AS unwatched,
              COALESCE(SUM(CASE WHEN media_type = 'movie' THEN COALESCE(file_size, 0) ELSE 0 END), 0) AS movie_bytes,
              COALESCE(SUM(CASE WHEN media_type = 'show' THEN COALESCE(file_size, 0) ELSE 0 END), 0) AS show_item_bytes
            FROM library_items
            """
        ).fetchone()
        unwatched_ms = conn.execute(
            """
            SELECT COALESCE(SUM(duration_ms), 0) AS ms
            FROM library_items
            WHERE (view_count IS NULL OR view_count = 0)
              AND duration_ms IS NOT NULL
              AND duration_ms > 0
            """
        ).fetchone()
        episode_ms = None
        try:
            episode_ms = conn.execute(
                """
                SELECT COALESCE(SUM(duration_ms), 0) AS ms
                FROM library_episodes
                WHERE (view_count IS NULL OR view_count = 0)
                  AND duration_ms IS NOT NULL
                  AND duration_ms > 0
                """
            ).fetchone()
        except Exception:  # noqa: BLE001 — older fixtures may lack the table
            episode_ms = None
        episode_file_bytes = 0
        try:
            episode_file_row = conn.execute(
                """
                SELECT COALESCE(SUM(COALESCE(file_size, 0)), 0) AS bytes_on_disk
                FROM library_episodes
                """
            ).fetchone()
            episode_file_bytes = _as_int(
                episode_file_row["bytes_on_disk"] if episode_file_row else 0
            )
        except Exception:  # noqa: BLE001 — older fixtures may lack the table
            episode_file_bytes = 0
        dead_rows = conn.execute(
            """
            SELECT id, title, year, media_type, file_size, added_at, rating_key, tmdb_id
            FROM library_items
            WHERE (view_count IS NULL OR view_count = 0)
              AND added_at IS NOT NULL
              AND added_at < ?
            ORDER BY COALESCE(file_size, 0) DESC, title ASC
            LIMIT ?
            """,
            (stale_cutoff, DEAD_WEIGHT_LIMIT),
        ).fetchall()
        dead_summary = conn.execute(
            """
            SELECT
              COUNT(*) AS cnt,
              COALESCE(SUM(COALESCE(file_size, 0)), 0) AS bytes_on_disk
            FROM library_items
            WHERE (view_count IS NULL OR view_count = 0)
              AND added_at IS NOT NULL
              AND added_at < ?
            """,
            (stale_cutoff,),
        ).fetchone()

    total = _as_int(totals["total"] if totals else 0)
    unwatched = _as_int(totals["unwatched"] if totals else 0)
    movie_bytes = _as_int(totals["movie_bytes"] if totals else 0)
    show_item_bytes = _as_int(totals["show_item_bytes"] if totals else 0)
    # Show rows often hold a Plex metadata slice (or 0 after a show-level sync
    # overwrites the episode rollup). Prefer actual episode file bytes.
    show_bytes = max(episode_file_bytes, show_item_bytes)
    library_used_bytes = movie_bytes + show_bytes
    if capacity_bytes is not None:
        resolved_capacity = max(0, int(capacity_bytes))
    else:
        resolved_capacity = volume_capacity_bytes(settings)
    movie_ms = _as_int(unwatched_ms["ms"] if unwatched_ms else 0)
    show_episode_ms = _as_int(episode_ms["ms"] if episode_ms else 0)
    unwatched_ms_total = movie_ms + show_episode_ms
    dead_count = _as_int(dead_summary["cnt"] if dead_summary else 0)
    dead_bytes = _as_int(dead_summary["bytes_on_disk"] if dead_summary else 0)

    dead_weight: List[Dict[str, Any]] = []
    for row in dead_rows or []:
        dead_weight.append(
            {
                "id": _as_int(row["id"]),
                "title": str(row["title"] or "Untitled"),
                "year": _as_int(row["year"]) if row["year"] is not None else None,
                "media_type": str(row["media_type"] or "movie"),
                "file_size": _as_int(row["file_size"]),
                "added_at": float(row["added_at"]) if row["added_at"] else None,
                "rating_key": str(row["rating_key"]) if row["rating_key"] else None,
                "tmdb_id": _as_int(row["tmdb_id"]) if row["tmdb_id"] is not None else None,
                "label": _title_label(
                    {
                        "title": row["title"],
                        "year": row["year"],
                    }
                ),
            }
        )

    unwatched_pct = round((unwatched / total) * 100, 1) if total else 0.0
    return {
        "total": total,
        "unwatched_count": unwatched,
        "unwatched_pct": unwatched_pct,
        "unwatched_ms": unwatched_ms_total,
        "unwatched_hours_label": format_hours(unwatched_ms_total),
        "disk_bytes": library_used_bytes,
        "disk_label": format_bytes(library_used_bytes) if library_used_bytes else "",
        "library_used_bytes": library_used_bytes,
        "capacity_bytes": resolved_capacity,
        "capacity_label": format_bytes(resolved_capacity) if resolved_capacity else "",
        "movie_bytes": movie_bytes,
        "show_bytes": show_bytes,
        "movie_disk_label": format_bytes(movie_bytes) if movie_bytes else "",
        "show_disk_label": format_bytes(show_bytes) if show_bytes else "",
        "stale_add_days": STALE_ADD_DAYS,
        "dead_weight_count": dead_count,
        "dead_weight_bytes": dead_bytes,
        "dead_weight_label": format_bytes(dead_bytes) if dead_bytes else "no sized files yet",
        "dead_weight": dead_weight,
        "generated_at": ts,
    }


def _paragraphs_for(stats: Dict[str, Any]) -> List[Dict[str, str]]:
    total = int(stats.get("total") or 0)
    if total <= 0:
        return [
            {
                "kind": "empty",
                "text": (
                    "The house is quiet. There is no library index yet, so I cannot tell you "
                    "about unwatched hours or disk. Sync from Admin → Libraries when you are "
                    "ready. I will write again after that."
                ),
            }
        ]

    unwatched = int(stats.get("unwatched_count") or 0)
    hours = str(stats.get("unwatched_hours_label") or "no timed hours")
    pct = stats.get("unwatched_pct")
    if unwatched <= 0:
        watch_text = (
            "Every title on the shelves has been sat with at least once. That is rare. "
            "The house is not waiting — it is ready for a rewatch or a gift."
        )
    elif hours == "no timed hours":
        watch_text = (
            f"There are {unwatched} titles nobody has sat with yet"
            f"{f' — about {pct}% of the shelves' if total else ''}. "
            "I do not have runtimes for them yet, so I will not invent hours."
        )
    else:
        watch_text = (
            f"There are {hours} of film and television that have never been sat with — "
            f"{unwatched} title{'s' if unwatched != 1 else ''}"
            f"{f', about {pct}% of the shelves' if total else ''}. "
            "That is not a failure. It is inventory waiting for a night."
        )

    dead_count = int(stats.get("dead_weight_count") or 0)
    stale_days = int(stats.get("stale_add_days") or STALE_ADD_DAYS)
    heaviest = (stats.get("dead_weight") or [None])[0]
    if dead_count <= 0:
        dead_text = (
            f"Nothing has sat unwatched for more than {stale_days} days with weight on disk. "
            "The house is not carrying dead weight right now."
        )
    else:
        heaviest_bit = ""
        if isinstance(heaviest, dict) and heaviest.get("label"):
            size = format_bytes(int(heaviest.get("file_size") or 0))
            if int(heaviest.get("file_size") or 0) > 0:
                heaviest_bit = f" The heaviest is {heaviest['label']} at {size}."
            else:
                heaviest_bit = f" The longest-sitting is {heaviest['label']}."
        dead_text = (
            f"{dead_count} title{'s' if dead_count != 1 else ''} have been here more than "
            f"{stale_days} days with no play, taking {stats.get('dead_weight_label')}.{heaviest_bit} "
            "I will not send a fleet at them. If you want the house lighter, open Health "
            "and confirm each one."
        )

    disk_text = disk_sentence(stats)

    close = (
        "Nothing here changes on its own. Open Health when you want the house lighter, "
        "or Live to put something on air for the week."
    )
    return [
        {"kind": "hours", "text": watch_text},
        {"kind": "dead_weight", "text": dead_text},
        {"kind": "disk", "text": disk_text},
        {"kind": "close", "text": close},
    ]


def compose_weekly_letter(
    db: Database,
    *,
    now: Optional[float] = None,
    settings: Optional[Settings] = None,
    capacity_bytes: Optional[int] = None,
) -> Dict[str, Any]:
    """Owner letter: unwatched hours, dead weight, disk — story, not tiles."""
    stats = gather_house_stats(db, now=now, settings=settings, capacity_bytes=capacity_bytes)
    paragraphs = _paragraphs_for(stats)
    body = "\n\n".join(item["text"] for item in paragraphs)
    return {
        "title": LETTER_TITLE,
        "salutation": "Dear owner,",
        "signoff": "— your curator",
        "body": body,
        "paragraphs": paragraphs,
        "stats": stats,
        "generated_at": stats["generated_at"],
    }


# ---------------------------------------------------------------------------
# Weekly delivery (owner inbox, optional email)
# ---------------------------------------------------------------------------


def default_letter_settings() -> Dict[str, Any]:
    return {"weekly": True, "email": False, "last_week": ""}


def load_letter_settings(db: Database) -> Dict[str, Any]:
    """Owner toggles: weekly delivery on/off + opt-in email (default: inbox only)."""
    out = default_letter_settings()
    raw = db.get_config(LETTER_CONFIG_KEY) if hasattr(db, "get_config") else None
    if raw:
        try:
            stored = json.loads(raw)
        except (TypeError, ValueError):
            stored = {}
        if isinstance(stored, dict):
            if "weekly" in stored:
                out["weekly"] = bool(stored["weekly"])
            if "email" in stored:
                out["email"] = bool(stored["email"])
            out["last_week"] = str(stored.get("last_week") or "")
    return out


def save_letter_settings(
    db: Database,
    *,
    weekly: Optional[bool] = None,
    email: Optional[bool] = None,
    last_week: Optional[str] = None,
) -> Dict[str, Any]:
    current = load_letter_settings(db)
    if weekly is not None:
        current["weekly"] = bool(weekly)
    if email is not None:
        current["email"] = bool(email)
    if last_week is not None:
        current["last_week"] = str(last_week)
    db.set_config(LETTER_CONFIG_KEY, json.dumps(current, separators=(",", ":")))
    return current


def week_bucket(now: Optional[float] = None) -> str:
    ts = time.time() if now is None else float(now)
    iso = datetime.fromtimestamp(ts, tz=timezone.utc).isocalendar()
    return f"{iso[0]:04d}-W{iso[1]:02d}"


def _owners(db: Database) -> List[Dict[str, Any]]:
    owners = [
        u for u in db.list_users(limit=100) if u.get("role") == "owner" and not u.get("disabled")
    ]
    if not owners:
        owners = [u for u in db.list_users(limit=20) if not u.get("disabled")][:1]
    return owners


def deliver_weekly_letter(
    db: Database,
    settings: Settings,
    *,
    now: Optional[float] = None,
    force: bool = False,
) -> Dict[str, Any]:
    """Drop this week's letter in the owner inbox (and email it if opted in).

    The scheduler calls this with ``force=False``: it is a no-op when weekly
    delivery is off, when this ISO week was already sent, or when there is no
    library index yet. "Send now" from Admin passes ``force=True``.
    Email is only attempted when the owner opted in *and* outbound mail is
    configured; inbox delivery never depends on mail.
    """
    from projectionist.mail import MailSendError, mail_configured, send_mail
    from projectionist.notifications.service import resolve_notification_email

    state = load_letter_settings(db)
    bucket = week_bucket(now)
    result: Dict[str, Any] = {
        "delivered": 0,
        "emailed": 0,
        "week": bucket,
        "skipped": "",
    }
    if not force:
        if not state["weekly"]:
            result["skipped"] = "weekly_off"
            return result
        if state["last_week"] == bucket:
            result["skipped"] = "already_sent"
            return result
    letter = compose_weekly_letter(db, now=now, settings=settings)
    if not force and int(letter["stats"].get("total") or 0) <= 0:
        result["skipped"] = "empty_library"
        return result

    body = f"{letter['salutation']}\n\n{letter['body']}\n\n{letter['signoff']}"
    want_email = bool(state["email"]) and mail_configured(settings)
    for owner in _owners(db):
        user_id = str(owner["id"])
        note = db.create_notification(
            notification_id=str(uuid.uuid4()),
            user_id=user_id,
            kind="digest",
            title=letter["title"],
            body=body,
            payload={
                "newsletter": LETTER_NEWSLETTER_ID,
                "week": bucket,
                "paragraphs": letter["paragraphs"],
                "blurb": "Your weekly letter about the house.",
            },
            related_id=f"{LETTER_NEWSLETTER_ID}-{bucket}",
        )
        if note:
            result["delivered"] += 1
        if want_email:
            to_email = resolve_notification_email(owner)
            if to_email:
                try:
                    send_mail(
                        settings,
                        to_email=to_email,
                        subject=f"{letter['title']} — {bucket}",
                        body_text=body,
                    )
                    result["emailed"] += 1
                except MailSendError as exc:
                    logger.warning("Weekly letter email failed for %s: %s", user_id, exc)
                    result["email_error"] = str(exc)
    if not force and result["delivered"]:
        save_letter_settings(db, last_week=bucket)
    return result
