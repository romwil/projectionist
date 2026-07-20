"""Fail-closed access control for private Curator memory."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from curatorx.library.db import Database


class MemoryAccessError(PermissionError):
    """Raised before any private-memory data is returned to an unauthorized caller."""


class UserMemoryService:
    def __init__(self, db: Database) -> None:
        self.db = db

    def _authorize(self, *, caller_id: str, caller_role: str, target_id: str) -> None:
        if caller_id == target_id:
            return
        target = self.db.get_user(target_id)
        # Owner moderation is deliberately restricted to accounts explicitly in Youth mode.
        if caller_role == "owner" and target and bool(target["is_youth"]):
            return
        raise MemoryAccessError("Private memory is not available for this account")

    def recall(
        self, *, caller_id: str, caller_role: str, target_id: Optional[str] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        target = target_id or caller_id
        self._authorize(caller_id=caller_id, caller_role=caller_role, target_id=target)
        return self.db.list_user_memory_notes(target, limit=limit)

    def remember(self, *, caller_id: str, kind: str, text: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.db.add_user_memory_note(caller_id, kind=kind, text=text, metadata=metadata)

    def update(self, *, caller_id: str, caller_role: str, note_id: str, text: str, kind: Optional[str] = None) -> Optional[Dict[str, Any]]:
        note = self.db.get_user_memory_note(note_id, user_id=caller_id)
        if note is None:
            # Do not reveal whether another user's note exists.
            raise MemoryAccessError("Memory note is not available")
        self._authorize(caller_id=caller_id, caller_role=caller_role, target_id=caller_id)
        return self.db.update_user_memory_note(caller_id, note_id, text=text, kind=kind)
