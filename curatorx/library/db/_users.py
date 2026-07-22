"""Users, auth, watchlist-sync prefs, message feedback, connection.

Behavior-preserving split of the original ``curatorx.library.db`` module: this
mixin carries a verbatim cluster of ``Database`` methods. Composed back into the
single ``Database`` class in ``curatorx/library/db/__init__.py``.
"""

from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from typing import (
    Any,
    Dict,
    Generator,
    List,
    Optional,
)

from ._shared import (
    SQLITE_BUSY_TIMEOUT_MS,
    SQLITE_SYNCHRONOUS,
    _optional_int_col,
    run_with_db_lock_retry,
)


class UsersAuthMixin:
    def get_user(self, user_id: str) -> Optional[sqlite3.Row]:
        def _read() -> Optional[sqlite3.Row]:
            with self.connect() as conn:
                return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

        return run_with_db_lock_retry(_read, label="get_user")

    def get_user_by_plex_id(self, plex_user_id: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE plex_user_id = ?",
                (plex_user_id,),
            ).fetchone()

    def count_users_with_role(self, role: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM users WHERE role = ?",
                (role,),
            ).fetchone()
            return int(row["count"] or 0) if row else 0

    def count_users_with_plex_id(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS count FROM users WHERE plex_user_id IS NOT NULL",
            ).fetchone()
            return int(row["count"] or 0) if row else 0

    def upsert_plex_user(
        self,
        *,
        user_id: str,
        display_name: str,
        email: Optional[str],
        plex_user_id: str,
        role: str,
        avatar_url: Optional[str] = None,
        seerr_user_id: Optional[int] = None,
        seerr_permissions: Optional[int] = None,
    ) -> Dict[str, Any]:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, display_name, email, role, plex_user_id, avatar_url,
                    seerr_user_id, seerr_permissions, created_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(plex_user_id) DO UPDATE SET
                    display_name = excluded.display_name,
                    email = excluded.email,
                    avatar_url = excluded.avatar_url,
                    seerr_user_id = COALESCE(excluded.seerr_user_id, users.seerr_user_id),
                    seerr_permissions = COALESCE(excluded.seerr_permissions, users.seerr_permissions),
                    last_login_at = excluded.last_login_at
                """,
                (
                    user_id,
                    display_name,
                    email,
                    role,
                    plex_user_id,
                    avatar_url,
                    seerr_user_id,
                    seerr_permissions,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM users WHERE plex_user_id = ?", (plex_user_id,)).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def list_users(self, *, limit: int = 100) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM users ORDER BY created_at ASC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_user(row) for row in rows]

    def update_user_role(self, user_id: str, role: str) -> Dict[str, Any]:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def set_user_disabled(self, user_id: str, disabled: bool) -> Dict[str, Any]:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            conn.execute(
                "UPDATE users SET disabled = ? WHERE id = ?",
                (1 if disabled else 0, user_id),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def delete_user(self, user_id: str) -> None:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            conn.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def update_user_seerr(
        self,
        user_id: str,
        *,
        seerr_user_id: int,
        seerr_permissions: Optional[int] = None,
    ) -> Dict[str, Any]:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            conn.execute(
                """
                UPDATE users
                SET seerr_user_id = ?, seerr_permissions = ?
                WHERE id = ?
                """,
                (seerr_user_id, seerr_permissions, user_id),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def update_user_profile(
        self,
        user_id: str,
        *,
        preferred_name: Any = ...,
        ui_font_size: Any = ...,
        ui_theme: Any = ...,
        avatar_url: Any = ...,
        notification_email: Any = ...,
        notify_channel_inbox: Any = ...,
        notify_channel_email: Any = ...,
        newsletter_opt_in: Any = ...,
        nudge_opt_in: Any = ...,
    ) -> Dict[str, Any]:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            cols = self._table_columns(conn, "users")
            updates: List[str] = []
            params: List[Any] = []
            if preferred_name is not ...:
                cleaned = (preferred_name or "").strip() or None
                updates.append("preferred_name = ?")
                params.append(cleaned)
            if ui_font_size is not ...:
                cleaned_font = str(ui_font_size or "medium").strip().lower()
                if cleaned_font not in {"small", "medium", "large"}:
                    cleaned_font = "medium"
                if "ui_font_size" in cols:
                    updates.append("ui_font_size = ?")
                    params.append(cleaned_font)
            if ui_theme is not ...:
                cleaned_theme = str(ui_theme or "system").strip().lower()
                if cleaned_theme not in {"lights_up", "lights_down", "system"}:
                    cleaned_theme = "system"
                if "ui_theme" in cols:
                    updates.append("ui_theme = ?")
                    params.append(cleaned_theme)
            if avatar_url is not ... and "avatar_url" in cols:
                cleaned_avatar = (avatar_url or "").strip() or None
                updates.append("avatar_url = ?")
                params.append(cleaned_avatar)
            if notification_email is not ... and "notification_email" in cols:
                cleaned_email = (notification_email or "").strip() or None
                if cleaned_email and "@" not in cleaned_email:
                    cleaned_email = None
                updates.append("notification_email = ?")
                params.append(cleaned_email)
            if notify_channel_inbox is not ... and "notify_channel_inbox" in cols:
                updates.append("notify_channel_inbox = ?")
                params.append(1 if notify_channel_inbox else 0)
            if notify_channel_email is not ... and "notify_channel_email" in cols:
                updates.append("notify_channel_email = ?")
                params.append(1 if notify_channel_email else 0)
            if newsletter_opt_in is not ... and "newsletter_opt_in" in cols:
                updates.append("newsletter_opt_in = ?")
                params.append(1 if newsletter_opt_in else 0)
            if nudge_opt_in is not ... and "nudge_opt_in" in cols:
                updates.append("nudge_opt_in = ?")
                params.append(1 if nudge_opt_in else 0)
            if updates:
                params.append(user_id)
                conn.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                    tuple(params),
                )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def create_local_user(
        self,
        *,
        user_id: str,
        display_name: str,
        password_hash: str,
        role: str = "member",
        email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a user who authenticates via local password."""
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, display_name, email, role, password_hash, auth_method,
                    created_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, 'local', ?, ?)
                """,
                (user_id, display_name, email, role, password_hash, now, now),
            )
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def get_user_by_display_name(self, display_name: str) -> Optional[sqlite3.Row]:
        """Look up a local user by display_name (used as username for local auth)."""
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE display_name = ? AND auth_method = 'local'",
                (display_name,),
            ).fetchone()

    def upsert_oidc_user(
        self,
        *,
        oidc_sub: str,
        display_name: str,
        email: Optional[str] = None,
        role: str = "member",
    ) -> Dict[str, Any]:
        """Create or update a user identified by OIDC subject claim."""
        now = time.time()
        user_id = f"oidc-{oidc_sub}"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    id, display_name, email, role, oidc_sub, auth_method,
                    created_at, last_login_at
                ) VALUES (?, ?, ?, ?, ?, 'oidc', ?, ?)
                ON CONFLICT(oidc_sub) DO UPDATE SET
                    display_name = excluded.display_name,
                    email = excluded.email,
                    last_login_at = excluded.last_login_at
                """,
                (user_id, display_name, email, role, oidc_sub, now, now),
            )
            row = conn.execute(
                "SELECT * FROM users WHERE oidc_sub = ?", (oidc_sub,)
            ).fetchone()
        assert row is not None
        return self._row_to_user(row)

    def get_user_by_oidc_sub(self, oidc_sub: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM users WHERE oidc_sub = ?", (oidc_sub,)
            ).fetchone()

    def set_user_plex_token_enc(self, user_id: str, token_enc: str) -> None:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            conn.execute(
                "UPDATE users SET plex_token_enc = ? WHERE id = ?",
                (token_enc, user_id),
            )

    def get_user_plex_token_enc(self, user_id: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT plex_token_enc FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
        if row is None or row["plex_token_enc"] is None:
            return None
        return str(row["plex_token_enc"])

    def get_watchlist_sync_prefs(self, user_id: str) -> Dict[str, Any]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            return {
                "watchlist_sync_enabled": True,
                "watchlist_pull_on_login": True,
                "watchlist_push_on_pin": True,
                "watchlist_last_synced_at": None,
            }
        keys = set(row.keys())
        return {
            "watchlist_sync_enabled": (
                bool(int(row["watchlist_sync_enabled"]))
                if "watchlist_sync_enabled" in keys and row["watchlist_sync_enabled"] is not None
                else True
            ),
            "watchlist_pull_on_login": (
                bool(int(row["watchlist_pull_on_login"]))
                if "watchlist_pull_on_login" in keys and row["watchlist_pull_on_login"] is not None
                else True
            ),
            "watchlist_push_on_pin": (
                bool(int(row["watchlist_push_on_pin"]))
                if "watchlist_push_on_pin" in keys and row["watchlist_push_on_pin"] is not None
                else True
            ),
            "watchlist_last_synced_at": (
                float(row["watchlist_last_synced_at"])
                if "watchlist_last_synced_at" in keys and row["watchlist_last_synced_at"] is not None
                else None
            ),
            "watchlist_last_pull_total": _optional_int_col(row, keys, "watchlist_last_pull_total"),
            "watchlist_last_pull_added": _optional_int_col(row, keys, "watchlist_last_pull_added"),
            "watchlist_last_pull_updated": _optional_int_col(row, keys, "watchlist_last_pull_updated"),
            "watchlist_last_pull_unresolved": _optional_int_col(
                row, keys, "watchlist_last_pull_unresolved"
            ),
        }

    def update_watchlist_sync_prefs(
        self,
        user_id: str,
        *,
        enabled: Optional[bool] = None,
        pull_on_login: Optional[bool] = None,
        push_on_pin: Optional[bool] = None,
    ) -> Dict[str, Any]:
        with self.connect() as conn:
            existing = conn.execute("SELECT id FROM users WHERE id = ?", (user_id,)).fetchone()
            if existing is None:
                raise ValueError("User not found")
            if enabled is not None:
                conn.execute(
                    "UPDATE users SET watchlist_sync_enabled = ? WHERE id = ?",
                    (1 if enabled else 0, user_id),
                )
            if pull_on_login is not None:
                conn.execute(
                    "UPDATE users SET watchlist_pull_on_login = ? WHERE id = ?",
                    (1 if pull_on_login else 0, user_id),
                )
            if push_on_pin is not None:
                conn.execute(
                    "UPDATE users SET watchlist_push_on_pin = ? WHERE id = ?",
                    (1 if push_on_pin else 0, user_id),
                )
        return self.get_watchlist_sync_prefs(user_id)

    def mark_watchlist_synced(
        self,
        user_id: str,
        *,
        synced_at: Optional[float] = None,
        pull_total: Optional[int] = None,
        pull_added: Optional[int] = None,
        pull_updated: Optional[int] = None,
        pull_unresolved: Optional[int] = None,
    ) -> None:
        stamp = time.time() if synced_at is None else float(synced_at)
        with self.connect() as conn:
            cols = self._table_columns(conn, "users")
            conn.execute(
                "UPDATE users SET watchlist_last_synced_at = ? WHERE id = ?",
                (stamp, user_id),
            )
            stat_updates = {
                "watchlist_last_pull_total": pull_total,
                "watchlist_last_pull_added": pull_added,
                "watchlist_last_pull_updated": pull_updated,
                "watchlist_last_pull_unresolved": pull_unresolved,
            }
            for column, value in stat_updates.items():
                if value is not None and column in cols:
                    conn.execute(
                        f"UPDATE users SET {column} = ? WHERE id = ?",
                        (int(value), user_id),
                    )

    def _row_to_user(self, row: sqlite3.Row) -> Dict[str, Any]:
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        preferred_name = None
        if "preferred_name" in keys and row["preferred_name"] is not None:
            preferred_name = str(row["preferred_name"])
        ui_font_size = "medium"
        if "ui_font_size" in keys and row["ui_font_size"] is not None:
            cleaned = str(row["ui_font_size"]).strip().lower()
            if cleaned in {"small", "medium", "large"}:
                ui_font_size = cleaned
        ui_theme = "system"
        if "ui_theme" in keys and row["ui_theme"] is not None:
            cleaned_theme = str(row["ui_theme"]).strip().lower()
            if cleaned_theme in {"lights_up", "lights_down", "system"}:
                ui_theme = cleaned_theme
        disabled = False
        if "disabled" in keys and row["disabled"] is not None:
            disabled = bool(int(row["disabled"]))
        is_youth = bool(int(row["is_youth"])) if "is_youth" in keys and row["is_youth"] is not None else False
        seerr_user_id = int(row["seerr_user_id"]) if row["seerr_user_id"] is not None else None
        notification_email = None
        if "notification_email" in keys and row["notification_email"] is not None:
            notification_email = str(row["notification_email"])
        notify_channel_inbox = True
        if "notify_channel_inbox" in keys and row["notify_channel_inbox"] is not None:
            notify_channel_inbox = bool(int(row["notify_channel_inbox"]))
        notify_channel_email = False
        if "notify_channel_email" in keys and row["notify_channel_email"] is not None:
            notify_channel_email = bool(int(row["notify_channel_email"]))
        newsletter_opt_in = False
        if "newsletter_opt_in" in keys and row["newsletter_opt_in"] is not None:
            newsletter_opt_in = bool(int(row["newsletter_opt_in"]))
        nudge_opt_in = False
        if "nudge_opt_in" in keys and row["nudge_opt_in"] is not None:
            nudge_opt_in = bool(int(row["nudge_opt_in"]))
        return {
            "id": str(row["id"]),
            "display_name": str(row["display_name"]),
            "preferred_name": preferred_name,
            "ui_font_size": ui_font_size,
            "ui_theme": ui_theme,
            "email": str(row["email"]) if row["email"] is not None else None,
            "notification_email": notification_email,
            "notify_channel_inbox": notify_channel_inbox,
            "notify_channel_email": notify_channel_email,
            "newsletter_opt_in": newsletter_opt_in,
            "nudge_opt_in": nudge_opt_in,
            "role": str(row["role"]),
            "disabled": disabled,
            "is_youth": is_youth,
            "plex_user_id": str(row["plex_user_id"]) if row["plex_user_id"] is not None else None,
            "seerr_user_id": seerr_user_id,
            "seerr_linked": seerr_user_id is not None,
            "seerr_permissions": int(row["seerr_permissions"]) if row["seerr_permissions"] is not None else None,
            "avatar_url": str(row["avatar_url"]) if row["avatar_url"] is not None else None,
            "has_plex_token": bool(
                "plex_token_enc" in keys and row["plex_token_enc"]
            ),
            "auth_method": str(row["auth_method"]) if "auth_method" in keys and row["auth_method"] is not None else "plex",
            "created_at": float(row["created_at"]),
            "last_login_at": float(row["last_login_at"]) if row["last_login_at"] is not None else None,
        }

    def get_chat_message(self, message_id: str) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()

    def upsert_message_feedback(
        self,
        *,
        feedback_id: str,
        message_id: str,
        session_id: str,
        user_id: Optional[str],
        feedback_type: str,
        excerpt: str,
    ) -> Dict[str, Any]:
        now = time.time()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO message_feedback (
                    id, message_id, session_id, user_id, feedback_type, excerpt, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id, user_id) DO UPDATE SET
                    feedback_type = excluded.feedback_type,
                    excerpt = excluded.excerpt,
                    created_at = excluded.created_at
                """,
                (feedback_id, message_id, session_id, user_id, feedback_type, excerpt, now),
            )
            row = conn.execute(
                """
                SELECT * FROM message_feedback
                WHERE message_id = ? AND (
                    (user_id IS NULL AND ? IS NULL) OR user_id = ?
                )
                """,
                (message_id, user_id, user_id),
            ).fetchone()
        assert row is not None
        return {
            "id": str(row["id"]),
            "message_id": str(row["message_id"]),
            "session_id": str(row["session_id"]),
            "user_id": str(row["user_id"]) if row["user_id"] is not None else None,
            "feedback": str(row["feedback_type"]),
            "excerpt": str(row["excerpt"] or ""),
            "created_at": float(row["created_at"]),
        }

    def list_message_feedback(
        self,
        session_id: str,
        *,
        user_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        with self.connect() as conn:
            if user_id is None:
                rows = conn.execute(
                    """
                    SELECT * FROM message_feedback
                    WHERE session_id = ? AND user_id IS NULL
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM message_feedback
                    WHERE session_id = ? AND user_id = ?
                    ORDER BY created_at ASC
                    """,
                    (session_id, user_id),
                ).fetchall()
        return [
            {
                "id": str(row["id"]),
                "message_id": str(row["message_id"]),
                "session_id": str(row["session_id"]),
                "user_id": str(row["user_id"]) if row["user_id"] is not None else None,
                "feedback": str(row["feedback_type"]),
                "excerpt": str(row["excerpt"] or ""),
                "created_at": float(row["created_at"]),
            }
            for row in rows
        ]

    def delete_message_feedback(
        self,
        message_id: str,
        *,
        user_id: Optional[str] = None,
    ) -> bool:
        with self.connect() as conn:
            if user_id is None:
                cursor = conn.execute(
                    """
                    DELETE FROM message_feedback
                    WHERE message_id = ? AND user_id IS NULL
                    """,
                    (message_id,),
                )
            else:
                cursor = conn.execute(
                    """
                    DELETE FROM message_feedback
                    WHERE message_id = ? AND user_id = ?
                    """,
                    (message_id, user_id),
                )
            return cursor.rowcount > 0

    def ensure_seed_data(self) -> None:
        with self.connect() as conn:
            self._seed_builtin_persona_templates(conn)
            self._seed_defaults(conn)

    def _open_connection(self) -> sqlite3.Connection:
        # timeout is seconds; check_same_thread=False allows FastAPI worker threads
        # to share Database instances (each call still gets its own connection).
        conn = sqlite3.connect(
            self.path,
            timeout=SQLITE_BUSY_TIMEOUT_MS / 1000.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {int(SQLITE_BUSY_TIMEOUT_MS)}")
        # WAL lets readers proceed while a writer commits; persistent on the DB file.
        conn.execute("PRAGMA journal_mode=WAL")
        # NORMAL with WAL is a common Unraid/NAS tradeoff: much less fsync cost than
        # FULL, with only a small window of loss on abrupt power failure mid-commit.
        conn.execute(f"PRAGMA synchronous={SQLITE_SYNCHRONOUS}")
        return conn

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = self._open_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise
        finally:
            conn.close()

