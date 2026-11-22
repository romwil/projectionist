"""Away address, home observation, and relative engine playlist URLs."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from projectionist.engine.audio import audio_transcode_command
from projectionist.engine.remux import remux_command, write_master
from projectionist.engine.session import EngineSession
from projectionist.public_url import PublicBaseUrlError, normalize_public_base_url
from projectionist.web.addresses import (
    addresses_payload,
    host_is_home,
    reset_observed_home,
)
from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import SESSION_COOKIE_NAME, clear_session_secret_cache, create_session_token


def _request(host: str, peer: str, headers: dict[str, str] | None = None):
    merged = {"host": host}
    if headers:
        merged.update(headers)
    return SimpleNamespace(
        headers=merged,
        url=SimpleNamespace(scheme="http", netloc=host),
        client=SimpleNamespace(host=peer, port=40000),
    )


class PublicBaseUrlNormalizationTests(unittest.TestCase):
    def test_origin_only(self) -> None:
        self.assertEqual(normalize_public_base_url(""), "")
        self.assertEqual(normalize_public_base_url("  "), "")
        self.assertEqual(
            normalize_public_base_url("https://films.example.com/"),
            "https://films.example.com",
        )
        self.assertEqual(
            normalize_public_base_url("http://10.1.2.3:8788"),
            "http://10.1.2.3:8788",
        )

    def test_rejects_anything_that_is_not_an_origin(self) -> None:
        rejected = [
            "ftp://films.example.com",
            "https://user:secret@films.example.com",
            "https://films.example.com/watch",
            "https://films.example.com?token=1",
            "https://films.example.com#room",
            "films.example.com",
            "javascript:alert(1)",
            "https://films.example.com/" + ("a" * 200),
        ]
        for raw in rejected:
            with self.subTest(raw=raw):
                with self.assertRaises(PublicBaseUrlError):
                    normalize_public_base_url(raw)


class HomeObservationTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_observed_home()

    def tearDown(self) -> None:
        reset_observed_home()
        os.environ.pop("PROJECTIONIST_TRUST_PROXY_HEADERS", None)

    def test_home_names(self) -> None:
        self.assertTrue(host_is_home("10.0.0.8:8788"))
        self.assertTrue(host_is_home("localhost:8788"))
        self.assertTrue(host_is_home("films.local"))
        self.assertTrue(host_is_home("[fe80::1]:8788"))
        self.assertTrue(host_is_home("100.64.1.2:8788"))
        self.assertFalse(host_is_home("films.example.com"))
        self.assertFalse(host_is_home("testserver"))

    def test_private_request_is_remembered_for_a_later_public_host(self) -> None:
        settings = SimpleNamespace(network=SimpleNamespace(public_base_url="https://films.example.com"))
        first = addresses_payload(_request("10.0.0.8:8788", "10.0.0.8"), settings)
        self.assertEqual(first["home"], "http://10.0.0.8:8788")
        self.assertEqual(first["away"], "https://films.example.com")
        later = addresses_payload(_request("films.example.com", "8.8.8.8"), settings)
        self.assertEqual(later["home"], "http://10.0.0.8:8788")
        self.assertEqual(later["away"], "https://films.example.com")

    def test_public_peer_cannot_plant_a_home_address(self) -> None:
        settings = SimpleNamespace(network=SimpleNamespace(public_base_url=""))
        planted = addresses_payload(_request("10.0.0.8:8788", "8.8.8.8"), settings)
        self.assertEqual(planted["home"], "")
        self.assertEqual(planted["away"], "")

    def test_trusted_proxy_uses_the_forwarded_client(self) -> None:
        os.environ["PROJECTIONIST_TRUST_PROXY_HEADERS"] = "1"
        settings = SimpleNamespace(network=SimpleNamespace(public_base_url=""))
        planted = addresses_payload(
            _request(
                "10.0.0.8:8788",
                "127.0.0.1",
                {"x-forwarded-for": "8.8.8.8", "x-forwarded-host": "10.0.0.8:8788"},
            ),
            settings,
        )
        self.assertEqual(planted["home"], "")
        home = addresses_payload(
            _request(
                "films.example.com",
                "127.0.0.1",
                {
                    "x-forwarded-for": "10.0.0.8",
                    "x-forwarded-host": "10.0.0.8:8788",
                    "x-forwarded-proto": "http",
                },
            ),
            settings,
        )
        self.assertEqual(home["home"], "http://10.0.0.8:8788")


class EnginePlaylistStaysRelativeTests(unittest.TestCase):
    def test_master_and_segments_have_no_host(self) -> None:
        away = "https://films.example.com"
        session = EngineSession(
            session_id="sess-1",
            token="token-1",
            rating_key="121986",
            user_id="owner",
            plan="remux",
            reason="The file can be remuxed.",
            playable=True,
            title="Heat",
            duration_ms=600_000,
            view_offset_ms=0,
            profile_id="apple-tv-4k-3",
        )
        master = session.master_url()
        self.assertTrue(master.startswith("/api/playback/sessions/"))
        self.assertNotIn(away, master)
        self.assertNotIn("http", master)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            write_master(folder, None, file_size=1000, duration_ms=600_000)
            playlist = (folder / "master.m3u8").read_text(encoding="utf-8")
        self.assertIn("av/stream.m3u8", playlist)
        self.assertNotIn("http://", playlist)
        self.assertNotIn("https://", playlist)
        self.assertNotIn(away, playlist)
        self.assertNotIn("-hls_base_url", remux_command("ffmpeg", Path("film.mkv")))
        self.assertNotIn(
            "-hls_base_url",
            audio_transcode_command("ffmpeg", Path("film.mkv"), "aac"),
        )


class PublicBaseUrlApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-public-base-url-session-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        reset_observed_home()
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        reset_observed_home()
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        for key in (
            "DATA_DIR",
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_owner_sets_the_away_address_and_features_publish_both(self) -> None:
        saved = self.client.put(
            "/api/network/public-base-url",
            json={"public_base_url": "https://films.example.com/"},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["public_base_url"], "https://films.example.com")
        home = TestClient(self.app_mod.app, base_url="http://10.0.0.8:8788")
        body = home.get("/api/features").json()
        self.assertEqual(body["capabilities"]["household_addresses"], 1)
        self.assertEqual(body["addresses"]["away"], "https://films.example.com")
        self.assertEqual(body["addresses"]["home"], "http://10.0.0.8:8788")
        again = self.client.get("/api/features").json()
        self.assertEqual(again["addresses"]["home"], "http://10.0.0.8:8788")
        self.assertEqual(again["addresses"]["away"], "https://films.example.com")
        cleared = self.client.put("/api/network/public-base-url", json={"public_base_url": ""})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertEqual(cleared.json()["public_base_url"], "")

    def test_a_bad_address_is_refused_and_a_settings_put_keeps_a_good_one(self) -> None:
        saved = self.client.put(
            "/api/network/public-base-url",
            json={"public_base_url": "https://films.example.com"},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        rejected = self.client.put(
            "/api/network/public-base-url",
            json={"public_base_url": "https://films.example.com/watch"},
        )
        self.assertEqual(rejected.status_code, 400, rejected.text)
        self.assertIn("path", rejected.json()["detail"].lower())
        kept = self.client.get("/api/network/public-base-url")
        self.assertEqual(kept.json()["public_base_url"], "https://films.example.com")
        wiped = self.client.put("/api/settings", json={"llm_provider": "ollama"})
        self.assertEqual(wiped.status_code, 200, wiped.text)
        self.assertEqual(
            self.client.get("/api/network/public-base-url").json()["public_base_url"],
            "https://films.example.com",
        )

    def test_signed_out_clients_do_not_receive_addresses_and_members_cannot_set_one(self) -> None:
        path = Path(self._tmpdir.name) / "settings.json"
        path.write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "local", "local_login_enabled": True},
                    "llm_provider": "ollama",
                    "network": {"public_base_url": "https://films.example.com"},
                }
            ),
            encoding="utf-8",
        )
        public = self.client.get("/api/features")
        self.assertEqual(public.status_code, 200, public.text)
        self.assertNotIn("addresses", public.json())
        self.assertEqual(public.json()["capabilities"]["household_addresses"], 1)
        db = self.app_mod._db()
        db.upsert_plex_user(
            user_id="member-1",
            display_name="Member",
            email=None,
            plex_user_id="2",
            role="member",
        )
        db.upsert_plex_user(
            user_id="owner-1",
            display_name="Owner",
            email=None,
            plex_user_id="1",
            role="owner",
        )
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("member-1"))
        denied = self.client.put(
            "/api/network/public-base-url",
            json={"public_base_url": "https://evil.example"},
        )
        self.assertEqual(denied.status_code, 403, denied.text)
        seen = self.client.get("/api/features")
        self.assertEqual(seen.status_code, 200, seen.text)
        self.assertEqual(seen.json()["addresses"]["away"], "https://films.example.com")
        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token("owner-1"))
        allowed = self.client.get("/api/network/public-base-url")
        self.assertEqual(allowed.status_code, 200, allowed.text)
        self.assertEqual(allowed.json()["public_base_url"], "https://films.example.com")
