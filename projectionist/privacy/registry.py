"""Personal-data registry (PRIV-024).

One list of every store that holds data about a household account. Export,
"Delete my data", account removal, restore-after-erasure, and the generated
table in ``docs/PRIVACY.md`` all read it. ``tests/test_privacy_registry.py``
introspects the migrated schema and fails when a person-linked column is not
registered here, so a new per-user table cannot silently fall outside rights
handling.

Each :class:`PersonalStore` names how rows are matched to one account and
what happens to them:

* ``export`` — included in the member's own export.
* ``erase`` — which self-service purge removes the rows: ``"memory"`` (the
  older chat-and-memory purge), ``"activity"`` (the rest of "Delete my data"),
  or ``None`` (only account removal touches them).
* ``on_delete`` — account removal: ``"delete"`` the rows, ``"anonymize"``
  (blank the identifying columns, keep the row), or ``"keep"`` with a reason.

Functions here take a raw ``sqlite3.Connection`` so the same code runs on the
live database and on a staged snapshot during restore. Missing tables or
columns (an older snapshot) are skipped, never an error.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Tuple

Erase = Optional[Literal["memory", "activity"]]
OnDelete = Literal["delete", "anonymize", "keep"]

ERASE_MEMORY: Tuple[str, ...] = ("memory",)
ERASE_ALL: Tuple[str, ...] = ("memory", "activity")

# Column names that look person-linked. The contract test requires every match
# to be registered below (as a subject, an anonymized column, a covered column
# on a registered table, or an explicit exemption).
PERSON_COLUMN_RE = re.compile(
    r"(^|_)(user|owner|actor|reporter|recipient|created_by|updated_by|resolved_by|redeemed)(_id|_key)?$"
    r"|email|plex_user_id|source_user_key|oidc_sub|display_name|password|token_enc|apprise",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PersonalStore:
    table: str
    label: str
    match: str
    """SQL boolean over the table's columns with exactly one ``?`` for the account id."""
    subject_cols: Tuple[str, ...] = ()
    """Columns that hold the account id (what the contract test checks)."""
    export: bool = True
    erase: Erase = None
    on_delete: OnDelete = "delete"
    anonymize_cols: Tuple[str, ...] = ()
    keep_reason: Optional[str] = None
    secret_cols: Tuple[str, ...] = ()
    """Never exported (password hashes, encrypted tokens, upstream account keys)."""
    covers_cols: Tuple[str, ...] = ()
    """Other person-linked columns on this table that ride along with the row."""
    requires_cols: Tuple[str, ...] = field(default=())
    """Skip the store when the table lacks these columns (older schemas)."""


def _direct(col: str) -> str:
    return f"{col} = ?"


# Deletion runs in this order: anonymize first (while foreign keys still point
# at the user), then child rows before parents, then the account row last.
STORES: Tuple[PersonalStore, ...] = (
    # --- Identity rows other people's records point at -----------------------
    PersonalStore(
        table="access_requests",
        label="Your request to join (name, email, message)",
        match=_direct("created_user_id"),
        subject_cols=("created_user_id",),
        on_delete="anonymize",
        anonymize_cols=("display_name", "email", "message", "created_user_id"),
    ),
    PersonalStore(
        table="access_requests",
        label="Join requests you approved or declined (who decided)",
        match=_direct("resolved_by"),
        subject_cols=("resolved_by",),
        export=False,
        on_delete="anonymize",
        anonymize_cols=("resolved_by",),
    ),
    PersonalStore(
        table="invites",
        label="The invite you joined with (email, expected Plex or SSO account)",
        match=_direct("redeemed_user_id"),
        subject_cols=("redeemed_user_id",),
        on_delete="anonymize",
        anonymize_cols=("email", "expected_plex_user_id", "expected_oidc_sub", "redeemed_user_id"),
        secret_cols=("token_hash",),
    ),
    PersonalStore(
        table="invites",
        label="Invites you sent (who sent them)",
        match=_direct("created_by"),
        subject_cols=("created_by",),
        export=False,
        on_delete="anonymize",
        anonymize_cols=("created_by",),
        secret_cols=("token_hash",),
    ),
    PersonalStore(
        table="media_issues",
        label="Problems you reported about a title (your name is removed, the note stays)",
        match=_direct("reporter_user_id"),
        subject_cols=("reporter_user_id",),
        on_delete="anonymize",
        anonymize_cols=("reporter_user_id",),
    ),
    PersonalStore(
        table="user_notifications",
        label="Notes other members got from you (your name is removed)",
        match=_direct("from_user_id"),
        subject_cols=("from_user_id",),
        export=False,
        on_delete="anonymize",
        anonymize_cols=("from_user_id",),
    ),
    PersonalStore(
        table="persona_templates",
        label="Curator voices you shared with the household (your name is removed)",
        match="owner_user_id = ? AND visibility != 'private'",
        subject_cols=("owner_user_id",),
        on_delete="anonymize",
        anonymize_cols=("owner_user_id",),
    ),
    PersonalStore(
        table="grooming_action_log",
        label="Library clean-up actions you ran (who ran them)",
        match=_direct("actor_user_id"),
        subject_cols=("actor_user_id",),
        export=False,
        on_delete="anonymize",
        anonymize_cols=("actor_user_id",),
    ),
    PersonalStore(
        table="ephemeral_plex_collections",
        label="Temporary Plex collections you made (who made them)",
        match=_direct("created_by_user_id"),
        subject_cols=("created_by_user_id",),
        export=False,
        on_delete="anonymize",
        anonymize_cols=("created_by_user_id",),
    ),
    PersonalStore(
        table="owner_checklist_marks",
        label="Owner checklist ticks (who ticked them)",
        match=_direct("updated_by"),
        subject_cols=("updated_by",),
        export=False,
        on_delete="anonymize",
        anonymize_cols=("updated_by",),
    ),
    PersonalStore(
        table="security_audit_log",
        label="Security log entries about your account",
        match="actor_id = ? OR target_id = ?",
        subject_cols=("actor_id", "target_id"),
        export=False,
        on_delete="keep",
        keep_reason=(
            "The owner's record of sign-ins, role changes, and removals. It holds account ids, "
            "not chats, and keeps the newest 20,000 rows."
        ),
    ),
    # --- Private memory and chat (the "memory" purge) -------------------------
    PersonalStore(
        table="watch_completions",
        label="Plex viewing: finished titles",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="memory",
    ),
    PersonalStore(
        table="watch_session_events",
        label="Plex viewing: session links",
        match="session_id IN (SELECT id FROM watch_sessions WHERE user_id = ?)",
        export=False,
        erase="memory",
    ),
    PersonalStore(
        table="watch_sessions",
        label="Plex viewing: sessions",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="memory",
        secret_cols=("source_user_key",),
        covers_cols=("source_user_key",),
    ),
    PersonalStore(
        table="watch_events",
        label="Plex viewing: play, pause, and stop events",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="memory",
        secret_cols=("source_user_key", "payload_hash"),
        covers_cols=("source_user_key",),
    ),
    PersonalStore(
        table="watch_source_identities",
        label="Your linked Plex account on the Plex server",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="memory",
        secret_cols=("source_user_key",),
        covers_cols=("source_user_key", "display_name"),
    ),
    PersonalStore(
        table="message_feedback",
        label="Thumbs up or down on curator replies",
        match="user_id = ? OR session_id IN (SELECT id FROM chat_sessions WHERE user_id = ?)",
        subject_cols=("user_id",),
        erase="memory",
    ),
    PersonalStore(
        table="chat_messages",
        label="Chat messages",
        match="session_id IN (SELECT id FROM chat_sessions WHERE user_id = ?)",
        erase="memory",
    ),
    PersonalStore(
        table="chat_sessions",
        label="Chat threads",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="memory",
    ),
    PersonalStore(
        table="saved_library_pages",
        label="Saved library pages",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="memory",
    ),
    PersonalStore(
        table="user_memory_notes",
        label="Private memory notes",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="memory",
    ),
    PersonalStore(
        table="preference_facts",
        label="Preference notes",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="memory",
        requires_cols=("user_id",),
    ),
    PersonalStore(
        table="system_telemetry_stream",
        label="Activity counts (chat turns and plays, never your words)",
        match="json_extract(payload_json, '$.user_id') = ?",
        erase="memory",
    ),
    PersonalStore(
        table="user_memory_events",
        label="Memory audit trail (when notes were added, exported, or purged)",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="memory",
        covers_cols=("target_id",),
    ),
    # --- Everything else that is yours ("Delete my data") ---------------------
    PersonalStore(
        table="watchlist_pins",
        label="Watchlist",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="curated_list_items",
        label="Titles on your lists",
        match="list_id IN (SELECT id FROM curated_lists WHERE user_id = ?)",
        erase="activity",
    ),
    PersonalStore(
        table="curated_lists",
        label="Lists you made, private or published",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="user_course_progress",
        label="Course progress",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="user_syllabus_sessions",
        label="Course sessions",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="user_title_reviews",
        label="Ratings and written reviews",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="rating_prompt_queue",
        label="Pending rating prompts",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="pending_actions",
        label="Actions you started that were never confirmed",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
        secret_cols=("token",),
    ),
    PersonalStore(
        table="user_notifications",
        label="Inbox: newsletters, nudges, whispers, and alerts",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="user_recommendations",
        label="Titles someone recommended to you, and ones you recommended",
        match="to_user_id = ? OR from_user_id = ?",
        subject_cols=("to_user_id", "from_user_id"),
        erase="activity",
    ),
    PersonalStore(
        table="user_taste_profile",
        label="Taste profile",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="user_weekly_rails",
        label="Weekly picks rail",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="user_badges",
        label="Badges",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="user_streaks",
        label="Streaks",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="user_challenge_progress",
        label="Challenge progress",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="year_in_review_snapshots",
        label="Year in Review",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="llm_usage",
        label="AI usage records (token counts, no words)",
        match=_direct("user_id"),
        subject_cols=("user_id",),
        erase="activity",
    ),
    PersonalStore(
        table="persona_templates",
        label="Private curator voices you made",
        match="owner_user_id = ? AND visibility = 'private'",
        subject_cols=("owner_user_id",),
        erase="activity",
    ),
    # --- The account itself (removed last) -----------------------------------
    PersonalStore(
        table="users",
        label="Your profile: name, email, sign-in links, and settings",
        match="id = ?",
        subject_cols=("id",),
        secret_cols=("password_hash", "plex_token_enc", "apprise_urls", "session_epoch"),
        covers_cols=(
            "display_name",
            "email",
            "plex_user_id",
            "seerr_user_id",
            "oidc_sub",
            "notification_email",
            "notify_channel_email",
            "notify_channel_apprise",
            "apprise_urls",
            "password_hash",
            "plex_token_enc",
        ),
    ),
)

# Person-linked-looking columns that are not about a household account.
NOT_PERSONAL: Mapping[Tuple[str, str], str] = {}

# Files outside the database that removal also clears.
FILE_STORES: Tuple[Tuple[str, str], ...] = (
    ("Uploaded profile picture", "DATA_DIR/avatars/<account>.*"),
)


def stores_for(*, erase: Optional[Sequence[str]] = None, export: Optional[bool] = None) -> List[PersonalStore]:
    out = []
    for store in STORES:
        if erase is not None and store.erase not in erase:
            continue
        if export is not None and store.export != export:
            continue
        out.append(store)
    return out


# --- schema helpers -----------------------------------------------------------


def _columns(conn: sqlite3.Connection, table: str) -> Dict[str, bool]:
    """``{column: notnull}`` for ``table``; empty when the table is missing."""
    try:
        rows = conn.execute(f"PRAGMA table_info('{table}')").fetchall()
    except sqlite3.Error:
        return {}
    return {str(r[1]): bool(r[3]) for r in rows}


def _usable(conn: sqlite3.Connection, store: PersonalStore, cache: Dict[str, Dict[str, bool]]) -> bool:
    cols = cache.setdefault(store.table, _columns(conn, store.table))
    if not cols:
        return False
    needed = set(store.subject_cols) | set(store.requires_cols) | set(store.anonymize_cols)
    if not needed.issubset(cols):
        return False
    if "json_extract" in store.match:
        try:
            conn.execute("SELECT json_extract('{}', '$.x')").fetchone()
        except sqlite3.Error:
            return False
    for parent in re.findall(r"FROM (\w+) WHERE", store.match):
        if not cache.setdefault(parent, _columns(conn, parent)):
            return False
    return True


def _params(store: PersonalStore, user_id: str) -> Tuple[str, ...]:
    return (user_id,) * store.match.count("?")


def _decode(value: Any, column: str) -> Any:
    if isinstance(value, bytes):
        return None
    if isinstance(value, str) and column.endswith("_json") and value:
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


# --- export -------------------------------------------------------------------


def export_keys() -> List[Tuple[str, PersonalStore]]:
    """Export section key per ``export=True`` store: ``table``, or ``table:subject`` on repeats."""
    seen: set = set()
    out = []
    for store in stores_for(export=True):
        key = store.table if store.table not in seen else f"{store.table}:{store.subject_cols[0]}"
        seen.add(store.table)
        out.append((key, store))
    return out


def export_rows(
    conn: sqlite3.Connection, user_id: str, *, skip_tables: Iterable[str] = ()
) -> Dict[str, List[Dict[str, Any]]]:
    """Rows for every ``export=True`` store, keyed per :func:`export_keys`."""
    skip = set(skip_tables)
    cache: Dict[str, Dict[str, bool]] = {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for key, store in export_keys():
        if store.table in skip or not _usable(conn, store, cache):
            continue
        cols = [c for c in cache[store.table] if c not in store.secret_cols]
        select = ", ".join(f'"{c}"' for c in cols)
        rows = conn.execute(
            f"SELECT {select} FROM {store.table} WHERE {store.match}", _params(store, user_id)
        ).fetchall()
        out[key] = [{c: _decode(row[i], c) for i, c in enumerate(cols)} for row in rows]
    return out


# --- erasure ------------------------------------------------------------------


def erase_user(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    groups: Sequence[str] = ERASE_ALL,
    account: bool = False,
) -> Dict[str, int]:
    """Delete (or anonymize, for ``account=True``) one account's rows on ``conn``.

    ``account=False`` runs a self-service purge over ``groups``. ``account=True``
    removes the account: every ``delete`` store, every ``anonymize`` store, and
    the ``users`` row last. ``keep`` stores are never touched. The caller owns
    the transaction; nothing here commits.
    """
    cache: Dict[str, Dict[str, bool]] = {}
    counts: Dict[str, int] = {}
    for store in STORES:
        if account:
            if store.on_delete == "keep":
                continue
        elif store.erase not in groups:
            continue
        if not _usable(conn, store, cache):
            continue
        params = _params(store, user_id)
        if account and store.on_delete == "anonymize":
            notnull = cache[store.table]
            sets = ", ".join(
                f"{c} = ''" if notnull.get(c) else f"{c} = NULL" for c in store.anonymize_cols
            )
            cur = conn.execute(f"UPDATE {store.table} SET {sets} WHERE {store.match}", params)
        else:
            cur = conn.execute(f"DELETE FROM {store.table} WHERE {store.match}", params)
        key = store.table if store.table not in counts else f"{store.table}:{store.subject_cols[0]}"
        counts[key] = counts.get(key, 0) + max(cur.rowcount, 0)
    return counts


def remaining_rows(conn: sqlite3.Connection, user_id: str) -> Dict[str, int]:
    """Rows still matching ``user_id`` in stores account removal should clear."""
    cache: Dict[str, Dict[str, bool]] = {}
    left: Dict[str, int] = {}
    for store in STORES:
        if store.on_delete == "keep" or not _usable(conn, store, cache):
            continue
        row = conn.execute(
            f"SELECT COUNT(*) FROM {store.table} WHERE {store.match}", _params(store, user_id)
        ).fetchone()
        if row and row[0]:
            left[f"{store.table}:{','.join(store.subject_cols) or 'via parent'}"] = int(row[0])
    return left


# --- docs ---------------------------------------------------------------------

DOCS_BEGIN = "<!-- privacy-registry:begin (generated by python -m projectionist.privacy.registry) -->"
DOCS_END = "<!-- privacy-registry:end -->"


def _yes(flag: bool) -> str:
    return "Yes" if flag else "No"


def render_docs_table() -> str:
    """The "What export and deletion cover" table in ``docs/PRIVACY.md``."""
    lines = [
        DOCS_BEGIN,
        "| Data | In your download | Delete my data | Removing the account | Table |",
        "|------|:----------------:|:--------------:|:--------------------:|-------|",
    ]
    for store in STORES:
        removal = {
            "delete": "Deleted",
            "anonymize": "Name removed",
            "keep": "**Kept**",
        }[store.on_delete]
        lines.append(
            f"| {store.label} | {_yes(store.export)} | {_yes(store.erase is not None)} | "
            f"{removal} | `{store.table}` |"
        )
    for label, where in FILE_STORES:
        lines.append(f"| {label} | No | No | Deleted | `{where}` |")
    lines.append(DOCS_END)
    return "\n".join(lines)


def kept_store_reasons() -> List[Tuple[str, str]]:
    return [(s.label, s.keep_reason or "") for s in STORES if s.on_delete == "keep"]


def replace_docs_block(markdown: str) -> str:
    start = markdown.index(DOCS_BEGIN)
    end = markdown.index(DOCS_END) + len(DOCS_END)
    return markdown[:start] + render_docs_table() + markdown[end:]


def _main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(prog="python -m projectionist.privacy.registry")
    parser.add_argument("--write", default="docs/PRIVACY.md", help="Markdown file to update in place")
    args = parser.parse_args(argv)
    path = Path(args.write)
    path.write_text(replace_docs_block(path.read_text(encoding="utf-8")), encoding="utf-8")
    print(f"Updated {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
