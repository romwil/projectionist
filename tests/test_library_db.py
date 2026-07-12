"""Tests for library database."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from curatorx.library.db import (
    BOOTSTRAP_OWNER_ID,
    CURATOR_NAME_CONFIG_KEY,
    DEFAULT_LENS_ID,
    SQLITE_BUSY_TIMEOUT_MS,
    Database,
    run_with_db_lock_retry,
)
from curatorx.library.embeddings import semantic_search
import sqlite3


class DatabaseTests(unittest.TestCase):
    def test_upsert_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            item_id = db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Blade Runner",
                    "year": 1982,
                    "summary": "Sci-fi noir",
                    "genres": ["Sci-Fi"],
                    "cast": [],
                    "directors": [],
                    "keywords": ["dystopia"],
                    "tmdb_id": 78,
                }
            )
            self.assertGreater(item_id, 0)
            rows = db.search_keyword("blade")
            self.assertEqual(len(rows), 1)
            self.assertIn(78, db.owned_tmdb_ids("movie"))

    def test_connection_uses_wal_and_busy_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            with db.connect() as conn:
                journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
                busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
                sync = conn.execute("PRAGMA synchronous").fetchone()[0]
            self.assertEqual(str(journal).lower(), "wal")
            self.assertEqual(int(busy), SQLITE_BUSY_TIMEOUT_MS)
            # NORMAL == 1
            self.assertEqual(int(sync), 1)

    def test_upsert_library_items_batches_one_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            connect_enters = {"n": 0}
            real_connect = db.connect

            from contextlib import contextmanager

            @contextmanager
            def counting_connect():
                connect_enters["n"] += 1
                with real_connect() as conn:
                    yield conn

            db.connect = counting_connect  # type: ignore[method-assign]
            ids = db.upsert_library_items(
                [
                    {
                        "rating_key": f"rk-{i}",
                        "media_type": "movie",
                        "title": f"Title {i}",
                        "year": 2000 + i,
                    }
                    for i in range(5)
                ]
            )
            self.assertEqual(len(ids), 5)
            self.assertEqual(connect_enters["n"], 1)
            self.assertEqual(len(db.all_library_items()), 5)

    def test_ensure_bootstrap_owner_is_idempotent_and_cached(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            self.assertIsNotNone(db.get_user(BOOTSTRAP_OWNER_ID))
            self.assertTrue(db._bootstrap_owner_ready)
            db.ensure_bootstrap_owner()
            db.ensure_bootstrap_owner()
            with db.connect() as conn:
                count = conn.execute(
                    "SELECT COUNT(*) AS c FROM users WHERE id = ?",
                    (BOOTSTRAP_OWNER_ID,),
                ).fetchone()["c"]
            self.assertEqual(int(count), 1)

    def test_run_with_db_lock_retry_retries_then_succeeds(self) -> None:
        calls = {"n": 0}

        def flaky() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise sqlite3.OperationalError("database is locked")
            return "ok"

        with patch("curatorx.library.db.time.sleep"):
            self.assertEqual(run_with_db_lock_retry(flaky, label="test"), "ok")
        self.assertEqual(calls["n"], 3)

    def test_pending_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.save_pending_action("token1", "add_radarr", {"tmdb_id": 123})
            payload = db.pop_pending_action("token1")
            self.assertEqual(payload["tmdb_id"], 123)
            self.assertIsNone(db.pop_pending_action("token1"))

    def test_prd_schema_tables_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            expected = {
                "curator_system_config",
                "service_integrations",
                "curator_persona_metrics",
                "curation_lenses",
                "lens_taste_profile",
                "interaction_telemetry",
                "agent_blueprints",
            }
            with db.connect() as conn:
                rows = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                names = {str(r["name"]) for r in rows}
            self.assertTrue(expected.issubset(names))

    def test_service_integrations_certified_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.upsert_service_integration(
                "plex",
                base_url="http://plex.local",
                api_token_encrypted="***configured***",
                connection_status="verified",
                certified=1,
            )
            row = db.get_service_integration("plex")
            self.assertIsNotNone(row)
            self.assertEqual(int(row["certified"]), 1)

            db.invalidate_service_certification("plex")
            row = db.get_service_integration("plex")
            self.assertEqual(int(row["certified"]), 0)
            self.assertEqual(str(row["connection_status"]), "unverified")

    def test_persona_and_general_lens_seeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            lens = db.get_lens(DEFAULT_LENS_ID)
            self.assertIsNotNone(lens)
            self.assertEqual(lens["lens_name"], "General")
            persona = db.get_persona()
            self.assertIsNotNone(persona)
            self.assertEqual(persona["metric_id"], "current_profile")
            self.assertEqual(db.get_active_lens_id(), DEFAULT_LENS_ID)

    def test_lens_chat_isolation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.create_lens("directors", "Director Studies", "Focus on directors")
            session = "session-a"
            db.ensure_chat_session(session, DEFAULT_LENS_ID)
            db.save_chat_message(
                session,
                "m1",
                "user",
                [{"type": "text", "content": "general hello"}],
                lens_id=DEFAULT_LENS_ID,
            )
            db.save_chat_message(
                session,
                "m2",
                "user",
                [{"type": "text", "content": "director hello"}],
                lens_id="directors",
            )
            general = db.chat_history(session, lens_id=DEFAULT_LENS_ID)
            directors = db.chat_history(session, lens_id="directors")
            self.assertEqual(len(general), 1)
            self.assertEqual(general[0]["blocks"][0]["content"], "general hello")
            self.assertEqual(len(directors), 1)
            self.assertEqual(directors[0]["blocks"][0]["content"], "director hello")

    def test_lens_taste_explicit_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            db.set_lens_taste_weight(DEFAULT_LENS_ID, "70s-sci-fi", 2.0, explicit_lock=True)
            db.set_lens_taste_weight(DEFAULT_LENS_ID, "70s-sci-fi", 0.1, respect_lock=True)
            rows = db.get_lens_taste_profile(DEFAULT_LENS_ID)
            self.assertEqual(len(rows), 1)
            self.assertEqual(float(rows[0]["weight"]), 2.0)
            self.assertEqual(int(rows[0]["explicit_lock"]), 1)

    def test_curator_name_config_seeded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            with db.connect() as conn:
                row = conn.execute(
                    "SELECT config_value FROM curator_system_config WHERE config_key = ?",
                    (CURATOR_NAME_CONFIG_KEY,),
                ).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["config_value"], "Curator")

    def test_semantic_search_filters_by_media_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            movie_id = db.upsert_library_item(
                {
                    "rating_key": "1",
                    "media_type": "movie",
                    "title": "Movie One",
                    "genres": ["Drama"],
                }
            )
            show_id = db.upsert_library_item(
                {
                    "rating_key": "2",
                    "media_type": "show",
                    "title": "Show One",
                    "genres": ["Drama"],
                }
            )
            db.set_embedding(movie_id, [1.0, 0.0])
            db.set_embedding(show_id, [0.0, 1.0])
            hits = semantic_search(db, [1.0, 0.0], limit=10, media_type="movie")
            self.assertEqual([item_id for item_id, _ in hits], [movie_id])


if __name__ == "__main__":
    unittest.main()
