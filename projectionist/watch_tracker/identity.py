"""Plex watch identity resolution and attribution repair.

Plex exposes two stable-looking identifiers that are *not* always the same:

* ``users.plex_user_id`` comes from plex.tv (``/api/v2/user`` → ``id``), e.g. ``148223``.
* PMS history ``accountID`` and session ``User.id`` for the **server owner** are often
  the *local* ``/accounts`` id (commonly ``1``), while shared users usually already
  use their plex.tv id as the PMS account id.

Exact ``source_user_key == plex_user_id`` therefore leaves the owner's watches
``user_id=NULL``. We alias the PMS local account whose name matches the server
token's plex.tv username onto the matching Projectionist user — never by
username alone for arbitrary shared accounts.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

from projectionist.library.db import Database

logger = logging.getLogger(__name__)

MAPPING_PLEX_ACCOUNT_ID = "plex_account_id"
MAPPING_PLEX_SERVER_ACCOUNT = "plex_server_account"
MAPPING_UNMAPPED = "unmapped"

_ALIAS_SOURCES: Tuple[str, ...] = ("plex_history", "plex_sessions", "plex_webhook")


def resolve_user_id(db: Database, source_user_key: str) -> Tuple[Optional[str], str]:
    """Return ``(user_id, mapping_method)`` for a provider identity key.

    Resolution order:
    1. Exact ``users.plex_user_id`` match (plex.tv account id).
    2. An already-mapped ``watch_source_identities`` row for the same key
       (server-owner local account alias, or prior repair).
    """
    key = str(source_user_key or "").strip()
    if not key:
        return None, MAPPING_UNMAPPED
    row = db.get_user_by_plex_id(key)
    if row is not None:
        return str(row["id"]), MAPPING_PLEX_ACCOUNT_ID
    with db.connect() as conn:
        mapped = conn.execute(
            """
            SELECT user_id, mapping_method
            FROM watch_source_identities
            WHERE source_user_key = ? AND user_id IS NOT NULL
            ORDER BY
                CASE mapping_method
                    WHEN ? THEN 0
                    WHEN ? THEN 1
                    ELSE 2
                END,
                last_seen_at DESC
            LIMIT 1
            """,
            (key, MAPPING_PLEX_ACCOUNT_ID, MAPPING_PLEX_SERVER_ACCOUNT),
        ).fetchone()
    if mapped is None or mapped["user_id"] is None:
        return None, MAPPING_UNMAPPED
    method = str(mapped["mapping_method"] or MAPPING_PLEX_SERVER_ACCOUNT).strip()
    if method == MAPPING_UNMAPPED or not method:
        method = MAPPING_PLEX_SERVER_ACCOUNT
    return str(mapped["user_id"]), method


def _upsert_mapped_identity(
    conn,
    *,
    source: str,
    server_machine_id: str,
    source_user_key: str,
    user_id: str,
    display_name: Optional[str],
    mapping_method: str,
    now: float,
) -> None:
    conn.execute(
        """
        INSERT INTO watch_source_identities (
            source, server_machine_id, source_user_key, user_id, display_name,
            mapping_method, first_seen_at, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source, server_machine_id, source_user_key) DO UPDATE SET
            user_id = excluded.user_id,
            display_name = COALESCE(excluded.display_name, watch_source_identities.display_name),
            mapping_method = excluded.mapping_method,
            last_seen_at = excluded.last_seen_at
        """,
        (
            source,
            server_machine_id,
            source_user_key,
            user_id,
            display_name,
            mapping_method,
            now,
            now,
        ),
    )


def discover_server_owner_local_account(
    *,
    plex_token: str,
    accounts: Sequence[Any],
    timeout: int = 20,
) -> Optional[Dict[str, str]]:
    """Map the PLEX_TOKEN owner to their PMS local ``/accounts`` id when names match.

    ``accounts`` entries are objects/mappings with ``account_id`` (or ``id``) and ``name``.
    Returns ``{plex_user_id, local_account_id, username, display_name}`` or None.
    """
    token = str(plex_token or "").strip()
    if not token:
        return None
    from projectionist.connectors.plex_account import fetch_plex_account

    profile = fetch_plex_account(token, timeout=timeout)
    plex_user_id = str(profile.get("id") or "").strip()
    username = str(profile.get("username") or profile.get("title") or "").strip()
    if not plex_user_id or not username:
        return None
    username_key = username.casefold()
    for account in accounts:
        if isinstance(account, dict):
            local_id = str(account.get("account_id") or account.get("id") or "").strip()
            name = str(account.get("name") or "").strip()
        else:
            local_id = str(getattr(account, "account_id", "") or getattr(account, "id", "") or "").strip()
            name = str(getattr(account, "name", "") or "").strip()
        if not local_id or not name:
            continue
        if name.casefold() != username_key:
            continue
        # Never treat the empty/system account as the owner.
        if local_id == "0":
            continue
        return {
            "plex_user_id": plex_user_id,
            "local_account_id": local_id,
            "username": username,
            "display_name": name,
        }
    return None


def refresh_plex_server_account_aliases(
    db: Database,
    *,
    plex_url: str,
    plex_token: str,
    server_machine_id: Optional[str] = None,
    timeout: int = 20,
) -> Dict[str, Any]:
    """Upsert server-owner local-account aliases into ``watch_source_identities``."""
    base = str(plex_url or "").strip()
    token = str(plex_token or "").strip()
    if not base or not token:
        return {"status": "skipped", "reason": "plex_not_configured", "aliases_upserted": 0}

    from projectionist.connectors.plex import PlexClient

    client = PlexClient(base, token, timeout=timeout)
    machine_id = str(server_machine_id or "").strip() or client.machine_identifier()
    accounts = client.accounts()
    discovered = discover_server_owner_local_account(
        plex_token=token,
        accounts=accounts,
        timeout=timeout,
    )
    if discovered is None:
        return {
            "status": "ok",
            "reason": "no_owner_local_account",
            "server_machine_id": machine_id,
            "aliases_upserted": 0,
        }

    plex_user_id = discovered["plex_user_id"]
    local_account_id = discovered["local_account_id"]
    display_name = discovered["display_name"]
    user_row = db.get_user_by_plex_id(plex_user_id)
    if user_row is None:
        return {
            "status": "ok",
            "reason": "owner_not_linked",
            "plex_user_id": plex_user_id,
            "local_account_id": local_account_id,
            "server_machine_id": machine_id,
            "aliases_upserted": 0,
        }

    user_id = str(user_row["id"])
    now = time.time()
    upserted = 0

    def _write() -> int:
        count = 0
        with db.connect() as conn:
            for source in _ALIAS_SOURCES:
                # Exact plex.tv id key (harmless if already mapped via ingest).
                _upsert_mapped_identity(
                    conn,
                    source=source,
                    server_machine_id=machine_id,
                    source_user_key=plex_user_id,
                    user_id=user_id,
                    display_name=display_name,
                    mapping_method=MAPPING_PLEX_ACCOUNT_ID,
                    now=now,
                )
                count += 1
                if local_account_id == plex_user_id:
                    continue
                _upsert_mapped_identity(
                    conn,
                    source=source,
                    server_machine_id=machine_id,
                    source_user_key=local_account_id,
                    user_id=user_id,
                    display_name=display_name,
                    mapping_method=MAPPING_PLEX_SERVER_ACCOUNT,
                    now=now,
                )
                count += 1
        return count

    upserted = db.run_write(_write, label="refresh_plex_server_account_aliases")
    logger.info(
        "Watch identity: aliased PMS account %s → user %s (plex_user_id=%s)",
        local_account_id,
        user_id,
        plex_user_id,
    )
    return {
        "status": "ok",
        "server_machine_id": machine_id,
        "plex_user_id": plex_user_id,
        "local_account_id": local_account_id,
        "user_id": user_id,
        "aliases_upserted": upserted,
    }


def list_mapped_source_keys(db: Database) -> List[Dict[str, str]]:
    """Distinct resolvable ``source_user_key`` → ``user_id`` pairs."""
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT source_user_key, user_id, mapping_method
            FROM watch_source_identities
            WHERE user_id IS NOT NULL
            """
        ).fetchall()
    # Prefer exact plex_account_id when the same key appears with multiple methods.
    best: Dict[str, Dict[str, str]] = {}
    for row in rows:
        key = str(row["source_user_key"])
        method = str(row["mapping_method"] or "")
        entry = {
            "source_user_key": key,
            "user_id": str(row["user_id"]),
            "mapping_method": method,
        }
        prior = best.get(key)
        if prior is None:
            best[key] = entry
            continue
        if prior["mapping_method"] != MAPPING_PLEX_ACCOUNT_ID and method == MAPPING_PLEX_ACCOUNT_ID:
            best[key] = entry
    return list(best.values())


def repair_watch_attribution(db: Database) -> Dict[str, Any]:
    """Idempotently attribute NULL-user ledger rows when identities are mapped.

    Never overwrites a non-NULL ``user_id`` (shared/unknown watches stay honest).
    """
    mappings = list_mapped_source_keys(db)
    if not mappings:
        return {
            "status": "ok",
            "mapped_keys": 0,
            "events_updated": 0,
            "sessions_updated": 0,
            "completions_updated": 0,
        }

    def _write() -> Dict[str, int]:
        events_updated = 0
        sessions_updated = 0
        completions_updated = 0
        with db.connect() as conn:
            for mapping in mappings:
                key = mapping["source_user_key"]
                user_id = mapping["user_id"]
                cur = conn.execute(
                    """
                    UPDATE watch_events
                    SET user_id = ?
                    WHERE source_user_key = ? AND user_id IS NULL
                    """,
                    (user_id, key),
                )
                events_updated += int(cur.rowcount or 0)
                cur = conn.execute(
                    """
                    UPDATE watch_sessions
                    SET user_id = ?
                    WHERE source_user_key = ? AND user_id IS NULL
                    """,
                    (user_id, key),
                )
                sessions_updated += int(cur.rowcount or 0)
                cur = conn.execute(
                    """
                    UPDATE watch_completions
                    SET user_id = ?
                    WHERE user_id IS NULL
                      AND session_id IN (
                          SELECT id FROM watch_sessions WHERE source_user_key = ?
                      )
                    """,
                    (user_id, key),
                )
                completions_updated += int(cur.rowcount or 0)
        return {
            "events_updated": events_updated,
            "sessions_updated": sessions_updated,
            "completions_updated": completions_updated,
        }

    stats = db.run_write(_write, label="repair_watch_attribution")
    logger.info(
        "Watch identity repair: keys=%s events=%s sessions=%s completions=%s",
        len(mappings),
        stats["events_updated"],
        stats["sessions_updated"],
        stats["completions_updated"],
    )
    return {
        "status": "ok",
        "mapped_keys": len(mappings),
        **stats,
    }


def sync_plex_watch_identities(
    db: Database,
    *,
    plex_url: str,
    plex_token: str,
    server_machine_id: Optional[str] = None,
    repair: bool = True,
) -> Dict[str, Any]:
    """Refresh owner aliases and optionally repair NULL attribution."""
    alias = refresh_plex_server_account_aliases(
        db,
        plex_url=plex_url,
        plex_token=plex_token,
        server_machine_id=server_machine_id,
    )
    result: Dict[str, Any] = {"alias": alias}
    if repair and alias.get("status") == "ok" and int(alias.get("aliases_upserted") or 0) >= 0:
        # Always attempt repair: identities may already exist from a prior run.
        result["repair"] = repair_watch_attribution(db)
    elif repair:
        result["repair"] = repair_watch_attribution(db)
    return result
