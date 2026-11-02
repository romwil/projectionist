"""Personal-data registry contract (PRIV-024) and the rights built on it.

* Every person-linked column in the migrated schema is registered.
* Export covers every ``export=True`` store and only the caller's rows (PRIV-005).
* Account removal is one transaction and leaves no orphan rows (PRIV-006, ARCH-009).
* Deleted chat text is not readable in the database file or its WAL.
* Restoring an older snapshot does not bring an erased account or purge back.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from typing import Dict
from unittest import mock

from fastapi.testclient import TestClient

from projectionist import backups
from projectionist.library.db import Database
from projectionist.privacy import erasures, registry
from projectionist.syllabus import _ensure_syllabus_table


def _all_tables(conn: sqlite3.Connection) -> Dict[str, Dict[str, dict]]:
    tables: Dict[str, Dict[str, dict]] = {}
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ):
        info = conn.execute(f"PRAGMA table_info('{name}')").fetchall()
        tables[name] = {
            r[1]: {"type": str(r[2] or "").upper(), "notnull": bool(r[3]), "pk": int(r[5])} for r in info
        }
    return tables


def _fill(col: str, meta: dict, marker: str) -> object:
    t = meta["type"]
    if "INT" in t:
        return 1
    if any(k in t for k in ("REAL", "FLOA", "DOUB", "NUM")):
        return 1.0
    return f"{marker}-{col}"


def seed_every_store(db: Database, user_id: str, marker: str) -> None:
    """One row per registry store for ``user_id``; every text column carries ``marker``.

    Foreign keys and CHECK constraints are off for seeding only, so a store added
    to the registry is covered here without hand-written fixtures.
    """
    conn = sqlite3.connect(db.path)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("PRAGMA ignore_check_constraints=ON")
    tables = _all_tables(conn)
    parent_ids: Dict[str, str] = {}
    try:
        for index, store in enumerate(reversed(registry.STORES)):
            cols = tables.get(store.table)
            if not cols:
                continue
            if store.table == "users":
                conn.execute(
                    "UPDATE users SET preferred_name = ? WHERE id = ?", (f"{marker}{index}-preferred_name", user_id)
                )
                continue
            values: Dict[str, object] = {}
            rowid_alias = sum(1 for m in cols.values() if m["pk"]) == 1
            for col, meta in cols.items():
                if rowid_alias and meta["pk"] and "INT" in meta["type"]:
                    continue
                values[col] = _fill(col, meta, f"{marker}{index}")
                if col.endswith("_json"):
                    values[col] = json.dumps({"user_id": user_id, "marker": f"{marker}{index}"})
            if "id" in cols and "INT" not in cols["id"]["type"]:
                values["id"] = f"{marker}{index}-{store.table}-id"
            for col in store.subject_cols:
                values[col] = user_id
            for col, literal in re.findall(r"(\w+) = '([^']*)'", store.match):
                values[col] = literal
            for m in re.finditer(r"(\w+) IN \(SELECT id FROM (\w+) WHERE", store.match):
                values[m.group(1)] = parent_ids[m.group(2)]
            names = list(values)
            conn.execute(
                f"INSERT INTO {store.table} ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
                [values[n] for n in names],
            )
            if "id" in values and store.subject_cols:
                parent_ids.setdefault(store.table, str(values["id"]))
        conn.commit()
    finally:
        conn.close()


def count_by_store(db: Database, user_id: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    with db.connect() as conn:
        for store in registry.STORES:
            key = f"{store.table}:{store.match}"
            row = conn.execute(
                f"SELECT COUNT(*) AS c FROM {store.table} WHERE {store.match}",
                (user_id,) * store.match.count("?"),
            ).fetchone()
            out[key] = int(row["c"])
    return out


class RegistryFixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        self.db = Database(self.data_dir / "projectionist.db")
        _ensure_syllabus_table(self.db)
        for uid in ("owner", "adult-a", "adult-b"):
            self.db.create_local_user(
                user_id=uid, display_name=uid, password_hash="x", role="owner" if uid == "owner" else "member"
            )
        seed_every_store(self.db, "adult-a", "AAAMARK")
        seed_every_store(self.db, "adult-b", "BBBMARK")

    def tearDown(self) -> None:
        self.tmp.cleanup()


class SchemaContractTests(unittest.TestCase):
    """PRIV-024: a new person-linked column fails CI until it is registered."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "projectionist.db")
        _ensure_syllabus_table(self.db)
        self.conn = sqlite3.connect(self.db.path)
        self.tables = _all_tables(self.conn)

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def _registered_cols(self) -> Dict[str, set]:
        out: Dict[str, set] = {}
        for store in registry.STORES:
            out.setdefault(store.table, set()).update(
                store.subject_cols, store.anonymize_cols, store.covers_cols, store.secret_cols
            )
        return out

    def test_every_person_linked_column_is_registered(self) -> None:
        registered = self._registered_cols()
        missing = []
        for table, cols in self.tables.items():
            for col in cols:
                if not registry.PERSON_COLUMN_RE.search(col):
                    continue
                if col in registered.get(table, set()) or (table, col) in registry.NOT_PERSONAL:
                    continue
                missing.append(f"{table}.{col}")
        self.assertEqual(missing, [], "Register these in projectionist/privacy/registry.py")

    def test_tables_pointing_at_users_or_registered_stores_are_registered(self) -> None:
        registered_tables = {s.table for s in registry.STORES}
        missing = []
        for table in self.tables:
            for fk in self.conn.execute(f"PRAGMA foreign_key_list('{table}')"):
                if fk[2] in registered_tables and table not in registered_tables:
                    missing.append(f"{table} -> {fk[2]}")
        self.assertEqual(missing, [])

    def test_registry_names_real_tables_and_columns(self) -> None:
        for store in registry.STORES:
            self.assertIn(store.table, self.tables, store.table)
            cols = self.tables[store.table]
            for col in (*store.subject_cols, *store.anonymize_cols, *store.covers_cols, *store.secret_cols):
                self.assertIn(col, cols, f"{store.table}.{col}")
            self.conn.execute(
                f"SELECT COUNT(*) FROM {store.table} WHERE {store.match}",
                ("x",) * store.match.count("?"),
            )
            if store.on_delete == "keep":
                self.assertTrue(store.keep_reason, store.table)

    def test_a_dummy_user_id_column_fails_the_contract(self) -> None:
        self.conn.execute("CREATE TABLE new_feature (id TEXT PRIMARY KEY, user_id TEXT)")
        tables = _all_tables(self.conn)
        registered = self._registered_cols()
        unregistered = [
            c for c in tables["new_feature"] if registry.PERSON_COLUMN_RE.search(c)
            and c not in registered.get("new_feature", set())
        ]
        self.assertEqual(unregistered, ["user_id"])

    def test_privacy_doc_table_is_generated_from_the_registry(self) -> None:
        doc = (Path(__file__).resolve().parents[1] / "docs" / "PRIVACY.md").read_text(encoding="utf-8")
        start = doc.index(registry.DOCS_BEGIN)
        end = doc.index(registry.DOCS_END) + len(registry.DOCS_END)
        self.assertEqual(
            doc[start:end],
            registry.render_docs_table(),
            "Run: python -m projectionist.privacy.registry",
        )


class ExportScopeTests(RegistryFixture):
    """PRIV-005: a member's export is complete for them and has nobody else's rows."""

    def test_export_has_every_export_store_and_no_other_member(self) -> None:
        export = self.db.export_user_memory("adult-a")
        blob = json.dumps(export)
        self.assertNotIn("BBBMARK", blob)
        for index, store in enumerate(reversed(registry.STORES)):
            if not store.export:
                continue
            marker = f"AAAMARK{index}-"
            self.assertIn(marker, blob, f"{store.table} ({store.label}) missing from export")
        self.assertNotIn("password_hash", blob)
        self.assertNotIn("plex_token_enc", blob)
        self.assertNotIn("source_user_key", blob)

    def test_non_export_stores_stay_out(self) -> None:
        blob = json.dumps(self.db.export_user_memory("adult-a"))
        for index, store in enumerate(reversed(registry.STORES)):
            if store.export:
                continue
            self.assertNotIn(f"AAAMARK{index}-", blob, store.table)


class AccountDeletionTests(RegistryFixture):
    """PRIV-006 / ARCH-009: one transaction, no orphans, other members intact."""

    def test_delete_user_leaves_no_rows_for_the_account(self) -> None:
        before_b = count_by_store(self.db, "adult-b")
        self.db.delete_user("adult-a")
        with self.db.connect() as conn:
            self.assertEqual(registry.remaining_rows(conn, "adult-a"), {})
            self.assertIsNone(conn.execute("SELECT 1 FROM users WHERE id='adult-a'").fetchone())
            kept = conn.execute(
                "SELECT COUNT(*) AS c FROM security_audit_log WHERE actor_id='adult-a'"
            ).fetchone()["c"]
            self.assertEqual(kept, 1, "security log is documented as kept")
            # Anonymized rows survive without the account id or its identifying text.
            row = conn.execute(
                "SELECT display_name, email, message, created_user_id FROM access_requests "
                "WHERE id LIKE 'AAAMARK%' AND created_user_id IS NULL"
            ).fetchone()
            self.assertEqual(
                (row["display_name"], row["email"], row["message"], row["created_user_id"]),
                ("", None, None, None),
            )
        self.assertEqual(count_by_store(self.db, "adult-b"), before_b)

    def test_delete_user_is_one_transaction(self) -> None:
        before = count_by_store(self.db, "adult-a")
        real = registry.erase_user

        def fail_after(conn, user_id, **kwargs):
            real(conn, user_id, **kwargs)
            raise sqlite3.OperationalError("disk full")

        with mock.patch.object(registry, "erase_user", side_effect=fail_after):
            with self.assertRaises(sqlite3.OperationalError):
                self.db.delete_user("adult-a")
        self.assertEqual(count_by_store(self.db, "adult-a"), before)
        self.assertEqual(erasures.load_erasures(self.data_dir), [])

    def test_deleted_chat_text_is_not_left_on_disk(self) -> None:
        self.db.ensure_chat_session("a-chat", user_id="adult-a")
        self.db.save_chat_message(
            "a-chat", "m-secret", "user", [{"type": "text", "content": "ZQXJ-unique-chat-marker " * 20}]
        )
        self.db.delete_user("adult-a")
        for suffix in ("", "-wal"):
            path = Path(f"{self.db.path}{suffix}")
            if path.exists():
                self.assertNotIn(b"ZQXJ-unique-chat-marker", path.read_bytes(), path.name)

    def test_delete_my_data_keeps_the_account_and_clears_the_rest(self) -> None:
        self.db.erase_user_data("adult-a")
        with self.db.connect() as conn:
            self.assertIsNotNone(conn.execute("SELECT 1 FROM users WHERE id='adult-a'").fetchone())
            for store in registry.stores_for(erase=registry.ERASE_ALL):
                if store.table == "user_memory_events":
                    continue
                n = conn.execute(
                    f"SELECT COUNT(*) AS c FROM {store.table} WHERE {store.match}",
                    ("adult-a",) * store.match.count("?"),
                ).fetchone()["c"]
                self.assertEqual(n, 0, store.table)
            events = conn.execute(
                "SELECT event_type FROM user_memory_events WHERE user_id='adult-a'"
            ).fetchall()
            self.assertEqual([e["event_type"] for e in events], ["purge"])


class RestoreAfterErasureTests(RegistryFixture):
    """A snapshot taken before an erasure must not resurrect it on restore."""

    def _snapshot(self, offset: float = 0.0) -> Path:
        return backups.create_snapshot_file(self.data_dir, now=time.time() + offset)

    def test_restore_does_not_bring_back_a_removed_account(self) -> None:
        self.db.ensure_chat_session("a-chat", user_id="adult-a")
        self.db.save_chat_message(
            "a-chat", "m-secret", "user", [{"type": "text", "content": "ZQXJ-restore-marker " * 20}]
        )
        snapshot = self._snapshot(offset=-10)
        self.db.delete_user("adult-a")
        result = backups.restore_snapshot(snapshot, self.data_dir)
        self.assertEqual(result["erasures_applied"], 1)
        restored = Database(self.data_dir / "projectionist.db")
        with restored.connect() as conn:
            self.assertIsNone(conn.execute("SELECT 1 FROM users WHERE id='adult-a'").fetchone())
            self.assertEqual(registry.remaining_rows(conn, "adult-a"), {})
            self.assertIsNotNone(conn.execute("SELECT 1 FROM users WHERE id='adult-b'").fetchone())
        self.assertNotIn(b"ZQXJ-restore-marker", (self.data_dir / "projectionist.db").read_bytes())

    def test_restore_reapplies_delete_my_data_to_older_snapshots_only(self) -> None:
        older = self._snapshot(offset=-10)
        self.db.erase_user_data("adult-a")
        backups.restore_snapshot(older, self.data_dir)
        restored = Database(self.data_dir / "projectionist.db")
        with restored.connect() as conn:
            self.assertIsNotNone(conn.execute("SELECT 1 FROM users WHERE id='adult-a'").fetchone())
            self.assertEqual(
                conn.execute("SELECT COUNT(*) AS c FROM chat_sessions WHERE user_id='adult-a'").fetchone()["c"],
                0,
            )
        # A snapshot taken after the purge keeps what the member made since.
        restored.ensure_chat_session("after-purge", user_id="adult-a")
        newer = self._snapshot(offset=10)
        backups.restore_snapshot(newer, self.data_dir, now=time.time() + 30)
        again = Database(self.data_dir / "projectionist.db")
        self.assertIsNotNone(again.get_chat_thread("after-purge", user_id="adult-a"))

    def test_restore_refuses_when_the_ledger_is_unreadable(self) -> None:
        snapshot = self._snapshot()
        erasures.ledger_path(self.data_dir).write_text("{not json", encoding="utf-8")
        with self.assertRaises(backups.RestoreError):
            backups.restore_snapshot(snapshot, self.data_dir)


class MyDataApiTests(unittest.TestCase):
    """The member routes behind Settings -> My data act only on the caller."""

    def setUp(self) -> None:
        from projectionist.web.auth import _hash_password, clear_pin_bindings
        from projectionist.web.rate_limit import clear_rate_limits
        from projectionist.web.session_tokens import clear_session_secret_cache

        self._tmp = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmp.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-my-data-session-secret-value"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        Path(self._tmp.name, "settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "local", "plex_login_enabled": False, "local_login_enabled": True},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db
        for name, role in (("owner", "owner"), ("alice", "member"), ("bob", "member")):
            self.db.create_local_user(
                user_id=f"local-{name}", display_name=name, password_hash=_hash_password("password123"), role=role
            )
        _ensure_syllabus_table(self.db)
        seed_every_store(self.db, "local-alice", "ALICEMARK")
        seed_every_store(self.db, "local-bob", "BOBMARK")
        self.db.ensure_chat_session("alice-chat", user_id="local-alice")
        self.db.save_chat_message("alice-chat", "m1", "user", [{"type": "text", "content": "alice says noir"}])

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs
        from projectionist.web.rate_limit import clear_rate_limits
        from projectionist.web.session_tokens import clear_session_secret_cache

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in (
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "DATA_DIR",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmp.cleanup()

    def _login(self, name: str) -> None:
        self.client.cookies.clear()
        resp = self.client.post("/api/auth/local/login", json={"username": name, "password": "password123"})
        self.assertEqual(resp.status_code, 200, resp.text)

    def test_member_export_is_their_own_only(self) -> None:
        self._login("alice")
        resp = self.client.get("/api/me/memory")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("ALICEMARK", resp.text)
        self.assertNotIn("BOBMARK", resp.text)
        self.assertNotIn("password_hash", resp.text)
        # No parameter widens scope to another account.
        other = self.client.get("/api/me/memory", params={"user_id": "local-bob"})
        self.assertNotIn("BOBMARK", other.text)

    def test_markdown_export_includes_message_text(self) -> None:
        self._login("alice")
        resp = self.client.get("/api/me/memory", params={"format": "markdown"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("alice says noir", resp.text)

    def test_note_delete_is_scoped_to_the_caller(self) -> None:
        note = self.db.add_user_memory_note("local-bob", kind="preference", text="bob private")
        self._login("alice")
        self.assertEqual(self.client.delete(f"/api/me/memory/notes/{note['id']}").status_code, 404)
        self.assertTrue(self.db.get_user_memory_note(note["id"], user_id="local-bob"))
        self._login("bob")
        listed = self.client.get("/api/me/memory/notes").json()["notes"]
        self.assertIn(note["id"], [n["id"] for n in listed])
        self.assertEqual(self.client.delete(f"/api/me/memory/notes/{note['id']}").status_code, 200)
        self.assertIsNone(self.db.get_user_memory_note(note["id"], user_id="local-bob"))

    def test_delete_my_data_needs_the_phrase_and_spares_others(self) -> None:
        self._login("alice")
        self.assertEqual(self.client.post("/api/me/data/erase", json={"confirm": "yes"}).status_code, 400)
        resp = self.client.post("/api/me/data/erase", json={"confirm": "Delete my data"})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertGreater(resp.json()["total"], 0)
        after = self.client.get("/api/me/memory").json()
        for key, store in registry.export_keys():
            if store.erase and key in after["stores"] and store.table != "user_memory_events":
                self.assertEqual(after["stores"][key], [], key)
        self.assertEqual(after["chat_threads"], [])
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)
        self._login("bob")
        self.assertIn("BOBMARK", self.client.get("/api/me/memory").text)

    def test_owner_removal_clears_the_avatar_file(self) -> None:
        from projectionist.web.avatars import avatars_dir

        avatar = avatars_dir(Path(self._tmp.name)) / "local-alice.png"
        avatar.write_bytes(b"\x89PNG fake")
        self._login("owner")
        self.assertEqual(self.client.delete("/api/users/local-alice").status_code, 200)
        self.assertFalse(avatar.exists())
        with self.db.connect() as conn:
            self.assertEqual(registry.remaining_rows(conn, "local-alice"), {})


if __name__ == "__main__":
    unittest.main()
