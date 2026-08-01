"""Tests for household recommendations and UI font preference."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.connectors.plex import cached_plex_friendly_name, cached_plex_identity
from projectionist.library.db import Database
from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


class RecommendationsAndPrefsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["CURATORX_SESSION_SECRET"] = "test-recs-session-secret-value"
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        # Reset plex identity cache between tests
        import projectionist.connectors.plex as plex_mod

        plex_mod._cached_plex_identity = None

        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("CURATORX_SESSION_SECRET", None)
        self._tmpdir.cleanup()

    def _enable_multi_user(self) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        payload = {
            "features": {"multi_user_enabled": True, "open_auto_provision": True},
            "auth": {"mode": "plex", "plex_login_enabled": True},
            "llm_provider": "ollama",
        }
        path.write_text(json.dumps(payload), encoding="utf-8")

    def _login(self, *, plex_id: int, title: str, email: str) -> dict:
        profile = {
            "id": plex_id,
            "title": title,
            "email": email,
            "thumb": None,
        }
        with patch("projectionist.web.auth.fetch_plex_account", return_value=profile):
            resp = self.client.post("/api/auth/plex", json={"auth_token": f"tok-{plex_id}"})
        self.assertEqual(resp.status_code, 200)
        return resp.json()["user"]

    def test_font_size_preference_round_trip(self) -> None:
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"].get("ui_font_size", "medium"), "medium")

        patched = self.client.patch("/api/auth/me", json={"ui_font_size": "large"})
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["user"]["ui_font_size"], "large")

        again = self.client.get("/api/auth/me")
        self.assertEqual(again.json()["user"]["ui_font_size"], "large")

    def test_ui_theme_preference_round_trip(self) -> None:
        me = self.client.get("/api/auth/me")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"].get("ui_theme", "system"), "system")

        patched = self.client.patch("/api/auth/me", json={"ui_theme": "lights_down"})
        self.assertEqual(patched.status_code, 200)
        self.assertEqual(patched.json()["user"]["ui_theme"], "lights_down")

        again = self.client.get("/api/auth/me")
        self.assertEqual(again.json()["user"]["ui_theme"], "lights_down")

        up = self.client.patch("/api/auth/me", json={"ui_theme": "lights_up"})
        self.assertEqual(up.status_code, 200)
        self.assertEqual(up.json()["user"]["ui_theme"], "lights_up")

    def test_library_stats_include_plex_server_name(self) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "plex_url": "http://plex.test",
                    "plex_token": "token",
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        with patch(
            "projectionist.web.app.cached_plex_friendly_name",
            return_value="Automat818",
        ):
            resp = self.client.get("/api/library/stats")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["plex_server_name"], "Automat818")
        self.assertIn("movies", body)
        self.assertIn("shows", body)

    def test_recommend_and_mark_seen(self) -> None:
        self._enable_multi_user()
        owner = self._login(plex_id=1, title="Owner", email="owner@example.com")
        # Second user needs a separate client/session
        member_client = TestClient(self.app_mod.app)
        profile = {
            "id": 2,
            "title": "Member",
            "email": "member@example.com",
            "thumb": None,
        }
        with patch("projectionist.web.auth.fetch_plex_account", return_value=profile):
            member_login = member_client.post("/api/auth/plex", json={"auth_token": "tok-2"})
        self.assertEqual(member_login.status_code, 200)
        member = member_login.json()["user"]

        peers = self.client.get("/api/household/peers")
        self.assertEqual(peers.status_code, 200)
        peer_ids = {item["id"] for item in peers.json()["items"]}
        self.assertIn(member["id"], peer_ids)
        self.assertNotIn(owner["id"], peer_ids)

        created = self.client.post(
            "/api/recommendations",
            json={
                "to_user_ids": [member["id"]],
                "media_type": "movie",
                "title": "Assassins",
                "tmdb_id": 3595,
                "year": 1995,
                "message": "You'll dig this",
            },
        )
        self.assertEqual(created.status_code, 200)
        self.assertEqual(created.json()["count"], 1)

        inbox = member_client.get("/api/recommendations?unread_only=true")
        self.assertEqual(inbox.status_code, 200)
        body = inbox.json()
        self.assertEqual(body["unread_count"], 1)
        self.assertEqual(body["items"][0]["title"], "Assassins")
        self.assertEqual(body["items"][0]["from_display_name"], "Owner")
        rec_id = body["items"][0]["id"]

        seen = member_client.post("/api/recommendations/seen", json={"ids": [rec_id]})
        self.assertEqual(seen.status_code, 200)
        self.assertEqual(seen.json()["updated"], 1)

        empty = member_client.get("/api/recommendations?unread_only=true")
        self.assertEqual(empty.json()["unread_count"], 0)
        self.assertEqual(empty.json()["count"], 0)

    def test_watch_party_intent_lands_in_notification_payload(self) -> None:
        self._enable_multi_user()
        self._login(plex_id=10, title="Owner", email="owner-wp@example.com")
        member_client = TestClient(self.app_mod.app)
        profile = {
            "id": 11,
            "title": "Member",
            "email": "member-wp@example.com",
            "thumb": None,
        }
        with patch("projectionist.web.auth.fetch_plex_account", return_value=profile):
            member_login = member_client.post("/api/auth/plex", json={"auth_token": "tok-11"})
        self.assertEqual(member_login.status_code, 200)
        member = member_login.json()["user"]

        created = self.client.post(
            "/api/recommendations",
            json={
                "to_user_ids": [member["id"]],
                "media_type": "movie",
                "title": "Heat",
                "tmdb_id": 949,
                "year": 1995,
                "message": "Watch together tonight?",
                "intent": "watch_party",
            },
        )
        self.assertEqual(created.status_code, 200)
        inbox = member_client.get("/api/notifications?unread_only=true")
        self.assertEqual(inbox.status_code, 200)
        items = inbox.json()["items"]
        self.assertTrue(items)
        match = next((row for row in items if row.get("kind") == "recommendation"), None)
        self.assertIsNotNone(match)
        self.assertEqual(match["title"], "Heat")
        self.assertEqual((match.get("payload") or {}).get("intent"), "watch_party")

    def test_share_saved_library_page_notifies_household(self) -> None:
        self._enable_multi_user()
        owner = self._login(plex_id=20, title="Owner", email="owner-share@example.com")
        member_client = TestClient(self.app_mod.app)
        profile = {
            "id": 21,
            "title": "Member",
            "email": "member-share@example.com",
            "thumb": None,
        }
        with patch("projectionist.web.auth.fetch_plex_account", return_value=profile):
            member_login = member_client.post("/api/auth/plex", json={"auth_token": "tok-21"})
        self.assertEqual(member_login.status_code, 200)
        member = member_login.json()["user"]

        saved = self.client.post(
            "/api/saved-library",
            json={
                "name": "Noir night picks",
                "content": {"blocks": [{"kind": "text", "content": "Two rainy-night titles."}]},
            },
        )
        self.assertEqual(saved.status_code, 200)
        page_id = saved.json()["id"]

        shared = self.client.post(
            f"/api/saved-library/{page_id}/share",
            json={"to_user_ids": [member["id"]], "message": "For Friday"},
        )
        self.assertEqual(shared.status_code, 200)
        self.assertEqual(shared.json()["count"], 1)

        inbox = member_client.get("/api/notifications?unread_only=true&kind=library-share")
        self.assertEqual(inbox.status_code, 200)
        items = inbox.json()["items"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kind"], "library-share")
        self.assertEqual(items[0]["title"], "Noir night picks")
        self.assertEqual(items[0]["payload"]["page_id"], page_id)
        self.assertEqual(items[0]["payload"]["path"], f"/library/{page_id}")
        self.assertEqual(items[0]["from_display_name"], owner["display_name"] or "Owner")

    def test_cached_plex_friendly_name(self) -> None:
        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def server_identity(self):
                return ("machine-1", "Automat818")

        with patch("projectionist.connectors.plex.PlexClient", FakeClient):
            name = cached_plex_friendly_name("http://plex", "tok")
            again = cached_plex_identity("http://plex", "tok")
        self.assertEqual(name, "Automat818")
        self.assertEqual(again, ("machine-1", "Automat818"))


if __name__ == "__main__":
    unittest.main()
