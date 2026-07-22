"""Tests for Delight Phase 4: youth rating gate + access requests."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from curatorx.config_store import Settings, YouthSettings
from curatorx.library.db import Database
from curatorx.library.query import LibraryFilters, filters_from_mapping, query_library
from curatorx.youth.rating_gate import (
    content_rating_allowed,
    filter_items_for_youth,
    normalize_content_rating,
)
from curatorx.youth.apply import apply_youth_gate_to_filters
from curatorx.access_requests import approve_access_request, notify_owners_of_access_request
from curatorx.web.auth import clear_pin_bindings
from curatorx.web.rate_limit import clear_rate_limits
from curatorx.web.session_tokens import clear_session_secret_cache


class RatingGateUnitTests(unittest.TestCase):
    def test_normalize_and_fail_closed(self) -> None:
        self.assertEqual(normalize_content_rating("PG-13"), "PG-13")
        self.assertEqual(normalize_content_rating("pg13"), "PG-13")
        self.assertEqual(normalize_content_rating(""), "")
        self.assertEqual(normalize_content_rating("Not Rated"), "")
        self.assertFalse(content_rating_allowed("", max_rating="PG-13"))
        self.assertFalse(content_rating_allowed("R", max_rating="PG-13"))
        self.assertTrue(content_rating_allowed("PG", max_rating="PG-13"))
        self.assertTrue(content_rating_allowed("TV-PG", max_rating="PG-13"))

    def test_filter_items_drops_unrated_and_over_max(self) -> None:
        items = [
            {"title": "A", "content_rating": "G"},
            {"title": "B", "content_rating": ""},
            {"title": "C", "content_rating": "R"},
            {"title": "D", "content_rating": "PG-13"},
        ]
        kept = filter_items_for_youth(items, max_rating="PG-13")
        titles = [i["title"] for i in kept]
        self.assertEqual(titles, ["A", "D"])


class RatingGateDbTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "curatorx.db")
        for key, title, rating in (
            ("rk-g", "Good Family", "G"),
            ("rk-r", "Rough Cut", "R"),
            ("rk-empty", "Mystery Box", ""),
        ):
            self.db.upsert_library_item(
                {
                    "rating_key": key,
                    "media_type": "movie",
                    "title": title,
                    "year": 2000,
                    "content_rating": rating,
                    "view_count": 0,
                }
            )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_query_youth_max_fail_closed(self) -> None:
        filters = LibraryFilters(youth_max_content_rating="PG-13", limit=50)
        result = query_library(self.db, filters)
        titles = {item["title"] for item in result["items"]}
        self.assertIn("Good Family", titles)
        self.assertNotIn("Rough Cut", titles)
        self.assertNotIn("Mystery Box", titles)

    def test_apply_youth_gate_to_filters(self) -> None:
        class User:
            is_youth = True

        settings = Settings(youth=YouthSettings(max_content_rating="PG"))
        filters = apply_youth_gate_to_filters(
            filters_from_mapping({"limit": 10}),
            user=User(),
            settings=settings,
        )
        self.assertEqual(filters.youth_max_content_rating, "PG")


class AccessRequestTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-access-session-secret-value"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = Database(Path(self._tmpdir.name) / "curatorx.db")
        self.db.create_local_user(
            user_id="owner-1",
            display_name="Owner",
            password_hash="x",
            role="owner",
            email="owner@example.com",
        )

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        self._tmpdir.cleanup()

    def test_create_access_request_public(self) -> None:
        response = self.client.post(
            "/api/access-requests",
            json={"display_name": "Casey", "email": "c@example.com", "message": "Hi"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["request"]["status"], "pending")
        rows = self.db.list_access_requests(status="pending")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["display_name"], "Casey")

    def test_approve_creates_local_member_when_enabled(self) -> None:
        row = self.db.create_access_request(display_name="Riley", email="r@example.com")
        settings = Settings()
        settings.auth.local_login_enabled = True
        result = approve_access_request(
            self.db,
            settings,
            request_id=row["id"],
            owner_id="owner-1",
        )
        self.assertEqual(result["request"]["status"], "approved")
        self.assertIsNotNone(result["temporary_password"])
        self.assertEqual(result["user"]["role"], "member")

    def test_notify_owners_creates_access_request_kind(self) -> None:
        row = self.db.create_access_request(display_name="Sam")
        notify_owners_of_access_request(self.db, Settings(), row)
        notes = self.db.list_notifications_for_user("owner-1", kinds=["access-request"])
        self.assertTrue(notes)
        self.assertEqual(notes[0]["kind"], "access-request")


if __name__ == "__main__":
    unittest.main()
