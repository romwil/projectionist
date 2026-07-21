"""Reversible grooming action log + safe undo (M4)."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.library.db import Database
from curatorx.web.auth import SESSION_COOKIE_NAME, clear_pin_bindings
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import clear_session_secret_cache, create_session_token


def _seed(db: Database, rating_key: str, title: str) -> None:
    db.upsert_library_item(
        {
            "rating_key": rating_key,
            "media_type": "movie",
            "title": title,
            "year": 2020,
            "summary": "x",
            "genres": [],
            "cast": [],
            "directors": [],
            "keywords": [],
            "tmdb_id": abs(hash(rating_key)) % 100000,
        }
    )


class GroomingActionDbTests(unittest.TestCase):
    def test_snapshot_delete_and_undo_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            _seed(db, "rk-1", "Undo One")
            _seed(db, "rk-2", "Undo Two")

            snapshot = db.snapshot_library_items_by_rating_keys(["rk-1", "rk-2"])
            self.assertEqual(len(snapshot["items"]), 2)

            deleted = db.delete_library_items_by_rating_keys(["rk-1", "rk-2"])
            self.assertEqual(deleted, 2)
            self.assertEqual(len(db.search_keyword("Undo")), 0)

            action = db.record_grooming_action(
                action_id="a-1",
                action_type="purge_delete",
                actor_user_id=None,
                summary="Deleted 2 purge candidates",
                item_count=deleted,
                snapshot=snapshot,
            )
            self.assertTrue(action["reversible"])

            result = db.undo_grooming_action("a-1")
            assert result is not None
            self.assertEqual(result["restored"], 2)
            self.assertIsNotNone(result["undone_at"])
            self.assertEqual(len(db.search_keyword("Undo")), 2)

    def test_double_undo_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            _seed(db, "rk-1", "Once")
            snapshot = db.snapshot_library_items_by_rating_keys(["rk-1"])
            db.delete_library_items_by_rating_keys(["rk-1"])
            db.record_grooming_action(
                action_id="a-1",
                action_type="purge_delete",
                actor_user_id=None,
                summary="Deleted 1",
                item_count=1,
                snapshot=snapshot,
            )
            db.undo_grooming_action("a-1")
            with self.assertRaises(ValueError):
                db.undo_grooming_action("a-1")

    def test_restore_is_idempotent_when_row_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            _seed(db, "rk-1", "Present")
            snapshot = db.snapshot_library_items_by_rating_keys(["rk-1"])
            # Row still present: restore should skip it (0 restored), no crash.
            restored = db.restore_library_items_snapshot(snapshot)
            self.assertEqual(restored, 0)


class GroomingUndoApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-grooming-secret"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        for key in ("CURATORX_SKIP_DOTENV", "LLM_PROVIDER", "CURATORX_SESSION_SECRET"):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _enable_multi_user(self) -> None:
        (Path(self._tmpdir.name) / "settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "plex", "plex_login_enabled": True},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )

    def test_delete_records_undoable_action_and_undo_restores(self) -> None:
        db = self.app_mod._db()
        _seed(db, "rk-a", "Purge Me")
        resp = self.client.post(
            "/api/library/purge-candidates/delete", json={"rating_keys": ["rk-a"]}
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["deleted"], 1)
        self.assertTrue(body["undoable"])
        action_id = body["action_id"]

        listing = self.client.get("/api/admin/grooming/actions")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["count"], 1)

        undo = self.client.post(f"/api/admin/grooming/actions/{action_id}/undo")
        self.assertEqual(undo.status_code, 200)
        self.assertEqual(undo.json()["restored"], 1)
        self.assertEqual(len(db.search_keyword("Purge Me")), 1)

        # Second undo → 409 conflict.
        again = self.client.post(f"/api/admin/grooming/actions/{action_id}/undo")
        self.assertEqual(again.status_code, 409)

    def test_undo_unknown_action_404(self) -> None:
        resp = self.client.post("/api/admin/grooming/actions/does-not-exist/undo")
        self.assertEqual(resp.status_code, 404)

    def test_member_cannot_list_or_undo_grooming_actions(self) -> None:
        self._enable_multi_user()
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": 1, "title": "Owner"},
        ):
            self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})
        import curatorx.web.jobs as jobs

        jobs.get_job_manager().db.upsert_plex_user(
            user_id="plex-77",
            display_name="Member",
            email="m@example.com",
            plex_user_id="77",
            role="member",
        )
        member = TestClient(self.app_mod.app)
        member.cookies.set(SESSION_COOKIE_NAME, create_session_token("plex-77"))
        self.assertEqual(member.get("/api/admin/grooming/actions").status_code, 403)
        self.assertEqual(
            member.post("/api/admin/grooming/actions/x/undo").status_code, 403
        )


if __name__ == "__main__":
    unittest.main()
