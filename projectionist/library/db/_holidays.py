"""SQLite persistence for the household holiday calendar + rail curation."""

from __future__ import annotations

import json
import time
import uuid
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence

from projectionist.library.holidays import (
    DEFAULT_OBSERVANCES,
    grounding_date_for,
    normalize_search_terms,
    upcoming_windows,
)


def _new_id(prefix: str = "hol") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class HolidaysMixin:
    """CRUD for holiday observances and per-scope rail title curation."""

    def ensure_holiday_defaults(self) -> int:
        """Seed builtin observances when the table is empty. Returns inserted count."""

        def _write() -> int:
            with self.connect() as conn:
                count_row = conn.execute("SELECT COUNT(*) AS c FROM holiday_observances").fetchone()
                if int(count_row["c"] or 0) > 0:
                    return 0
                now = time.time()
                inserted = 0
                for index, seed in enumerate(DEFAULT_OBSERVANCES):
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO holiday_observances (
                            id, name, kind, month, day, movable_rule,
                            pre_shoulder_days, post_shoulder_days, search_terms_json,
                            enabled, is_builtin, schedule_publish, sort_order,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?)
                        """,
                        (
                            seed["id"],
                            seed["name"],
                            seed["kind"],
                            seed.get("month"),
                            seed.get("day"),
                            seed.get("movable_rule"),
                            int(seed["pre_shoulder_days"]),
                            int(seed["post_shoulder_days"]),
                            json.dumps(list(seed["search_terms"])),
                            1 if seed.get("schedule_publish", True) else 0,
                            index,
                            now,
                            now,
                        ),
                    )
                    inserted += 1
                return inserted

        return int(self.run_write(_write, label="ensure_holiday_defaults") or 0)

    def restore_holiday_defaults(self) -> Dict[str, Any]:
        """Re-upsert builtin seeds (does not delete custom family observances)."""

        def _write() -> Dict[str, Any]:
            with self.connect() as conn:
                now = time.time()
                restored = 0
                for index, seed in enumerate(DEFAULT_OBSERVANCES):
                    conn.execute(
                        """
                        INSERT INTO holiday_observances (
                            id, name, kind, month, day, movable_rule,
                            pre_shoulder_days, post_shoulder_days, search_terms_json,
                            enabled, is_builtin, schedule_publish, sort_order,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            name = excluded.name,
                            kind = excluded.kind,
                            month = excluded.month,
                            day = excluded.day,
                            movable_rule = excluded.movable_rule,
                            pre_shoulder_days = excluded.pre_shoulder_days,
                            post_shoulder_days = excluded.post_shoulder_days,
                            search_terms_json = excluded.search_terms_json,
                            enabled = 1,
                            is_builtin = 1,
                            schedule_publish = excluded.schedule_publish,
                            sort_order = excluded.sort_order,
                            updated_at = excluded.updated_at
                        """,
                        (
                            seed["id"],
                            seed["name"],
                            seed["kind"],
                            seed.get("month"),
                            seed.get("day"),
                            seed.get("movable_rule"),
                            int(seed["pre_shoulder_days"]),
                            int(seed["post_shoulder_days"]),
                            json.dumps(list(seed["search_terms"])),
                            1 if seed.get("schedule_publish", True) else 0,
                            index,
                            now,
                            now,
                        ),
                    )
                    restored += 1
                return {"restored": restored, "custom_preserved": True}

        return self.run_write(_write, label="restore_holiday_defaults") or {
            "restored": 0,
            "custom_preserved": True,
        }

    def list_holiday_observances(self, *, include_disabled: bool = True) -> List[Dict[str, Any]]:
        self.ensure_holiday_defaults()
        with self.connect() as conn:
            if include_disabled:
                rows = conn.execute(
                    """
                    SELECT * FROM holiday_observances
                    ORDER BY sort_order ASC, name COLLATE NOCASE ASC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM holiday_observances
                    WHERE enabled = 1
                    ORDER BY sort_order ASC, name COLLATE NOCASE ASC
                    """
                ).fetchall()
        today = date.today()
        return [self._row_to_holiday(row, today=today) for row in rows]

    def get_holiday_observance(self, observance_id: str) -> Optional[Dict[str, Any]]:
        self.ensure_holiday_defaults()
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM holiday_observances WHERE id = ?",
                (observance_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_holiday(row, today=date.today())

    def create_holiday_observance(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        cleaned = self._validate_observance_payload(payload, partial=False)
        observance_id = str(payload.get("id") or "").strip() or _new_id("hol")

        def _write() -> Dict[str, Any]:
            with self.connect() as conn:
                existing = conn.execute(
                    "SELECT id FROM holiday_observances WHERE id = ?",
                    (observance_id,),
                ).fetchone()
                if existing is not None:
                    raise ValueError("A holiday with that id already exists")
                now = time.time()
                order_row = conn.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_pos FROM holiday_observances"
                ).fetchone()
                sort_order = int(order_row["next_pos"] or 0)
                conn.execute(
                    """
                    INSERT INTO holiday_observances (
                        id, name, kind, month, day, movable_rule,
                        pre_shoulder_days, post_shoulder_days, search_terms_json,
                        enabled, is_builtin, schedule_publish, sort_order,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                    """,
                    (
                        observance_id,
                        cleaned["name"],
                        cleaned["kind"],
                        cleaned.get("month"),
                        cleaned.get("day"),
                        cleaned.get("movable_rule"),
                        cleaned["pre_shoulder_days"],
                        cleaned["post_shoulder_days"],
                        json.dumps(cleaned["search_terms"]),
                        1 if cleaned["enabled"] else 0,
                        1 if cleaned["schedule_publish"] else 0,
                        sort_order,
                        now,
                        now,
                    ),
                )
            return self.get_holiday_observance(observance_id) or {}

        return self.run_write(_write, label="create_holiday_observance")

    def update_holiday_observance(
        self, observance_id: str, payload: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        existing = self.get_holiday_observance(observance_id)
        if existing is None:
            return None
        merged = {**existing, **payload, "id": observance_id}
        cleaned = self._validate_observance_payload(merged, partial=False)

        def _write() -> Optional[Dict[str, Any]]:
            with self.connect() as conn:
                row = conn.execute(
                    "SELECT id FROM holiday_observances WHERE id = ?",
                    (observance_id,),
                ).fetchone()
                if row is None:
                    return None
                now = time.time()
                conn.execute(
                    """
                    UPDATE holiday_observances SET
                        name = ?,
                        kind = ?,
                        month = ?,
                        day = ?,
                        movable_rule = ?,
                        pre_shoulder_days = ?,
                        post_shoulder_days = ?,
                        search_terms_json = ?,
                        enabled = ?,
                        schedule_publish = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        cleaned["name"],
                        cleaned["kind"],
                        cleaned.get("month"),
                        cleaned.get("day"),
                        cleaned.get("movable_rule"),
                        cleaned["pre_shoulder_days"],
                        cleaned["post_shoulder_days"],
                        json.dumps(cleaned["search_terms"]),
                        1 if cleaned["enabled"] else 0,
                        1 if cleaned["schedule_publish"] else 0,
                        now,
                        observance_id,
                    ),
                )
            return self.get_holiday_observance(observance_id)

        return self.run_write(_write, label="update_holiday_observance")

    def delete_holiday_observance(self, observance_id: str) -> bool:
        def _write() -> bool:
            with self.connect() as conn:
                row = conn.execute(
                    "SELECT id FROM holiday_observances WHERE id = ?",
                    (observance_id,),
                ).fetchone()
                if row is None:
                    return False
                conn.execute(
                    "DELETE FROM holiday_rail_titles WHERE scope_id = ?",
                    (observance_id,),
                )
                conn.execute(
                    "DELETE FROM holiday_observances WHERE id = ?",
                    (observance_id,),
                )
                return True

        return bool(self.run_write(_write, label="delete_holiday_observance"))

    def list_holiday_rail_titles(self, scope_id: str) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT t.*, li.title AS library_title, li.year AS library_year,
                       li.media_type AS library_media_type, li.poster_url AS library_poster_url
                FROM holiday_rail_titles t
                LEFT JOIN library_items li ON li.id = t.library_item_id
                WHERE t.scope_id = ?
                ORDER BY
                    CASE t.curation WHEN 'pin' THEN 0 WHEN 'include' THEN 1 ELSE 2 END,
                    t.pin_position ASC,
                    t.created_at ASC
                """,
                (scope_id,),
            ).fetchall()
        return [self._row_to_rail_title(row) for row in rows]

    def set_holiday_rail_title(
        self,
        scope_id: str,
        library_item_id: int,
        *,
        curation: str,
        pin_position: Optional[int] = None,
    ) -> Dict[str, Any]:
        role = str(curation or "").strip().lower()
        if role not in {"pin", "include", "exclude"}:
            raise ValueError("curation must be pin, include, or exclude")
        item_id = int(library_item_id)

        def _write() -> Dict[str, Any]:
            with self.connect() as conn:
                lib = conn.execute(
                    "SELECT id FROM library_items WHERE id = ?",
                    (item_id,),
                ).fetchone()
                if lib is None:
                    raise ValueError("Library title not found")
                now = time.time()
                position = pin_position
                if role == "pin" and position is None:
                    pos_row = conn.execute(
                        """
                        SELECT COALESCE(MAX(pin_position), -1) + 1 AS next_pos
                        FROM holiday_rail_titles
                        WHERE scope_id = ? AND curation = 'pin'
                        """,
                        (scope_id,),
                    ).fetchone()
                    position = int(pos_row["next_pos"] or 0)
                if role != "pin":
                    position = None
                conn.execute(
                    """
                    INSERT INTO holiday_rail_titles (
                        scope_id, library_item_id, curation, pin_position, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(scope_id, library_item_id) DO UPDATE SET
                        curation = excluded.curation,
                        pin_position = excluded.pin_position
                    """,
                    (scope_id, item_id, role, position, now),
                )
            titles = self.list_holiday_rail_titles(scope_id)
            for title in titles:
                if int(title["library_item_id"]) == item_id:
                    return title
            raise ValueError("Could not save rail title curation")

        return self.run_write(_write, label="set_holiday_rail_title")

    def clear_holiday_rail_title(self, scope_id: str, library_item_id: int) -> bool:
        def _write() -> bool:
            with self.connect() as conn:
                cur = conn.execute(
                    """
                    DELETE FROM holiday_rail_titles
                    WHERE scope_id = ? AND library_item_id = ?
                    """,
                    (scope_id, int(library_item_id)),
                )
                return cur.rowcount > 0

        return bool(self.run_write(_write, label="clear_holiday_rail_title"))

    def reorder_holiday_rail_pins(self, scope_id: str, library_item_ids: Sequence[int]) -> List[Dict[str, Any]]:
        ordered = [int(item_id) for item_id in library_item_ids]

        def _write() -> List[Dict[str, Any]]:
            with self.connect() as conn:
                for index, item_id in enumerate(ordered):
                    conn.execute(
                        """
                        UPDATE holiday_rail_titles
                        SET curation = 'pin', pin_position = ?
                        WHERE scope_id = ? AND library_item_id = ?
                        """,
                        (index, scope_id, item_id),
                    )
            return self.list_holiday_rail_titles(scope_id)

        return self.run_write(_write, label="reorder_holiday_rail_pins") or []

    def holiday_rail_curation_maps(self, scope_id: str) -> Dict[str, Any]:
        """Return pin/include/exclude id lists for feed composition."""
        titles = self.list_holiday_rail_titles(scope_id)
        pins: List[int] = []
        includes: List[int] = []
        excludes: List[int] = []
        for title in titles:
            item_id = int(title["library_item_id"])
            role = title["curation"]
            if role == "pin":
                pins.append(item_id)
            elif role == "include":
                includes.append(item_id)
            elif role == "exclude":
                excludes.append(item_id)
        return {"pins": pins, "includes": includes, "excludes": excludes}

    def get_library_items_by_ids(self, item_ids: Sequence[int]) -> Dict[int, Any]:
        ids = [int(item_id) for item_id in item_ids]
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM library_items WHERE id IN ({placeholders})",
                tuple(ids),
            ).fetchall()
        return {int(row["id"]): row for row in rows}

    def list_holiday_schedule(self, *, horizon_days: int = 60) -> List[Dict[str, Any]]:
        observances = self.list_holiday_observances(include_disabled=False)
        return upcoming_windows(observances, date.today(), horizon_days=horizon_days)

    def save_seasonal_rail_snapshot(
        self,
        *,
        snapshot_date: str,
        scope_id: str,
        label: str,
        mode: str,
        items: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """B2: materialize today's seasonal rail for stable Explore reads."""

        def _write() -> Dict[str, Any]:
            now = time.time()
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO seasonal_rail_snapshots (
                        snapshot_date, scope_id, label, mode, items_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(snapshot_date) DO UPDATE SET
                        scope_id = excluded.scope_id,
                        label = excluded.label,
                        mode = excluded.mode,
                        items_json = excluded.items_json,
                        created_at = excluded.created_at
                    """,
                    (
                        snapshot_date,
                        scope_id,
                        label,
                        mode,
                        json.dumps(list(items)),
                        now,
                    ),
                )
            return {
                "snapshot_date": snapshot_date,
                "scope_id": scope_id,
                "label": label,
                "mode": mode,
                "item_count": len(items),
            }

        return self.run_write(_write, label="save_seasonal_rail_snapshot") or {}

    def get_seasonal_rail_snapshot(self, snapshot_date: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM seasonal_rail_snapshots WHERE snapshot_date = ?",
                (snapshot_date,),
            ).fetchone()
        if row is None:
            return None
        try:
            items = json.loads(str(row["items_json"] or "[]"))
        except (TypeError, ValueError):
            items = []
        if not isinstance(items, list):
            items = []
        return {
            "snapshot_date": str(row["snapshot_date"]),
            "scope_id": str(row["scope_id"]),
            "label": str(row["label"] or ""),
            "mode": str(row["mode"] or ""),
            "items": items,
            "created_at": float(row["created_at"] or 0),
        }

    def _validate_observance_payload(self, payload: Mapping[str, Any], *, partial: bool) -> Dict[str, Any]:
        del partial  # full merge expected from callers
        name = str(payload.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        kind = str(payload.get("kind") or "fixed").strip().lower()
        if kind not in {"fixed", "movable"}:
            raise ValueError("kind must be fixed or movable")
        month = payload.get("month")
        day = payload.get("day")
        movable_rule = payload.get("movable_rule")
        if kind == "fixed":
            try:
                month_i = int(month)
                day_i = int(day)
                date(2024 if month_i != 2 or day_i != 29 else 2024, month_i, day_i)
            except (TypeError, ValueError):
                raise ValueError("fixed holidays need a valid month and day") from None
            movable_rule = None
        else:
            rule = str(movable_rule or "").strip().lower()
            if rule not in {"arbor_day", "labor_day", "thanksgiving"}:
                raise ValueError("movable_rule must be arbor_day, labor_day, or thanksgiving")
            month_i = None
            day_i = None
            movable_rule = rule
        try:
            pre = int(payload.get("pre_shoulder_days", 7))
            post = int(payload.get("post_shoulder_days", 7))
        except (TypeError, ValueError) as exc:
            raise ValueError("pre/post shoulder days must be integers") from exc
        if pre < 0 or post < 0 or pre > 90 or post > 90:
            raise ValueError("shoulder days must be between 0 and 90")
        terms = normalize_search_terms(payload.get("search_terms"))
        if not terms:
            raise ValueError("at least one search/filter term is required")
        enabled = bool(payload.get("enabled", True))
        schedule_publish = bool(payload.get("schedule_publish", True))
        return {
            "name": name,
            "kind": kind,
            "month": month_i,
            "day": day_i,
            "movable_rule": movable_rule,
            "pre_shoulder_days": pre,
            "post_shoulder_days": post,
            "search_terms": terms,
            "enabled": enabled,
            "schedule_publish": schedule_publish,
        }

    def _row_to_holiday(self, row, *, today: date) -> Dict[str, Any]:
        try:
            terms = json.loads(str(row["search_terms_json"] or "[]"))
        except (TypeError, ValueError):
            terms = []
        if not isinstance(terms, list):
            terms = []
        payload = {
            "id": str(row["id"]),
            "name": str(row["name"] or ""),
            "kind": str(row["kind"] or "fixed"),
            "month": int(row["month"]) if row["month"] is not None else None,
            "day": int(row["day"]) if row["day"] is not None else None,
            "movable_rule": str(row["movable_rule"]) if row["movable_rule"] else None,
            "pre_shoulder_days": int(row["pre_shoulder_days"] or 0),
            "post_shoulder_days": int(row["post_shoulder_days"] or 0),
            "search_terms": [str(t).strip() for t in terms if str(t).strip()],
            "enabled": bool(row["enabled"]),
            "is_builtin": bool(row["is_builtin"]),
            "schedule_publish": bool(row["schedule_publish"]),
            "sort_order": int(row["sort_order"] or 0),
            "created_at": float(row["created_at"] or 0),
            "updated_at": float(row["updated_at"] or 0),
        }
        try:
            grounding = grounding_date_for(payload, today.year)
            payload["grounding_date"] = grounding.isoformat()
            payload["grounding_date_label"] = (
                f"{grounding.strftime('%b')} {grounding.day}, {grounding.year}"
            )
        except (TypeError, ValueError):
            payload["grounding_date"] = None
            payload["grounding_date_label"] = None
        return payload

    def _row_to_rail_title(self, row) -> Dict[str, Any]:
        return {
            "scope_id": str(row["scope_id"]),
            "library_item_id": int(row["library_item_id"]),
            "curation": str(row["curation"]),
            "pin_position": int(row["pin_position"]) if row["pin_position"] is not None else None,
            "created_at": float(row["created_at"] or 0),
            "title": str(row["library_title"] or ""),
            "year": int(row["library_year"]) if row["library_year"] is not None else None,
            "media_type": str(row["library_media_type"] or ""),
            "poster_url": str(row["library_poster_url"] or "") if "library_poster_url" in row.keys() else "",
        }
