"""Member taste overrides, weekly rails, and engagement substrate (P3c)."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence

from ._shared import DEFAULT_LENS_ID


class EngagementMixin:
    # --- Member taste (overrides on top of lens_taste_profile) ---

    def get_user_taste_overrides(self, user_id: str) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT cluster_tag, weight, explicit_lock, last_updated
                FROM user_taste_profile
                WHERE user_id = ?
                ORDER BY weight DESC, cluster_tag ASC
                """,
                (user_id,),
            ).fetchall()
        return [
            {
                "cluster_tag": str(row["cluster_tag"]),
                "weight": float(row["weight"]),
                "explicit_lock": bool(int(row["explicit_lock"] or 0)),
                "last_updated": float(row["last_updated"]) if row["last_updated"] else None,
                "source": "user",
            }
            for row in rows
        ]

    def set_user_taste_weight(
        self,
        user_id: str,
        cluster_tag: str,
        weight: float,
        *,
        explicit_lock: Optional[bool] = None,
    ) -> Dict[str, Any]:
        tag = str(cluster_tag or "").strip().lower()
        if not tag:
            raise ValueError("cluster_tag is required")
        clamped = max(0.0, min(1.0, float(weight)))
        now = time.time()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM user_taste_profile WHERE user_id = ? AND cluster_tag = ?",
                (user_id, tag),
            ).fetchone()
            lock_value = (
                int(bool(explicit_lock))
                if explicit_lock is not None
                else (int(existing["explicit_lock"]) if existing else 1)
            )
            conn.execute(
                """
                INSERT INTO user_taste_profile (user_id, cluster_tag, weight, explicit_lock, last_updated)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, cluster_tag) DO UPDATE SET
                    weight = excluded.weight,
                    explicit_lock = excluded.explicit_lock,
                    last_updated = excluded.last_updated
                """,
                (user_id, tag, round(clamped, 4), lock_value, now),
            )
        return {
            "cluster_tag": tag,
            "weight": round(clamped, 4),
            "explicit_lock": bool(lock_value),
            "last_updated": now,
            "source": "user",
        }

    def delete_user_taste_weight(self, user_id: str, cluster_tag: str) -> bool:
        tag = str(cluster_tag or "").strip().lower()
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM user_taste_profile WHERE user_id = ? AND cluster_tag = ?",
                (user_id, tag),
            )
            return cur.rowcount > 0

    def get_effective_taste_profile(
        self,
        user_id: Optional[str] = None,
        *,
        lens_id: str = DEFAULT_LENS_ID,
        limit: int = 40,
    ) -> List[Dict[str, Any]]:
        """Merge lens taste with optional per-user overrides (user wins)."""
        lens_rows = self.get_lens_taste_profile(lens_id or DEFAULT_LENS_ID)
        merged: Dict[str, Dict[str, Any]] = {}
        for row in lens_rows:
            tag = str(row["cluster_tag"])
            merged[tag] = {
                "cluster_tag": tag,
                "weight": float(row["weight"] or 0.5),
                "explicit_lock": bool(int(row["explicit_lock"] or 0)),
                "last_updated": str(row["last_updated"]) if row["last_updated"] else None,
                "source": "lens",
            }
        if user_id:
            for item in self.get_user_taste_overrides(user_id):
                merged[item["cluster_tag"]] = item
        ranked = sorted(
            merged.values(),
            key=lambda item: (abs(float(item["weight"]) - 0.5), item["cluster_tag"]),
            reverse=True,
        )
        return ranked[: max(1, int(limit))]

    # --- Weekly rails ---

    def save_user_weekly_rail(
        self,
        *,
        user_id: str,
        week_bucket: int,
        title: str,
        voice_line: str,
        items: Sequence[Dict[str, Any]],
        rail_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        rid = rail_id or uuid.uuid4().hex
        payload = json.dumps(list(items), separators=(",", ":"), sort_keys=True)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_weekly_rails (
                    id, user_id, week_bucket, title, voice_line, items_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, week_bucket) DO UPDATE SET
                    title = excluded.title,
                    voice_line = excluded.voice_line,
                    items_json = excluded.items_json,
                    created_at = excluded.created_at
                """,
                (rid, user_id, int(week_bucket), title, voice_line, payload, now),
            )
            row = conn.execute(
                """
                SELECT * FROM user_weekly_rails
                WHERE user_id = ? AND week_bucket = ?
                """,
                (user_id, int(week_bucket)),
            ).fetchone()
        assert row is not None
        return self._row_to_weekly_rail(row)

    def get_latest_user_weekly_rail(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM user_weekly_rails
                WHERE user_id = ?
                ORDER BY week_bucket DESC
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_weekly_rail(row)

    def _row_to_weekly_rail(self, row: sqlite3.Row) -> Dict[str, Any]:
        try:
            items = json.loads(row["items_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            items = []
        if not isinstance(items, list):
            items = []
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "week_bucket": int(row["week_bucket"]),
            "title": str(row["title"] or "For you this week"),
            "voice_line": str(row["voice_line"] or ""),
            "items": items,
            "created_at": float(row["created_at"]),
        }

    # --- Engagement: badges / streaks / challenges / explainers / courses ---

    def list_engagement_badges(self, *, youth_safe_only: bool = False) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            if youth_safe_only:
                rows = conn.execute(
                    "SELECT * FROM engagement_badges WHERE youth_safe = 1 ORDER BY name ASC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM engagement_badges ORDER BY name ASC"
                ).fetchall()
        return [self._row_to_badge(row) for row in rows]

    def list_user_badges(self, user_id: str) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT b.*, ub.earned_at
                FROM user_badges ub
                JOIN engagement_badges b ON b.id = ub.badge_id
                WHERE ub.user_id = ?
                ORDER BY ub.earned_at DESC
                """,
                (user_id,),
            ).fetchall()
        out = []
        for row in rows:
            badge = self._row_to_badge(row)
            badge["earned_at"] = float(row["earned_at"])
            out.append(badge)
        return out

    def award_badge(self, user_id: str, badge_id: str) -> bool:
        now = time.time()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO user_badges (user_id, badge_id, earned_at)
                VALUES (?, ?, ?)
                """,
                (user_id, badge_id, now),
            )
            return cur.rowcount > 0

    def get_user_streak(self, user_id: str, streak_kind: str = "chat") -> Dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM user_streaks
                WHERE user_id = ? AND streak_kind = ?
                """,
                (user_id, streak_kind),
            ).fetchone()
        if row is None:
            return {
                "user_id": user_id,
                "streak_kind": streak_kind,
                "current_count": 0,
                "best_count": 0,
                "last_event_at": None,
            }
        return {
            "user_id": str(row["user_id"]),
            "streak_kind": str(row["streak_kind"]),
            "current_count": int(row["current_count"] or 0),
            "best_count": int(row["best_count"] or 0),
            "last_event_at": float(row["last_event_at"]) if row["last_event_at"] else None,
        }

    def touch_user_streak(self, user_id: str, streak_kind: str = "chat") -> Dict[str, Any]:
        """Increment streak when last event was yesterday; reset if older; no-op same day."""
        now = time.time()
        day = int(now // 86400)
        current = self.get_user_streak(user_id, streak_kind)
        last = current.get("last_event_at")
        last_day = int(last // 86400) if last else None
        if last_day == day:
            return current
        if last_day == day - 1:
            count = int(current["current_count"]) + 1
        else:
            count = 1
        best = max(int(current["best_count"]), count)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_streaks (user_id, streak_kind, current_count, best_count, last_event_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, streak_kind) DO UPDATE SET
                    current_count = excluded.current_count,
                    best_count = excluded.best_count,
                    last_event_at = excluded.last_event_at
                """,
                (user_id, streak_kind, count, best, now),
            )
        return self.get_user_streak(user_id, streak_kind)

    def list_engagement_challenges(
        self, *, active_only: bool = True, youth_safe_only: bool = False
    ) -> List[Dict[str, Any]]:
        clauses = []
        if active_only:
            clauses.append("active = 1")
        if youth_safe_only:
            clauses.append("youth_safe = 1")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM engagement_challenges {where} ORDER BY target_count ASC, title ASC"
            ).fetchall()
        return [self._row_to_challenge(row) for row in rows]

    def get_user_challenge_progress(self, user_id: str) -> List[Dict[str, Any]]:
        challenges = self.list_engagement_challenges(active_only=True)
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM user_challenge_progress WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        by_id = {str(row["challenge_id"]): row for row in rows}
        out = []
        for challenge in challenges:
            row = by_id.get(challenge["id"])
            progress = int(row["progress"]) if row else 0
            out.append(
                {
                    **challenge,
                    "progress": progress,
                    "completed_at": float(row["completed_at"]) if row and row["completed_at"] else None,
                    "updated_at": float(row["updated_at"]) if row else None,
                }
            )
        return out

    def set_challenge_progress(
        self, user_id: str, challenge_id: str, progress: int
    ) -> Dict[str, Any]:
        now = time.time()
        with self.connect() as conn:
            challenge = conn.execute(
                "SELECT * FROM engagement_challenges WHERE id = ?",
                (challenge_id,),
            ).fetchone()
            if challenge is None:
                raise ValueError(f"Unknown challenge: {challenge_id}")
            target = int(challenge["target_count"] or 1)
            clamped = max(0, int(progress))
            completed = now if clamped >= target else None
            conn.execute(
                """
                INSERT INTO user_challenge_progress (
                    user_id, challenge_id, progress, completed_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, challenge_id) DO UPDATE SET
                    progress = excluded.progress,
                    completed_at = COALESCE(user_challenge_progress.completed_at, excluded.completed_at),
                    updated_at = excluded.updated_at
                """,
                (user_id, challenge_id, clamped, completed, now),
            )
        items = self.get_user_challenge_progress(user_id)
        for item in items:
            if item["id"] == challenge_id:
                return item
        raise ValueError(f"Unknown challenge: {challenge_id}")

    def list_engagement_explainers(self, *, youth_safe_only: bool = False) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            if youth_safe_only:
                rows = conn.execute(
                    "SELECT * FROM engagement_explainers WHERE youth_safe = 1 ORDER BY title ASC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM engagement_explainers ORDER BY title ASC"
                ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "slug": str(row["slug"]),
                "title": str(row["title"]),
                "body_md": str(row["body_md"] or ""),
                "related_tag": row["related_tag"],
                "youth_safe": bool(int(row["youth_safe"] or 0)),
                "created_at": float(row["created_at"]),
            }
            for row in rows
        ]

    def get_course_progress(self, user_id: str, list_id: str) -> Dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM user_course_progress
                WHERE user_id = ? AND list_id = ?
                """,
                (user_id, list_id),
            ).fetchone()
        if row is None:
            return {
                "user_id": user_id,
                "list_id": list_id,
                "position": 0,
                "completed_at": None,
                "updated_at": None,
            }
        return {
            "user_id": str(row["user_id"]),
            "list_id": str(row["list_id"]),
            "position": int(row["position"] or 0),
            "completed_at": float(row["completed_at"]) if row["completed_at"] else None,
            "updated_at": float(row["updated_at"]) if row["updated_at"] else None,
        }

    def set_course_progress(
        self,
        user_id: str,
        list_id: str,
        position: int,
        *,
        completed: bool = False,
    ) -> Dict[str, Any]:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO user_course_progress (
                    user_id, list_id, position, completed_at, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, list_id) DO UPDATE SET
                    position = excluded.position,
                    completed_at = CASE
                        WHEN excluded.completed_at IS NOT NULL THEN excluded.completed_at
                        ELSE user_course_progress.completed_at
                    END,
                    updated_at = excluded.updated_at
                """,
                (user_id, list_id, max(0, int(position)), now if completed else None, now),
            )
        return self.get_course_progress(user_id, list_id)

    def list_user_course_progress(self, user_id: str) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM user_course_progress
                WHERE user_id = ?
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()
        return [
            {
                "user_id": str(row["user_id"]),
                "list_id": str(row["list_id"]),
                "position": int(row["position"] or 0),
                "completed_at": float(row["completed_at"]) if row["completed_at"] else None,
                "updated_at": float(row["updated_at"]) if row["updated_at"] else None,
            }
            for row in rows
        ]

    def count_user_reviews(self, user_id: str) -> int:
        with self.connect() as conn:
            # Reviews may be global in single-user; prefer user-scoped when column exists.
            cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(user_title_reviews)").fetchall()}
            if "user_id" in cols:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM user_title_reviews WHERE user_id = ? AND stars IS NOT NULL",
                    (user_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM user_title_reviews WHERE stars IS NOT NULL"
                ).fetchone()
        return int(row["c"] if row else 0)

    def _row_to_badge(self, row: sqlite3.Row) -> Dict[str, Any]:
        try:
            criteria = json.loads(row["criteria_json"] or "{}")
        except (json.JSONDecodeError, TypeError):
            criteria = {}
        return {
            "id": str(row["id"]),
            "slug": str(row["slug"]),
            "name": str(row["name"]),
            "description": str(row["description"] or ""),
            "criteria": criteria if isinstance(criteria, dict) else {},
            "youth_safe": bool(int(row["youth_safe"] or 0)),
            "created_at": float(row["created_at"]),
        }

    def _row_to_challenge(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": str(row["id"]),
            "slug": str(row["slug"]),
            "kind": str(row["kind"]),
            "title": str(row["title"]),
            "description": str(row["description"] or ""),
            "target_count": int(row["target_count"] or 0),
            "youth_safe": bool(int(row["youth_safe"] or 0)),
            "active": bool(int(row["active"] or 0)),
            "created_at": float(row["created_at"]),
        }
