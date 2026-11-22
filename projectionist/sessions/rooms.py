"""Rooms: the household's named screens (SES-002).

A room is a paired screen. Handhelds are not rooms. The list is the name of
the screen. It does not say what is playing, or who is signed in on it.
"""

from __future__ import annotations

import re
from typing import Any

from projectionist.library.db._shared import begin_immediate

_DEVICE_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")

SCREEN_KIND = "tv"


class RoomError(Exception):
    def __init__(self, detail: str, *, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = int(status_code)


def room_name(raw: str) -> str:
    text = " ".join(str(raw or "").split())
    if not text:
        raise RoomError("A room needs a name.")
    return text[:40]


def _row_kind(row: Any) -> str:
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    if "kind" not in keys or row["kind"] is None or str(row["kind"]).strip() == "":
        return SCREEN_KIND
    return str(row["kind"])


def list_rooms(db: Any) -> list[dict[str, str]]:
    """Every signed-in member may read this. No playback, no person."""
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, label, kind
            FROM paired_devices
            WHERE revoked_at IS NULL
            ORDER BY label COLLATE NOCASE, id
            """
        ).fetchall()
    rooms: list[dict[str, str]] = []
    for row in rows:
        kind = _row_kind(row)
        if kind != SCREEN_KIND:
            continue
        rooms.append(
            {
                "id": str(row["id"]),
                "name": str(row["label"] or "Screen"),
                "kind": SCREEN_KIND,
            }
        )
    return rooms


def rename_room(db: Any, room_id: str, name: str, *, user_id: str, is_owner: bool) -> dict[str, str]:
    """The household owner, or the member signed in on that screen, may rename it."""
    device = str(room_id or "").strip().lower()
    if not _DEVICE_ID.match(device):
        raise RoomError("That room is not in this household.", status_code=404)
    cleaned = room_name(name)

    def _write() -> dict[str, str]:
        with db.connect() as conn:
            begin_immediate(conn)
            row = conn.execute(
                """
                SELECT id, user_id, label, kind, revoked_at
                FROM paired_devices
                WHERE id = ?
                """,
                (device,),
            ).fetchone()
            if row is None or row["revoked_at"] is not None or _row_kind(row) != SCREEN_KIND:
                raise RoomError("That room is not in this household.", status_code=404)
            if not is_owner and str(row["user_id"] or "") != str(user_id or ""):
                raise RoomError("Only the household owner can rename that room.", status_code=403)
            conn.execute(
                "UPDATE paired_devices SET label = ? WHERE id = ?",
                (cleaned, device),
            )
        return {"id": device, "name": cleaned, "kind": SCREEN_KIND}

    return db.run_write(_write, label="room_rename")
