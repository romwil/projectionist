"""Household invite tokens (invite-only join when multi-user is on)."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any, Dict, List, Optional

from ._shared import begin_immediate


INVITE_STATUSES = frozenset({"pending", "redeemed", "revoked"})
INVITE_ROLES = frozenset({"member"})
INVITE_METHODS = frozenset({"plex", "oidc", "local"})


class InviteConflict(ValueError):
    """Invite already used, or a concurrent redeem lost the write lock."""


class InvitesMixin:
    def create_invite(
        self,
        *,
        token_hash: str,
        created_by: str,
        role: str = "member",
        is_youth: bool = False,
        allowed_methods: Optional[List[str]] = None,
        expires_at: Optional[float] = None,
        email: Optional[str] = None,
        expected_plex_user_id: Optional[str] = None,
        expected_oidc_sub: Optional[str] = None,
        access_request_id: Optional[str] = None,
        invite_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        cleaned_role = str(role or "member").strip().lower()
        if cleaned_role not in INVITE_ROLES:
            raise ValueError("role must be member")
        methods = _normalize_methods(allowed_methods)
        email_clean = str(email or "").strip() or None
        plex_clean = str(expected_plex_user_id or "").strip() or None
        oidc_clean = str(expected_oidc_sub or "").strip() or None
        request_clean = str(access_request_id or "").strip() or None
        hash_clean = str(token_hash or "").strip()
        if not hash_clean:
            raise ValueError("token_hash is required")
        iid = invite_id or uuid.uuid4().hex
        now = time.time()
        exp = float(expires_at) if expires_at is not None else now + 7 * 24 * 3600
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO invites (
                    id, token_hash, expires_at, status, email,
                    expected_plex_user_id, expected_oidc_sub, role, is_youth,
                    allowed_methods, created_by, created_at,
                    redeemed_at, redeemed_user_id, access_request_id
                ) VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?)
                """,
                (
                    iid,
                    hash_clean,
                    exp,
                    email_clean,
                    plex_clean,
                    oidc_clean,
                    cleaned_role,
                    1 if is_youth else 0,
                    json.dumps(methods),
                    created_by,
                    now,
                    request_clean,
                ),
            )
            row = conn.execute("SELECT * FROM invites WHERE id = ?", (iid,)).fetchone()
        assert row is not None
        return self._row_to_invite(row)

    def get_invite(self, invite_id: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM invites WHERE id = ?",
                (invite_id,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_invite(row)

    def get_invite_by_token_hash(self, token_hash: str) -> Optional[Dict[str, Any]]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM invites WHERE token_hash = ?",
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_invite(row)

    def list_invites(
        self,
        *,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM invites"
        params: List[Any] = []
        cleaned = str(status or "").strip().lower()
        if cleaned:
            if cleaned not in INVITE_STATUSES:
                raise ValueError(f"Unsupported status: {status}")
            query += " WHERE status = ?"
            params.append(cleaned)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(max(1, min(int(limit), 200)))
        with self.connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [self._row_to_invite(row) for row in rows]

    def revoke_invite(self, invite_id: str, *, revoked_by: Optional[str] = None) -> Dict[str, Any]:
        del revoked_by  # reserved for audit; status alone is enough for v1
        now = time.time()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM invites WHERE id = ?",
                (invite_id,),
            ).fetchone()
            if existing is None:
                raise ValueError(f"Unknown invite: {invite_id}")
            if str(existing["status"]) != "pending":
                raise ValueError("Invite is not pending")
            conn.execute(
                "UPDATE invites SET status = 'revoked' WHERE id = ?",
                (invite_id,),
            )
            row = conn.execute("SELECT * FROM invites WHERE id = ?", (invite_id,)).fetchone()
        assert row is not None
        # Touch now so callers can distinguish revoke timing if needed later.
        _ = now
        return self._row_to_invite(row)

    def redeem_invite(
        self,
        invite_id: str,
        *,
        redeemed_user_id: str,
    ) -> Dict[str, Any]:
        now = time.time()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT * FROM invites WHERE id = ?",
                (invite_id,),
            ).fetchone()
            if existing is None:
                raise ValueError(f"Unknown invite: {invite_id}")
            if str(existing["status"]) != "pending":
                raise ValueError("Invite is not pending")
            if float(existing["expires_at"]) < now:
                raise ValueError("Invite has expired")
            conn.execute(
                """
                UPDATE invites
                SET status = 'redeemed', redeemed_at = ?, redeemed_user_id = ?
                WHERE id = ? AND status = 'pending'
                """,
                (now, redeemed_user_id, invite_id),
            )
            row = conn.execute("SELECT * FROM invites WHERE id = ?", (invite_id,)).fetchone()
        assert row is not None
        if str(row["status"]) != "redeemed":
            raise ValueError("Invite could not be redeemed")
        return self._row_to_invite(row)

    def create_local_user_and_redeem_invite(
        self,
        *,
        invite_id: str,
        user_id: str,
        display_name: str,
        password_hash: str,
        role: str,
        email: Optional[str] = None,
        is_youth: bool = False,
    ) -> Dict[str, Any]:
        """Insert a local user and burn the invite in one SQLite transaction."""
        now = time.time()
        try:
            with self.connect() as conn:
                begin_immediate(conn)
                conn.execute(
                    """
                    INSERT INTO users (
                        id, display_name, email, role, password_hash, auth_method,
                        created_at, last_login_at, is_youth
                    ) VALUES (?, ?, ?, ?, ?, 'local', ?, ?, ?)
                    """,
                    (
                        user_id,
                        display_name,
                        email,
                        role,
                        password_hash,
                        now,
                        now,
                        1 if is_youth else 0,
                    ),
                )
                cursor = conn.execute(
                    """
                    UPDATE invites
                    SET status = 'redeemed', redeemed_at = ?, redeemed_user_id = ?
                    WHERE id = ? AND status = 'pending' AND expires_at >= ?
                    """,
                    (now, user_id, invite_id, now),
                )
                if int(cursor.rowcount or 0) != 1:
                    raise InviteConflict("Invite has already been used")
                user_row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
                invite_row = conn.execute("SELECT * FROM invites WHERE id = ?", (invite_id,)).fetchone()
        except sqlite3.OperationalError as error:
            if "locked" in str(error).lower() or "busy" in str(error).lower():
                raise InviteConflict("Invite has already been used") from error
            raise
        assert user_row is not None and invite_row is not None
        return {"user": self._row_to_user(user_row), "invite": self._row_to_invite(invite_row)}

    def upsert_identity_and_redeem_invite(
        self,
        *,
        invite_id: str,
        method: str,
        user_id: str,
        display_name: str,
        email: Optional[str],
        role: str,
        plex_user_id: Optional[str] = None,
        oidc_sub: Optional[str] = None,
        avatar_url: Optional[str] = None,
        seerr_user_id: Optional[int] = None,
        seerr_permissions: Optional[int] = None,
        is_youth: bool = False,
    ) -> Dict[str, Any]:
        """Insert/upsert Plex or OIDC user and burn the invite in one transaction."""
        now = time.time()
        try:
            with self.connect() as conn:
                begin_immediate(conn)
                if plex_user_id:
                    conn.execute(
                        """
                        INSERT INTO users (
                            id, display_name, email, role, plex_user_id, avatar_url,
                            seerr_user_id, seerr_permissions, created_at, last_login_at,
                            is_youth
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                            1 if is_youth else 0,
                        ),
                    )
                    bound = conn.execute(
                        "SELECT * FROM users WHERE plex_user_id = ?",
                        (plex_user_id,),
                    ).fetchone()
                elif oidc_sub:
                    oidc_user_id = f"oidc-{oidc_sub}"
                    conn.execute(
                        """
                        INSERT INTO users (
                            id, display_name, email, role, oidc_sub, auth_method,
                            created_at, last_login_at, is_youth
                        ) VALUES (?, ?, ?, ?, ?, 'oidc', ?, ?, ?)
                        ON CONFLICT(oidc_sub) DO UPDATE SET
                            display_name = excluded.display_name,
                            email = excluded.email,
                            last_login_at = excluded.last_login_at
                        """,
                        (
                            oidc_user_id,
                            display_name,
                            email,
                            role,
                            oidc_sub,
                            now,
                            now,
                            1 if is_youth else 0,
                        ),
                    )
                    bound = conn.execute(
                        "SELECT * FROM users WHERE oidc_sub = ?",
                        (oidc_sub,),
                    ).fetchone()
                else:
                    raise ValueError("Plex or OIDC identity is required")
                assert bound is not None
                redeemed_id = str(bound["id"])
                cursor = conn.execute(
                    """
                    UPDATE invites
                    SET status = 'redeemed', redeemed_at = ?, redeemed_user_id = ?
                    WHERE id = ? AND status = 'pending' AND expires_at >= ?
                    """,
                    (now, redeemed_id, invite_id, now),
                )
                if int(cursor.rowcount or 0) != 1:
                    raise InviteConflict("Invite has already been used")
                invite_row = conn.execute("SELECT * FROM invites WHERE id = ?", (invite_id,)).fetchone()
        except sqlite3.OperationalError as error:
            if "locked" in str(error).lower() or "busy" in str(error).lower():
                raise InviteConflict("Invite has already been used") from error
            raise
        assert invite_row is not None
        return {"user": self._row_to_user(bound), "invite": self._row_to_invite(invite_row)}

    def has_denied_identity(
        self,
        *,
        email: Optional[str] = None,
        plex_user_id: Optional[str] = None,
        oidc_sub: Optional[str] = None,
    ) -> bool:
        """Soft-block: a denied access request matching a known identity."""
        email_clean = str(email or "").strip().lower() or None
        plex_clean = str(plex_user_id or "").strip() or None
        oidc_clean = str(oidc_sub or "").strip() or None
        if not email_clean and not plex_clean and not oidc_clean:
            return False
        with self.connect() as conn:
            cols = {str(r["name"]) for r in conn.execute("PRAGMA table_info(access_requests)").fetchall()}
            if email_clean and "email" in cols:
                row = conn.execute(
                    """
                    SELECT 1 FROM access_requests
                    WHERE status = 'denied' AND lower(email) = ?
                    LIMIT 1
                    """,
                    (email_clean,),
                ).fetchone()
                if row is not None:
                    return True
            # Optional identity columns (future-proof); ignore if absent.
            if plex_clean and "plex_user_id" in cols:
                row = conn.execute(
                    """
                    SELECT 1 FROM access_requests
                    WHERE status = 'denied' AND plex_user_id = ?
                    LIMIT 1
                    """,
                    (plex_clean,),
                ).fetchone()
                if row is not None:
                    return True
            if oidc_clean and "oidc_sub" in cols:
                row = conn.execute(
                    """
                    SELECT 1 FROM access_requests
                    WHERE status = 'denied' AND oidc_sub = ?
                    LIMIT 1
                    """,
                    (oidc_clean,),
                ).fetchone()
                if row is not None:
                    return True
        return False

    @staticmethod
    def _row_to_invite(row: sqlite3.Row) -> Dict[str, Any]:
        methods_raw = row["allowed_methods"]
        try:
            methods = json.loads(methods_raw) if methods_raw else ["plex"]
        except (json.JSONDecodeError, TypeError):
            methods = ["plex"]
        if not isinstance(methods, list):
            methods = ["plex"]
        methods = [str(m).strip().lower() for m in methods if str(m).strip().lower() in INVITE_METHODS]
        if not methods:
            methods = ["plex"]
        keys = set(row.keys()) if hasattr(row, "keys") else set()
        return {
            "id": str(row["id"]),
            "token_hash": str(row["token_hash"]),
            "expires_at": float(row["expires_at"]),
            "status": str(row["status"]),
            "email": str(row["email"]) if row["email"] is not None else None,
            "expected_plex_user_id": (
                str(row["expected_plex_user_id"]) if row["expected_plex_user_id"] is not None else None
            ),
            "expected_oidc_sub": (
                str(row["expected_oidc_sub"]) if row["expected_oidc_sub"] is not None else None
            ),
            "role": str(row["role"]),
            "is_youth": bool(int(row["is_youth"])) if row["is_youth"] is not None else False,
            "allowed_methods": methods,
            "created_by": str(row["created_by"]) if row["created_by"] is not None else None,
            "created_at": float(row["created_at"]),
            "redeemed_at": float(row["redeemed_at"]) if row["redeemed_at"] is not None else None,
            "redeemed_user_id": (
                str(row["redeemed_user_id"]) if row["redeemed_user_id"] is not None else None
            ),
            "access_request_id": (
                str(row["access_request_id"])
                if "access_request_id" in keys and row["access_request_id"] is not None
                else None
            ),
        }


def _normalize_methods(allowed_methods: Optional[List[str]]) -> List[str]:
    if not allowed_methods:
        return ["plex", "oidc", "local"]
    cleaned = [
        str(m).strip().lower()
        for m in allowed_methods
        if str(m).strip().lower() in INVITE_METHODS
    ]
    # Preserve order, drop dupes.
    seen: set[str] = set()
    out: List[str] = []
    for method in cleaned:
        if method not in seen:
            seen.add(method)
            out.append(method)
    return out or ["plex", "oidc", "local"]
