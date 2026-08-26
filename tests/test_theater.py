"""Lobby theater — snapshot, SSE, WAN gate, poster cache, watcher idle."""

from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from projectionist.config_store import Settings, TheaterSettings
from projectionist.connectors.plex import PlexActiveSession
from projectionist.library.db import Database
from projectionist.theater import POSTER_CACHE_CONTROL
from projectionist.theater.app import create_theater_app, theater_peer_allowed
from projectionist.theater.hub import TheaterHub, reset_theater_hub_for_tests
from projectionist.theater.normalize import normalize_theater_settings
from projectionist.theater.snapshot import (
    build_board_snapshot,
    filter_sessions,
    resolve_header_label,
)


def _session(
    *,
    user: str = "42",
    rating_key: str = "100",
    media_type: str = "movie",
    state: str = "playing",
    parent: str | None = None,
    progress_ms: int = 1_000,
    duration_ms: int = 10_000,
) -> PlexActiveSession:
    return PlexActiveSession(
        source_user_key=user,
        rating_key=rating_key,
        media_type=media_type,
        parent_rating_key=parent,
        progress_ms=progress_ms,
        duration_ms=duration_ms,
        client_identifier="client-1",
        session_key="sess-1",
        state=state,
    )


class NormalizeTheaterTests(unittest.TestCase):
    def test_clamps_rotate_and_label(self) -> None:
        theater = normalize_theater_settings(
            {
                "enabled": True,
                "orientation": "nope",
                "audience": "household",
                "idle_mode": "now_available",
                "multi_mode": "panelled",
                "header_mode": "static",
                "static_label": "X" * 40,
                "rotate_seconds": 3,
            }
        )
        self.assertEqual(theater.orientation, "landscape")
        self.assertEqual(theater.audience, "household")
        self.assertEqual(len(theater.static_label), 24)
        self.assertEqual(theater.rotate_seconds, 8)


class SnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        self.db = Database(self.data_dir / "projectionist.db")
        self.db.upsert_library_item(
            {
                "rating_key": "100",
                "media_type": "movie",
                "title": "Example",
                "year": 2020,
                "poster_url": "https://image.tmdb.org/t/p/w500/example.jpg",
                "added_at": int(time.time()) - 3600,
            }
        )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_filter_household_and_buffering(self) -> None:
        sessions = [
            _session(user="1", state="playing"),
            _session(user="9", state="playing", rating_key="101"),
            _session(user="1", state="buffering", rating_key="102"),
            _session(user="1", state="paused", rating_key="103"),
        ]
        kept = filter_sessions(sessions, audience="household", household_keys={"1"})
        self.assertEqual({s.rating_key for s in kept}, {"100", "103"})

    def test_hydrate_now_playing_omits_titles(self) -> None:
        settings = Settings(
            theater=TheaterSettings(enabled=True, idle_mode="now_available"),
        )
        snap = build_board_snapshot(
            self.db,
            settings,
            sessions=[_session()],
            fetch_sessions=False,
        )
        self.assertEqual(snap["mode"], "now_playing")
        self.assertTrue(snap["watching"])
        self.assertEqual(len(snap["sessions"]), 1)
        self.assertNotIn("title", snap["sessions"][0])
        self.assertIn("/api/theater/poster?rk=", snap["sessions"][0]["poster_url"])
        self.assertEqual(resolve_header_label(settings.theater, watching=True), "NOW PLAYING")

    def test_idle_now_available_deck(self) -> None:
        settings = Settings(
            theater=TheaterSettings(enabled=True, idle_mode="now_available"),
        )
        snap = build_board_snapshot(
            self.db,
            settings,
            sessions=[],
            fetch_sessions=False,
        )
        self.assertEqual(snap["mode"], "now_available")
        self.assertGreaterEqual(len(snap["available"]), 1)


class TheaterAppTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_theater_hub_for_tests()
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        self.db = Database(self.data_dir / "projectionist.db")
        self.db.upsert_library_item(
            {
                "rating_key": "100",
                "media_type": "movie",
                "title": "Example",
                "year": 2020,
                "poster_url": "https://image.tmdb.org/t/p/w500/example.jpg",
                "added_at": int(time.time()) - 3600,
            }
        )
        (self.data_dir / "settings.json").write_text(
            json.dumps(
                {
                    "theater": {
                        "enabled": True,
                        "idle_mode": "empty",
                        "orientation": "landscape",
                    }
                }
            ),
            encoding="utf-8",
        )
        self.settings = Settings.load(self.data_dir / "settings.json")
        self.app = create_theater_app(
            data_dir=self.data_dir,
            db_factory=lambda: self.db,
            settings_factory=lambda: self.settings,
        )
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        reset_theater_hub_for_tests()
        self._tmpdir.cleanup()

    def test_sse_hydrate_on_connect(self) -> None:
        import asyncio

        hub: TheaterHub = self.app.state.theater_hub

        async def first_event() -> str:
            agen = hub.subscribe()
            try:
                return await asyncio.wait_for(agen.__anext__(), timeout=2.0)
            finally:
                await agen.aclose()

        chunk = asyncio.run(first_event())
        self.assertIn("event: hydrate", chunk)
        self.assertIn('"mode"', chunk)

        # Route exists and is event-stream (don't hold the streaming body open).
        # TestClient.stream can hang on infinite generators; probe headers via hub above.
        routes = {getattr(route, "path", "") for route in self.app.routes}
        self.assertIn("/api/theater/events", routes)

    def test_wan_reject(self) -> None:
        request = MagicMock()
        request.client = MagicMock(host="8.8.8.8", port=12345)
        self.assertFalse(theater_peer_allowed(request))

        lan = MagicMock()
        lan.client = MagicMock(host="10.10.1.50", port=12345)
        self.assertTrue(theater_peer_allowed(lan))

        with patch("projectionist.theater.app.theater_peer_allowed", return_value=False):
            response = self.client.get("/")
            self.assertEqual(response.status_code, 403)

    def test_poster_cache_headers(self) -> None:
        fake_body = b"\xff\xd8\xfffakejpeg"
        with patch(
            "projectionist.theater.app.fetch_poster_bytes",
            return_value=(fake_body, "image/jpeg"),
        ):
            response = self.client.get("/api/theater/poster?rk=100")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), POSTER_CACHE_CONTROL)

    def test_zero_subscribers_no_plex_stampede(self) -> None:
        hub: TheaterHub = self.app.state.theater_hub
        before = hub.plex_call_count
        # Force a watcher tick with zero subscribers.
        hub._tick()
        self.assertEqual(hub.plex_call_count, before)

    def test_disabled_skips_plex(self) -> None:
        self.settings = Settings(theater=TheaterSettings(enabled=False))
        hub: TheaterHub = self.app.state.theater_hub
        hub.settings_factory = lambda: self.settings
        before = hub.plex_call_count
        # Even with a fake subscriber count, disabled path must not poll Plex.
        with patch.object(TheaterHub, "subscriber_count", property(lambda self: 1)):
            hub._tick()
        self.assertEqual(hub.plex_call_count, before)


class TheaterRoutesAbsentFromMainApp(unittest.TestCase):
    def test_main_app_has_no_theater_events_route(self) -> None:
        from projectionist.web.app import app

        paths = {getattr(route, "path", "") for route in app.routes}
        self.assertNotIn("/api/theater/events", paths)
        self.assertNotIn("/api/theater/poster", paths)


if __name__ == "__main__":
    unittest.main()
