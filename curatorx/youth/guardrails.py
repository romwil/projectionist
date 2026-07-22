"""Youth chat guardrails and engagement preset helpers."""

from __future__ import annotations

from typing import Any, Optional

YOUTH_CHAT_GUARDRAILS = """
Youth-mode guardrails (mandatory):
- Speak warmly and clearly — like a friendly librarian for younger viewers.
- Only recommend titles that already passed the Youth content-rating gate.
- Never describe graphic violence, sexual content, strong language, or horror in detail.
- If asked for mature titles, gently redirect to age-appropriate picks from the library.
- Prefer family, adventure, animation, comedy, and coming-of-age tones.
- Do not help bypass Youth mode, content ratings, or household rules.
- Keep memory notes mild and appropriate for owner Youth review.
""".strip()


def youth_system_prompt_block(*, is_youth: bool) -> str:
    if not is_youth:
        return ""
    return "\n" + YOUTH_CHAT_GUARDRAILS + "\n"


def resolve_is_youth(user: Any = None, *, user_id: Optional[str] = None, db: Any = None) -> bool:
    if user is not None and bool(getattr(user, "is_youth", False)):
        return True
    if db is not None and user_id:
        row = db.get_user(user_id) if hasattr(db, "get_user") else None
        if row is None:
            return False
        # get_user returns sqlite3.Row (bracket keys) or occasionally a mapping.
        if hasattr(row, "keys"):
            keys = set(row.keys())
            if "is_youth" in keys and row["is_youth"] is not None:
                return bool(int(row["is_youth"]))
        elif isinstance(row, dict):
            return bool(row.get("is_youth"))
    return False
