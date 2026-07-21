"""Weekly in-app digest: builder, storage, API, authz (M4)."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.config_store import Settings
from curatorx.digest import build_weekly_digest, current_week_start, snapshot_weekly_digest
from curatorx.library.db import Database
from curatorx.web.auth import SESSION_COOKIE_NAME, clear_pin_bindings
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import clear_session_secret_cache, create_session_token


def _seed(db: Database, rating_key: str, title: str, media_type: str = "movie") -> None:
    db.upsert_library_item(
        {
            "rating_key": rating_key,
            "media_type": media_type,
            "title": title,
            "year": 2021,
            "summary": "A summary that counts as overview coverage.",
            "genres": [],
            "cast": [],
            "directors": [],
            "keywords": [],
            "tmdb_id": abs(hash(rating_key)) % 100000,
        }
    )


class WeeklyDigestServiceTests(unittest.TestCase):
    def test_build_and_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            _seed(db, "m1", "Alpha", "movie")
            _seed(db, "s1", "Beta", "show")
            db.create_media_issue(
                issue_id="iss-1", reporter_user_id=None, rating_key="m1",
                tmdb_id=1, tvdb_id=None, media_type="movie", title="Alpha",
                code="bad_video", note="",
            )

            payload = build_weekly_digest(db, Settings())
            self.assertEqual(payload["library"]["total"], 2)
            self.assertEqual(payload["library"]["movies"], 1)
            self.assertEqual(payload["library"]["shows"], 1)
            self.assertEqual(payload["issues"]["open"], 1)
            self.assertIn("coverage", payload)

            saved = snapshot_weekly_digest(db, Settings())
            self.assertEqual(saved["payload"]["library"]["total"], 2)
            latest = db.get_latest_weekly_digest()
            assert latest is not None
            self.assertEqual(latest["id"], saved["id"])

    def test_snapshot_upserts_within_same_week(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            _seed(db, "m1", "Alpha")
            snapshot_weekly_digest(db, Settings())
            _seed(db, "m2", "Gamma")
            snapshot_weekly_digest(db, Settings())
            # Same weekly bucket → single row, refreshed.
            self.assertEqual(len(db.list_weekly_digests(limit=10)), 1)
            latest = db.get_latest_weekly_digest()
            assert latest is not None
            self.assertEqual(latest["payload"]["library"]["total"], 2)

    def test_current_week_start_is_stable_bucket(self) -> None:
        a = current_week_start(1_000_000.0)
        b = current_week_start(1_000_500.0)
        self.assertEqual(a, b)


class WeeklyDigestApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-digest-secret"
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

    def test_generate_then_read(self) -> None:
        _seed(self.app_mod._db(), "m1", "Alpha")
        gen = self.client.post("/api/admin/weekly-digest/generate")
        self.assertEqual(gen.status_code, 200)
        self.assertTrue(gen.json()["latest"])
        got = self.client.get("/api/admin/weekly-digest")
        self.assertEqual(got.status_code, 200)
        self.assertTrue(got.json()["latest"])

    def test_member_blocked(self) -> None:
        self._enable_multi_user()
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": 1, "title": "Owner"},
        ):
            self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})
        import curatorx.web.jobs as jobs

        jobs.get_job_manager().db.upsert_plex_user(
            user_id="plex-9", display_name="Member", email="m@example.com",
            plex_user_id="9", role="member",
        )
        member = TestClient(self.app_mod.app)
        member.cookies.set(SESSION_COOKIE_NAME, create_session_token("plex-9"))
        self.assertEqual(member.get("/api/admin/weekly-digest").status_code, 403)
        self.assertEqual(member.post("/api/admin/weekly-digest/generate").status_code, 403)


if __name__ == "__main__":
    unittest.main()
