"""Lobby theater — snapshot, SSE, WAN gate, poster cache, watcher idle."""

from __future__ import annotations

import asyncio
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from projectionist.circuit_breaker import host_circuits, reset_host_circuits
from projectionist.config_store import Settings, TheaterSettings
from projectionist.connectors.plex import PlexActiveSession
from projectionist.library.db import Database
from projectionist.theater import (
    POSTER_CACHE_CONTROL,
    POSTER_RATE_LIMIT_PER_MINUTE,
    WATCHER_POLL_ACTIVE_SECONDS,
    WATCHER_POLL_DEGRADED_SECONDS,
    WATCHER_POLL_IDLE_SECONDS,
)
from projectionist.theater.app import create_theater_app, theater_peer_allowed
from projectionist.theater.hub import TheaterHub, reset_theater_hub_for_tests
from projectionist.theater.normalize import normalize_theater_settings
from projectionist.theater.poster import fetch_poster_bytes
from projectionist.theater.poster_cache import (
    TheaterPosterCache,
    get_poster_cache,
    reset_poster_caches_for_tests,
)
from projectionist.theater.snapshot import (
    build_board_snapshot,
    filter_sessions,
    resolve_header_label,
)
from projectionist.web.rate_limit import clear_rate_limits


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

    def test_circuit_open_skips_plex_client(self) -> None:
        reset_host_circuits()
        settings = Settings(
            plex_url="http://plex.local:32400",
            plex_token="token",
            theater=TheaterSettings(enabled=True, idle_mode="empty"),
        )
        host_circuits.record_failure(settings.plex_url, "timeout")
        host_circuits.record_failure(settings.plex_url, "timeout")
        host_circuits.record_failure(settings.plex_url, "timeout")
        with patch("projectionist.theater.snapshot.PlexClient") as plex_cls:
            snap = build_board_snapshot(self.db, settings, fetch_sessions=True)
        plex_cls.assert_not_called()
        self.assertEqual(snap["mode"], "empty")
        reset_host_circuits()


class TheaterAppTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_theater_hub_for_tests()
        reset_poster_caches_for_tests()
        clear_rate_limits()
        reset_host_circuits()
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
        reset_poster_caches_for_tests()
        clear_rate_limits()
        reset_host_circuits()
        self._tmpdir.cleanup()

    def test_sse_hydrate_on_connect(self) -> None:
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
            return_value=(fake_body, "image/jpeg", '"abc"'),
        ):
            response = self.client.get("/api/theater/poster?rk=100")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("cache-control"), POSTER_CACHE_CONTROL)
        self.assertEqual(response.headers.get("etag"), '"abc"')

    def test_poster_etag_304(self) -> None:
        fake_body = b"\xff\xd8\xfffakejpeg"
        with patch(
            "projectionist.theater.app.fetch_poster_bytes",
            return_value=(fake_body, "image/jpeg", '"abc"'),
        ):
            response = self.client.get(
                "/api/theater/poster?rk=100",
                headers={"If-None-Match": '"abc"'},
            )
        self.assertEqual(response.status_code, 304)

    def test_zero_subscribers_no_plex_stampede(self) -> None:
        hub: TheaterHub = self.app.state.theater_hub
        before = hub.plex_call_count
        hub._tick()
        self.assertEqual(hub.plex_call_count, before)

    def test_disabled_skips_plex(self) -> None:
        self.settings = Settings(theater=TheaterSettings(enabled=False))
        hub: TheaterHub = self.app.state.theater_hub
        hub.settings_factory = lambda: self.settings
        before = hub.plex_call_count
        with patch.object(TheaterHub, "subscriber_count", property(lambda self: 1)):
            hub._tick()
        self.assertEqual(hub.plex_call_count, before)

    def test_adaptive_poll_idle_slower_than_active(self) -> None:
        hub: TheaterHub = self.app.state.theater_hub
        idle = hub.poll_interval_for_mode("now_available", degraded=False)
        active = hub.poll_interval_for_mode("now_playing", degraded=False)
        degraded = hub.poll_interval_for_mode("now_playing", degraded=True)
        self.assertEqual(idle, float(WATCHER_POLL_IDLE_SECONDS))
        self.assertEqual(active, float(WATCHER_POLL_ACTIVE_SECONDS))
        self.assertGreaterEqual(degraded, float(WATCHER_POLL_DEGRADED_SECONDS))
        self.assertGreater(idle, active)

    def test_circuit_open_watcher_skips_plex_increment(self) -> None:
        self.settings = Settings(
            plex_url="http://plex.local:32400",
            plex_token="token",
            theater=TheaterSettings(enabled=True, idle_mode="empty"),
        )
        hub: TheaterHub = self.app.state.theater_hub
        hub.settings_factory = lambda: self.settings
        host_circuits.record_failure(self.settings.plex_url, "timeout")
        host_circuits.record_failure(self.settings.plex_url, "timeout")
        host_circuits.record_failure(self.settings.plex_url, "timeout")
        before = hub.plex_call_count
        with patch.object(TheaterHub, "subscriber_count", property(lambda self: 1)):
            with patch(
                "projectionist.theater.hub.build_board_snapshot",
                return_value={
                    "enabled": True,
                    "mode": "empty",
                    "watching": False,
                    "sessions": [],
                    "available": [],
                    "header_label": "NOW PLAYING",
                    "header_mode": "dynamic",
                    "orientation": "landscape",
                    "multi_mode": "rotator",
                    "idle_mode": "empty",
                    "rotate_seconds": 12,
                },
            ) as snap:
                hub._tick()
        # Circuit open path must not count a Plex poll.
        self.assertEqual(hub.plex_call_count, before)
        snap.assert_called()
        self.assertTrue(hub.degraded)

    def test_poster_rate_limit(self) -> None:
        fake_body = b"\xff\xd8\xfffakejpeg"
        with patch(
            "projectionist.theater.app.fetch_poster_bytes",
            return_value=(fake_body, "image/jpeg", '"abc"'),
        ):
            last = None
            for _ in range(POSTER_RATE_LIMIT_PER_MINUTE + 5):
                last = self.client.get("/api/theater/poster?rk=100")
                if last.status_code == 429:
                    break
        self.assertIsNotNone(last)
        self.assertEqual(last.status_code, 429)

    def test_health_exposes_watcher_and_cache(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("watcher_interval_s", body)
        self.assertIn("poster_cache_hits", body)


class PosterCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        reset_poster_caches_for_tests()
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
            }
        )
        self.settings = Settings(theater=TheaterSettings(enabled=True))

    def tearDown(self) -> None:
        reset_poster_caches_for_tests()
        self._tmpdir.cleanup()

    def test_negative_cache_skips_second_upstream(self) -> None:
        calls = {"n": 0}

        async def boom(*_a, **_k):
            calls["n"] += 1
            raise HTTPException(status_code=404, detail="Poster not found")

        with patch("projectionist.theater.poster._upstream_fetch", side_effect=boom):
            with self.assertRaises(HTTPException):
                asyncio.run(
                    fetch_poster_bytes(
                        self.db,
                        self.settings,
                        rating_key="100",
                        data_dir=self.data_dir,
                    )
                )
            with self.assertRaises(HTTPException):
                asyncio.run(
                    fetch_poster_bytes(
                        self.db,
                        self.settings,
                        rating_key="100",
                        data_dir=self.data_dir,
                    )
                )
        self.assertEqual(calls["n"], 1)
        cache = get_poster_cache(self.data_dir)
        self.assertGreaterEqual(cache.negative_hits, 1)

    def test_positive_cache_and_single_flight(self) -> None:
        calls = {"n": 0}
        body = b"\xff\xd8\xffcached"

        async def once(*_a, **_k):
            calls["n"] += 1
            await asyncio.sleep(0.05)
            return body, "image/jpeg", "https://image.tmdb.org/t/p/w500/example.jpg"

        async def dual() -> None:
            with patch("projectionist.theater.poster._upstream_fetch", side_effect=once):
                a, b = await asyncio.gather(
                    fetch_poster_bytes(
                        self.db,
                        self.settings,
                        rating_key="100",
                        data_dir=self.data_dir,
                    ),
                    fetch_poster_bytes(
                        self.db,
                        self.settings,
                        rating_key="100",
                        data_dir=self.data_dir,
                    ),
                )
            self.assertEqual(a[0], body)
            self.assertEqual(b[0], body)

        asyncio.run(dual())
        self.assertEqual(calls["n"], 1)

        # Third call is a pure memory/disk hit — no upstream.
        with patch(
            "projectionist.theater.poster._upstream_fetch",
            side_effect=AssertionError("should not fetch"),
        ):
            cached = asyncio.run(
                fetch_poster_bytes(
                    self.db,
                    self.settings,
                    rating_key="100",
                    data_dir=self.data_dir,
                )
            )
        self.assertEqual(cached[0], body)

    def test_disk_hit_across_cache_instances(self) -> None:
        cache_a = TheaterPosterCache(self.data_dir)
        poster = cache_a.put(
            "100",
            b"\xff\xd8\xffdisk",
            "image/jpeg",
            source="https://image.tmdb.org/t/p/w500/example.jpg",
        )
        cache_b = TheaterPosterCache(self.data_dir)
        hit = cache_b.get("100")
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertEqual(hit.body, poster.body)
        self.assertEqual(hit.content_type, "image/jpeg")

    def test_single_flight_leader_cancel_terminates_waiters(self) -> None:
        """Leader CancelledError must complete the shared Future (no waiter hang)."""
        cache = TheaterPosterCache(self.data_dir)

        async def scenario() -> None:
            started = asyncio.Event()

            async def slow_factory() -> str:
                started.set()
                await asyncio.sleep(3600)
                return "never"

            def waiter_must_not_lead() -> str:
                raise AssertionError("waiter must join inflight, not become leader")

            leader = asyncio.create_task(cache.single_flight("rk-cancel", slow_factory))
            await started.wait()
            waiter = asyncio.create_task(
                cache.single_flight("rk-cancel", waiter_must_not_lead)
            )
            # Let the waiter attach to the shared Future.
            await asyncio.sleep(0)

            leader.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await leader

            # Pre-fix hang: shield(wait) never completed after leader cancel.
            with self.assertRaises(asyncio.CancelledError):
                await asyncio.wait_for(waiter, timeout=1.0)

            # Inflight cleared — a fresh flight can succeed.
            result = await cache.single_flight("rk-cancel", lambda: "retried")
            self.assertEqual(result, "retried")
            self.assertEqual(len(cache._inflight), 0)

        asyncio.run(scenario())


class TheaterRoutesAbsentFromMainApp(unittest.TestCase):
    def test_main_app_has_no_theater_events_route(self) -> None:
        from projectionist.web.app import app

        paths = {getattr(route, "path", "") for route in app.routes}
        self.assertNotIn("/api/theater/events", paths)
        self.assertNotIn("/api/theater/poster", paths)


if __name__ == "__main__":
    unittest.main()
