"""Member vs owner library API audience sanitization."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.web.auth import clear_pin_bindings
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import clear_session_secret_cache


class LibraryAudienceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["CURATORX_SESSION_SECRET"] = "test-library-privacy-session-secret"
        os.environ["LLM_PROVIDER"] = "ollama"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()

        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "plex", "plex_login_enabled": True},
                    "llm_provider": "ollama",
                    "onboarding_complete": True,
                }
            ),
            encoding="utf-8",
        )

        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        # Ensure DATA_DIR picked up after env mutation (reload can race with module const).
        app_mod.DATA_DIR = Path(self._tmpdir.name)
        self.client = TestClient(app_mod.app)
        self._jobs = jobs
        self._app_mod = app_mod

        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": 10, "title": "Owner"},
        ):
            login = self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})
        self.assertEqual(login.status_code, 200)

        db = jobs.get_job_manager().db
        db.upsert_library_item(
            {
                "rating_key": "rk-secret",
                "media_type": "movie",
                "title": "Jaws",
                "year": 1975,
                "genres": ["Thriller"],
                "view_count": 0,
                "file_size": 5_000_000_000,
                "poster_url": "http://192.168.1.5:32400/thumb?X-Plex-Token=LIVE_TOKEN",
                "tmdb_id": 578,
            }
        )
        db.upsert_plex_user(
            user_id="plex-20",
            display_name="Member",
            email="member@example.com",
            plex_user_id="20",
            role="member",
        )

    def tearDown(self) -> None:
        self._jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        self._tmpdir.cleanup()

    def test_owner_library_query_keeps_internal_fields(self) -> None:
        resp = self.client.get("/api/library/query")
        self.assertEqual(resp.status_code, 200)
        item = resp.json()["items"][0]
        self.assertEqual(item["rating_key"], "rk-secret")
        self.assertEqual(item["file_size"], 5_000_000_000)
        self.assertNotIn("LIVE_TOKEN", resp.text)

    def test_member_library_query_uses_public_schema(self) -> None:
        # Sign in as the member (Plex id 20).
        self.client.post("/api/auth/logout")
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": 20, "title": "Member", "email": "member@example.com"},
        ):
            login = self.client.post("/api/auth/plex", json={"auth_token": "member-token"})
        self.assertEqual(login.status_code, 200)
        self.assertEqual(login.json()["user"]["role"], "member")

        resp = self.client.get("/api/library/query")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertGreaterEqual(body.get("total_matched", 0), 1)
        item = body["items"][0]
        self.assertEqual(item["title"], "Jaws")
        self.assertNotIn("rating_key", item)
        self.assertNotIn("file_size", item)
        self.assertNotIn("LIVE_TOKEN", resp.text)
        self.assertEqual(item.get("watch_state"), "unwatched")


if __name__ == "__main__":
    unittest.main()
