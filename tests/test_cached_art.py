"""EXP-006: authenticated cached art, and the SEC-013 fetch policy."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.library.art_egress import (
    ArtBlocked,
    ArtHttpResponse,
    ArtUnavailable,
    fetch_art,
    plan_art_fetch,
)
from projectionist.library.cached_art import ArtNotFound, load_cached_art, point_cached_art
from projectionist.library.db import Database
from projectionist.privacy.schema import public_image_urls, sanitize
from projectionist.theater.poster_cache import reset_poster_caches_for_tests
from projectionist.web.auth import clear_pin_bindings
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache
from tests.owner_claim_helpers import grant_owner_claim

JPEG = b"\xff\xd8\xff" + b"\x00" * 32
PLEX = "http://plex.household:32400"
TOKEN = "server-token"


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        plex_url=PLEX, plex_token=TOKEN, youth=SimpleNamespace(max_content_rating="PG-13")
    )


class ArtPolicyTests(unittest.TestCase):
    def test_plex_thumb_uses_the_server_token_and_drops_the_leaked_one(self) -> None:
        plan = plan_art_fetch(
            f"{PLEX}/library/metadata/5/thumb/9?X-Plex-Token=LEAKED",
            _settings(),
        )
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertNotIn("LEAKED", plan.url)
        self.assertNotIn(TOKEN, plan.url)
        self.assertEqual(plan.headers.get("X-Plex-Token"), TOKEN)
        self.assertFalse(plan.public)

    def test_relative_plex_path_stays_on_the_configured_origin(self) -> None:
        plan = plan_art_fetch("/library/metadata/5/thumb/9", _settings())
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertTrue(plan.url.startswith(f"{PLEX}/library/metadata/5/thumb/9"))

    def test_public_cdn_is_https_and_exact(self) -> None:
        plan = plan_art_fetch("https://image.tmdb.org/t/p/w500/abc.jpg", _settings())
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertTrue(plan.public)
        self.assertIsNone(plan_art_fetch("http://image.tmdb.org/t/p/w500/abc.jpg", _settings()))
        self.assertIsNone(plan_art_fetch("https://image.tmdb.org.evil.com/a.jpg", _settings()))
        self.assertIsNone(plan_art_fetch("https://169.254.169.254/latest/meta-data", _settings()))
        self.assertIsNone(plan_art_fetch("file:///etc/passwd", _settings()))

    def test_other_host_on_the_plex_port_is_refused(self) -> None:
        self.assertIsNone(
            plan_art_fetch("http://127.0.0.1:32400/library/metadata/1/thumb/1", _settings())
        )

    def test_path_escape_is_refused(self) -> None:
        self.assertIsNone(plan_art_fetch(f"{PLEX}/library/metadata/../admin", _settings()))

    def test_redirect_off_the_allowlist_is_refused(self) -> None:
        plan = plan_art_fetch("https://image.tmdb.org/t/p/w500/a.jpg", _settings())
        assert plan is not None

        async def _run() -> None:
            calls: list[str] = []

            async def fake(url, headers, *, public):
                del headers, public
                calls.append(url)
                return ArtHttpResponse(302, {"location": "http://127.0.0.1/secret"}, b"")

            with patch("projectionist.library.art_egress.request_art", fake):
                with self.assertRaises(ArtBlocked):
                    await fetch_art(plan, _settings())
            self.assertEqual(calls, ["https://image.tmdb.org/t/p/w500/a.jpg"])

        asyncio.run(_run())

    def test_html_is_not_cached_as_art(self) -> None:
        plan = plan_art_fetch("https://image.tmdb.org/t/p/w500/a.jpg", _settings())
        assert plan is not None

        async def fake(url, headers, *, public):
            del url, headers, public
            return ArtHttpResponse(200, {}, b"<html>nope</html>")

        async def _run() -> None:
            with patch("projectionist.library.art_egress.request_art", fake):
                with self.assertRaises(ArtUnavailable):
                    await fetch_art(plan, _settings())

        asyncio.run(_run())


class CachedArtUrlTests(unittest.TestCase):
    def test_plex_art_points_at_the_route_without_the_token(self) -> None:
        card = {
            "media_type": "movie",
            "title": "Purgatory",
            "tmdb_id": 238445,
            "rating_key": "rk-secret",
            "in_library": True,
            "poster_url": f"{PLEX}/library/metadata/5/thumb/9?X-Plex-Token=LEAKED",
            "backdrop_url": "https://image.tmdb.org/t/p/w780/bg.jpg",
        }
        pointed = point_cached_art(card, _settings())
        self.assertEqual(
            pointed["poster_url"],
            "/api/library/art/movie/238445?id_type=tmdb&kind=poster",
        )
        self.assertEqual(
            pointed["backdrop_url"],
            "/api/library/art/movie/238445?id_type=tmdb&kind=backdrop",
        )
        self.assertNotIn("LEAKED", json.dumps(pointed))
        self.assertNotIn("rk-secret", pointed["poster_url"])
        self.assertEqual(card["poster_url"].split("?")[-1], "X-Plex-Token=LEAKED")

    def test_titles_outside_the_library_keep_a_public_cdn_url(self) -> None:
        card = {
            "media_type": "movie",
            "tmdb_id": 1,
            "in_library": False,
            "poster_url": "https://image.tmdb.org/t/p/w500/x.jpg",
        }
        self.assertEqual(
            point_cached_art(card, _settings())["poster_url"],
            "https://image.tmdb.org/t/p/w500/x.jpg",
        )

    def test_sanitize_keeps_the_route_and_still_drops_a_raw_plex_url(self) -> None:
        images = public_image_urls(
            {
                "poster_url": "/api/library/art/movie/5?id_type=tmdb&kind=poster",
                "backdrop_url": "http://plex.local/thumb?X-Plex-Token=SECRET",
            }
        )
        self.assertEqual(
            images["poster_url"],
            "/api/library/art/movie/5?id_type=tmdb&kind=poster",
        )
        self.assertEqual(images["backdrop_url"], "")
        cleaned = sanitize(
            {"poster_url": "http://plex.local/thumb?X-Plex-Token=SECRET"},
            audience="member",
        )
        self.assertEqual(cleaned.get("poster_url") or "", "")
        self.assertNotIn("SECRET", json.dumps(cleaned))


class YouthArtTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "art.db")
        self.db.upsert_library_item(
            {
                "rating_key": "rk-r",
                "media_type": "movie",
                "title": "Late",
                "year": 1999,
                "poster_url": f"{PLEX}/library/metadata/1/thumb/1",
                "tmdb_id": 99,
                "content_rating": "R",
            }
        )
        reset_poster_caches_for_tests()

    def tearDown(self) -> None:
        reset_poster_caches_for_tests()
        self._tmpdir.cleanup()

    def test_youth_does_not_receive_an_r_rated_poster(self) -> None:
        youth = SimpleNamespace(is_youth=True, role="member", id="youth")

        async def _run() -> None:
            with self.assertRaises(ArtNotFound):
                await load_cached_art(
                    self.db,
                    _settings(),
                    media_type="movie",
                    item_id="99",
                    id_type="tmdb",
                    kind="poster",
                    user=youth,
                    data_dir=Path(self._tmpdir.name),
                )

        asyncio.run(_run())


class CachedArtApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-cached-art-session-secret"
        os.environ["LLM_PROVIDER"] = "ollama"
        self._saved = {key: os.environ.pop(key, None) for key in ("PLEX_URL", "PLEX_TOKEN")}
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        reset_poster_caches_for_tests()
        Path(self._tmpdir.name, "settings.json").write_text(
            json.dumps(
                {
                    "plex_url": PLEX,
                    "plex_token": TOKEN,
                    "features": {"multi_user_enabled": True},
                    "auth": {"mode": "plex", "plex_login_enabled": True},
                    "llm_provider": "ollama",
                    "onboarding_complete": True,
                }
            ),
            encoding="utf-8",
        )
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        app_mod.DATA_DIR = Path(self._tmpdir.name)
        self.client = TestClient(app_mod.app)
        grant_owner_claim(self.client)
        self._jobs = jobs
        with patch(
            "projectionist.web.auth.fetch_plex_account",
            return_value={"id": 10, "title": "Owner"},
        ):
            login = self.client.post("/api/auth/plex", json={"auth_token": "owner-token"})
        self.assertEqual(login.status_code, 200, login.text)
        db = jobs.get_job_manager().db
        db.upsert_library_item(
            {
                "rating_key": "rk-secret",
                "media_type": "movie",
                "title": "Purgatory",
                "year": 1999,
                "poster_url": f"{PLEX}/library/metadata/5/thumb/9?X-Plex-Token=LEAKED",
                "backdrop_url": "https://image.tmdb.org/t/p/w780/bg.jpg",
                "tmdb_id": 238445,
                "content_rating": "PG-13",
            }
        )

    def tearDown(self) -> None:
        self._jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        clear_pin_bindings()
        reset_poster_caches_for_tests()
        for key in (
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "DATA_DIR",
            "PLEX_URL",
            "PLEX_TOKEN",
        ):
            os.environ.pop(key, None)
        for key, value in self._saved.items():
            if value is not None:
                os.environ[key] = value
        self._tmpdir.cleanup()

    def test_search_points_at_the_route_and_a_credential_loads_the_poster(self) -> None:
        listed = self.client.get("/api/library/query")
        self.assertEqual(listed.status_code, 200, listed.text)
        item = listed.json()["items"][0]
        poster = item["poster_url"]
        backdrop = item["backdrop_url"]
        self.assertEqual(poster, "/api/library/art/movie/238445?id_type=tmdb&kind=poster")
        self.assertEqual(backdrop, "/api/library/art/movie/238445?id_type=tmdb&kind=backdrop")
        self.assertNotIn("LEAKED", listed.text)
        self.assertNotIn(TOKEN, listed.text)
        self.assertTrue(self.client.get("/api/features").json()["features"]["cached_art"])

        anon = TestClient(self.client.app)
        self.assertEqual(anon.get(poster).status_code, 401)

        calls: list[tuple[str, str]] = []

        async def fake(url, headers, *, public):
            calls.append((url, headers.get("X-Plex-Token", "")))
            self.assertNotIn("LEAKED", url)
            if public:
                return ArtHttpResponse(200, {}, b"RIFF" + b"\x00" * 4 + b"WEBP" + b"\x00" * 8)
            return ArtHttpResponse(200, {}, JPEG)

        with patch("projectionist.library.art_egress.request_art", fake):
            poster_resp = self.client.get(poster)
            backdrop_resp = self.client.get(backdrop)
        self.assertEqual(poster_resp.status_code, 200, poster_resp.text)
        self.assertEqual(poster_resp.headers["content-type"], "image/jpeg")
        self.assertEqual(poster_resp.content, JPEG)
        self.assertEqual(backdrop_resp.status_code, 200, backdrop_resp.text)
        self.assertEqual(backdrop_resp.headers["content-type"], "image/webp")
        self.assertIn("private", poster_resp.headers["cache-control"])
        self.assertEqual(calls[0][1], TOKEN)
        self.assertNotIn(TOKEN, calls[1][1])
        self.assertTrue(calls[1][0].startswith("https://image.tmdb.org/"))

        async def fail(url, headers, *, public):
            del url, headers, public
            raise AssertionError("cache should answer the second read")

        with patch("projectionist.library.art_egress.request_art", fail):
            again = self.client.get(poster)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.content, JPEG)

    def test_feeds_share_the_hub_poster_address(self) -> None:
        art = "/api/library/art/movie/238445?id_type=tmdb&kind=poster"
        db = self._jobs.get_job_manager().db
        now = int(time.time())
        db.upsert_library_item(
            {
                "rating_key": "rk-secret",
                "media_type": "movie",
                "title": "Purgatory",
                "year": 1999,
                "poster_url": f"{PLEX}/library/metadata/5/thumb/9?X-Plex-Token=LEAKED",
                "backdrop_url": "https://image.tmdb.org/t/p/w780/bg.jpg",
                "tmdb_id": 238445,
                "content_rating": "PG-13",
                "added_at": now - 1000,
                "view_count": 0,
                "view_offset_ms": 60_000,
                "duration_ms": 6_000_000,
            }
        )

        def posters(payload: object) -> list[str]:
            found: list[str] = []

            def walk(node: object) -> None:
                if isinstance(node, dict):
                    if node.get("rating_key") == "rk-secret" and "poster_url" in node:
                        found.append(str(node.get("poster_url") or ""))
                    for value in node.values():
                        walk(value)
                elif isinstance(node, list):
                    for value in node:
                        walk(value)

            walk(payload)
            return found

        with patch(
            "projectionist.connectors.plex.PlexClient.on_deck",
            side_effect=RuntimeError("plex on deck is down"),
        ):
            responses = {
                "hub": self.client.get("/api/library/feeds/hub"),
                "continue": self.client.get("/api/library/feeds/continue-watching"),
                "recent": self.client.get("/api/library/feeds/recently-added", params={"days": 7}),
                "search": self.client.get("/api/library/query", params={"query": "Purgatory"}),
                "title": self.client.get("/api/title/movie/238445"),
                "because": self.client.get("/api/library/feeds/for-you"),
                "holiday": self.client.get("/api/library/feeds/seasonal-spotlight"),
            }
        for name, response in responses.items():
            self.assertEqual(response.status_code, 200, f"{name} {response.text}")
        required = ("hub", "continue", "recent", "search", "title")
        seen: dict[str, list[str]] = {name: posters(response.json()) for name, response in responses.items()}
        for name in required:
            self.assertTrue(seen[name], name)
            self.assertEqual(set(seen[name]), {art}, name)
        for name, urls in seen.items():
            if urls:
                self.assertEqual(set(urls), {art}, name)
            self.assertNotIn("LEAKED", responses[name].text)


class SharedArtSerializerTests(unittest.TestCase):
    def test_related_holiday_and_live_match_a_library_card(self) -> None:
        from projectionist.library.cached_art import serialize_library_art, serialize_live_guide

        card = {
            "media_type": "movie",
            "title": "Purgatory",
            "tmdb_id": 238445,
            "rating_key": "rk-secret",
            "in_library": True,
            "poster_url": f"{PLEX}/library/metadata/5/thumb/9?X-Plex-Token=LEAKED",
            "backdrop_url": "https://image.tmdb.org/t/p/w780/bg.jpg",
        }
        expected = serialize_library_art(card, _settings())["poster_url"]
        self.assertEqual(expected, "/api/library/art/movie/238445?id_type=tmdb&kind=poster")
        related = serialize_library_art({"items": [{"peer": dict(card)}]}, _settings())
        holiday = serialize_library_art({"items": [dict(card)]}, _settings())
        self.assertEqual(related["items"][0]["peer"]["poster_url"], expected)
        self.assertEqual(holiday["items"][0]["poster_url"], expected)

        class _Library:
            def library_item_by_rating_key(self, key: str):
                self.last = key
                return dict(card)

        guide = {
            "channels": [
                {
                    "programs": [
                        {
                            "program": {
                                "type": "movie",
                                "title": "Purgatory",
                                "plexRatingKey": "rk-secret",
                            }
                        }
                    ]
                }
            ]
        }
        live = serialize_live_guide(guide, _Library(), _settings())
        program = live["channels"][0]["programs"][0]["program"]
        self.assertEqual(program["poster_url"], expected)
        self.assertNotIn("LEAKED", json.dumps(live))


if __name__ == "__main__":
    unittest.main()
