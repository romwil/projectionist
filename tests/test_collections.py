"""Collections/courses: publish-to-members + ordered sequencing (M4)."""

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


class CollectionsDbTests(unittest.TestCase):
    def test_course_kind_visibility_and_step_note(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            created = db.create_curated_list(
                list_id="c1", user_id=None, name="Kurosawa 101", list_kind="course"
            )
            self.assertEqual(created["list_kind"], "course")
            self.assertEqual(created["visibility"], "private")

            item = db.add_curated_list_item(
                item_id="i1", list_id="c1", user_id=None,
                tmdb_id=11, tvdb_id=None, media_type="movie", title="Ran",
            )
            self.assertEqual(item["note"], "")

            updated = db.update_curated_list_item(
                "c1", "i1", user_id=None, note="Start here", position=3
            )
            assert updated is not None
            self.assertEqual(updated["note"], "Start here")
            self.assertEqual(updated["position"], 3)

            published = db.set_curated_list_visibility("c1", user_id=None, visibility="published")
            assert published is not None
            self.assertEqual(published["visibility"], "published")
            self.assertIsNotNone(published["published_at"])

            self.assertEqual(len(db.list_published_lists()), 1)
            detail = db.get_published_list("c1", include_items=True)
            assert detail is not None
            self.assertEqual(len(detail["items"]), 1)
            self.assertEqual(detail["items"][0]["note"], "Start here")

    def test_private_list_not_in_published_read_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            db.create_curated_list(list_id="c1", user_id=None, name="Secret")
            self.assertEqual(db.list_published_lists(), [])
            self.assertIsNone(db.get_published_list("c1"))

    def test_unpublish_clears_published_at(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "t.db")
            db.create_curated_list(list_id="c1", user_id=None, name="Toggle")
            db.set_curated_list_visibility("c1", user_id=None, visibility="published")
            back = db.set_curated_list_visibility("c1", user_id=None, visibility="private")
            assert back is not None
            self.assertEqual(back["visibility"], "private")
            self.assertIsNone(back["published_at"])


class CollectionsApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-collections-secret"
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

    def test_implicit_owner_publish_flow(self) -> None:
        create = self.client.post("/api/lists", json={"name": "Noir", "list_kind": "course"})
        self.assertEqual(create.status_code, 200)
        list_id = create.json()["id"]
        item = self.client.post(
            f"/api/lists/{list_id}/items",
            json={"title": "Heat", "media_type": "movie", "tmdb_id": 949},
        )
        self.assertEqual(item.status_code, 200)
        item_id = item.json()["id"]

        patch_item = self.client.patch(
            f"/api/lists/{list_id}/items/{item_id}", json={"note": "Watch first", "position": 1}
        )
        self.assertEqual(patch_item.status_code, 200)
        self.assertEqual(patch_item.json()["note"], "Watch first")

        publish = self.client.patch(f"/api/lists/{list_id}", json={"visibility": "published"})
        self.assertEqual(publish.status_code, 200)
        self.assertEqual(publish.json()["visibility"], "published")

        collections = self.client.get("/api/collections")
        self.assertEqual(collections.status_code, 200)
        self.assertEqual(collections.json()["count"], 1)
        detail = self.client.get(f"/api/collections/{list_id}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["items"][0]["note"], "Watch first")

    def test_member_can_read_published_but_not_publish(self) -> None:
        self._enable_multi_user()
        with patch(
            "curatorx.web.auth.fetch_plex_account",
            return_value={"id": 1, "title": "Owner"},
        ):
            self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})
        owner_db = self.app_mod._db()
        # Owner publishes a shared (NULL-user) collection.
        owner_db.create_curated_list(list_id="shared", user_id=None, name="Shared picks")
        owner_db.set_curated_list_visibility("shared", user_id=None, visibility="published")

        import curatorx.web.jobs as jobs

        jobs.get_job_manager().db.upsert_plex_user(
            user_id="plex-55",
            display_name="Member",
            email="m@example.com",
            plex_user_id="55",
            role="member",
        )
        member = TestClient(self.app_mod.app)
        member.cookies.set(SESSION_COOKIE_NAME, create_session_token("plex-55"))

        # Member can read published collections.
        self.assertEqual(member.get("/api/collections").json()["count"], 1)
        self.assertEqual(member.get("/api/collections/shared").status_code, 200)

        # Member creates their own list and cannot publish it.
        created = member.post("/api/lists", json={"name": "Mine"})
        self.assertEqual(created.status_code, 200)
        mine_id = created.json()["id"]
        blocked = member.patch(f"/api/lists/{mine_id}", json={"visibility": "published"})
        self.assertEqual(blocked.status_code, 403)


if __name__ == "__main__":
    unittest.main()
