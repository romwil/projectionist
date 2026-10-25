"""In-browser library Play — resolve, rewrite, youth, progress, hostile keys."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.config_store import Settings, YouthSettings
from projectionist.library.db import Database
from projectionist.library.playback import (
    PlaybackError,
    PlaybackSession,
    YouthBlockedError,
    assert_youth_allowed,
    plex_fetch_path,
    proxy_session_asset,
    report_progress,
    reset_playback_sessions,
    resolve_playable_item,
    rewrite_plex_hls_playlist,
    seek_playback,
    should_resume_from_offset,
    should_send_progress,
    start_playback,
    strip_secret_query,
    universal_start_url,
    validate_playback_path,
    validate_rating_key,
)
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


def _show_with_episodes(db: Database) -> int:
    show_id = db.upsert_library_item(
        {
            "rating_key": "show-1",
            "media_type": "show",
            "title": "The Wire",
            "content_rating": "TV-MA",
            "view_count": 0,
        }
    )
    db.upsert_library_episode(
        {
            "show_item_id": show_id,
            "rating_key": "ep-1",
            "season_number": 1,
            "episode_number": 1,
            "title": "The Target",
            "view_count": 1,
            "view_offset_ms": 0,
            "duration_ms": 3_600_000,
        }
    )
    db.upsert_library_episode(
        {
            "show_item_id": show_id,
            "rating_key": "ep-2",
            "season_number": 1,
            "episode_number": 2,
            "title": "The Detail",
            "view_count": 0,
            "view_offset_ms": 180_000,
            "duration_ms": 3_600_000,
        }
    )
    db.upsert_library_episode(
        {
            "show_item_id": show_id,
            "rating_key": "ep-3",
            "season_number": 1,
            "episode_number": 3,
            "title": "The Buys",
            "view_count": 0,
            "view_offset_ms": 0,
            "duration_ms": 3_600_000,
        }
    )
    return show_id


class PlaybackResolveTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "play.db")
        self.db.upsert_library_item(
            {
                "rating_key": "movie-1",
                "media_type": "movie",
                "title": "Heat",
                "content_rating": "R",
                "view_offset_ms": 10_000,
                "duration_ms": 10_200_000,
            }
        )
        _show_with_episodes(self.db)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_movie_plays_as_is(self) -> None:
        item = resolve_playable_item(self.db, "movie-1")
        self.assertEqual(item["media_type"], "movie")
        self.assertEqual(item["rating_key"], "movie-1")
        self.assertEqual(item["view_offset_ms"], 10_000)

    def test_show_resolves_to_on_deck_episode(self) -> None:
        item = resolve_playable_item(self.db, "show-1")
        self.assertEqual(item["media_type"], "episode")
        self.assertEqual(item["rating_key"], "ep-2")
        self.assertEqual(item["title"], "The Detail")
        self.assertEqual(item["season"], 1)

    def test_episode_key_plays_and_next_exists(self) -> None:
        item = resolve_playable_item(self.db, "ep-2")
        self.assertEqual(item["rating_key"], "ep-2")
        self.assertEqual(item["show_title"], "The Wire")

    def test_missing_key_404(self) -> None:
        with self.assertRaises(PlaybackError) as ctx:
            resolve_playable_item(self.db, "nope")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_hostile_rating_keys(self) -> None:
        for raw in ("", "../etc/passwd", "http://evil.test/1", "a" * 200, "bad key", "javascript:alert(1)"):
            with self.subTest(raw=raw):
                with self.assertRaises(PlaybackError):
                    validate_rating_key(raw)

    def test_hostile_stream_paths(self) -> None:
        with self.assertRaises(PlaybackError):
            validate_playback_path("../secret")
        with self.assertRaises(PlaybackError):
            validate_playback_path("https://plex.local/video")


class PlaylistRewriteTests(unittest.TestCase):
    def test_rewrite_strips_plex_host_and_token(self) -> None:
        body = (
            "#EXTM3U\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=800000\n"
            "http://plex.test:32400/video/:/transcode/universal/session/abc/base/index.m3u8?X-Plex-Token=SECRET&X-Plex-Session-Identifier=1\n"
            '#EXT-X-KEY:METHOD=AES-128,URI="http://plex.test:32400/library/keys/1?X-Plex-Token=SECRET"\n'
        )
        out = rewrite_plex_hls_playlist(
            body,
            session_id="sess-1",
            plex_base="http://plex.test:32400",
            playlist_path="index.m3u8",
        )
        self.assertNotIn("plex.test", out)
        self.assertNotIn("SECRET", out)
        self.assertNotIn("X-Plex-Token", out)
        self.assertIn("/api/library/playback/sess-1/", out)
        self.assertIn("X-Plex-Session-Identifier=1", out)

    def test_relative_segment_stays_on_proxy(self) -> None:
        body = "#EXTM3U\n#EXTINF:4.0,\nsegment0.ts\n"
        out = rewrite_plex_hls_playlist(
            body,
            session_id="sess-9",
            plex_base="http://10.10.1.9:32400",
            playlist_path="video/session/base/index.m3u8",
        )
        self.assertIn("/api/library/playback/sess-9/", out)
        self.assertNotIn("10.10.1.9", out)

    def test_relative_session_uri_resolves_under_universal(self) -> None:
        """Plex masters emit session/… relatives; bare index.m3u8 must not root them."""
        body = (
            "#EXTM3U\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=800000\n"
            "session/abc/base/index.m3u8\n"
        )
        out = rewrite_plex_hls_playlist(
            body,
            session_id="sess-1",
            plex_base="http://plex.test:32400",
            playlist_path="index.m3u8",
        )
        self.assertIn(
            "/api/library/playback/sess-1/video/:/transcode/universal/session/abc/base/index.m3u8",
            out,
        )
        self.assertNotIn("/api/library/playback/sess-1/session/", out)

    def test_plex_fetch_path_prefixes_bare_session(self) -> None:
        self.assertEqual(
            plex_fetch_path("session/abc/base/index.m3u8"),
            "video/:/transcode/universal/session/abc/base/index.m3u8",
        )
        self.assertEqual(plex_fetch_path("index.m3u8"), "video/:/transcode/universal/start.m3u8")

    def test_proxy_fetches_universal_prefixed_session_path(self) -> None:
        session = PlaybackSession(
            session_id="sess-proxy",
            user_id="owner",
            rating_key="ep-1",
            plex_base="http://plex.test:32400",
            token="tok",
        )
        seen: list[str] = []

        def fake_fetch(url, **_kwargs):
            seen.append(url)
            return (
                b"#EXTM3U\n#EXTINF:4.0,\n0.ts\n",
                "application/vnd.apple.mpegurl",
                200,
                url,
            )

        asset = proxy_session_asset(
            session,
            "session/sess-proxy/base/index.m3u8",
            fetch=fake_fetch,
        )
        self.assertEqual(len(seen), 1)
        self.assertIn(
            "http://plex.test:32400/video/:/transcode/universal/session/sess-proxy/base/index.m3u8",
            seen[0],
        )
        self.assertIn(
            "/api/library/playback/sess-proxy/video/:/transcode/universal/session/sess-proxy/base/0.ts",
            asset["body"].decode(),
        )

    def test_strip_secret_query(self) -> None:
        self.assertEqual(
            strip_secret_query("/p?X-Plex-Token=abc&keep=1"),
            "/p?keep=1",
        )


class YouthAndProgressTests(unittest.TestCase):
    def test_youth_rejects_missing_and_over_ceiling(self) -> None:
        user = type("U", (), {"is_youth": True})()
        settings = Settings(youth=YouthSettings(max_content_rating="PG-13"))
        with self.assertRaises(YouthBlockedError):
            assert_youth_allowed(user, settings, {"content_rating": ""})
        with self.assertRaises(YouthBlockedError):
            assert_youth_allowed(user, settings, {"content_rating": "R"})
        assert_youth_allowed(user, settings, {"content_rating": "PG"})

    def test_resume_threshold(self) -> None:
        self.assertFalse(should_resume_from_offset(119_999))
        self.assertTrue(should_resume_from_offset(120_000))

    def test_progress_throttle(self) -> None:
        self.assertTrue(should_send_progress(None, 10))
        self.assertFalse(should_send_progress(1.0, 9.0))
        self.assertTrue(should_send_progress(1.0, 11.1))

    def test_universal_start_disables_burned_in_subtitles(self) -> None:
        url = universal_start_url(
            "http://plex.test:32400",
            "42",
            session_id="sess-1",
            offset_seconds=15,
        )
        self.assertIn("subtitles=none", url)
        self.assertIn("offset=15", url)
        self.assertNotIn("subtitleStreamID=", url)
        self.assertNotIn("advancedSubtitles=", url)

    def test_universal_start_burns_selected_plex_stream(self) -> None:
        url = universal_start_url(
            "http://plex.test:32400",
            "42",
            session_id="sess-1",
            offset_seconds=90,
            subtitle_stream_id="9003",
        )
        self.assertIn("subtitles=burn", url)
        self.assertIn("subtitleStreamID=9003", url)
        self.assertIn("advancedSubtitles=burn", url)
        self.assertNotIn("subtitles=none", url)
        self.assertIn("offset=90", url)


class PlaybackStartMockTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "play.db")
        self.db.upsert_library_item(
            {
                "rating_key": "movie-1",
                "media_type": "movie",
                "title": "Heat",
                "content_rating": "R",
                "view_offset_ms": 0,
                "duration_ms": 1000,
            }
        )
        reset_playback_sessions()

    def tearDown(self) -> None:
        reset_playback_sessions()
        self._tmpdir.cleanup()

    def test_start_returns_proxy_url_not_pms(self) -> None:
        settings = Settings(plex_url="http://plex.test:32400", plex_token="server-token")
        user = type("U", (), {"id": "owner", "is_youth": False})()

        def fake_fetch(url, **_kwargs):
            self.assertIn("start.m3u8", url)
            self.assertIn("subtitles=none", url)
            self.assertNotIn("subtitleStreamID=", url)
            self.assertNotIn("X-Plex-Token=server-token", url)
            return b"#EXTM3U\n", "application/vnd.apple.mpegurl", 200, url

        payload = start_playback(
            self.db,
            settings,
            rating_key="movie-1",
            user=user,
            fetch=fake_fetch,
        )
        self.assertTrue(payload["stream_url"].startswith("/api/library/playback/"))
        self.assertNotIn("plex.test", json.dumps(payload))
        self.assertNotIn("server-token", json.dumps(payload))
        self.assertEqual(payload["title"], "Heat")
        self.assertEqual(payload["subtitle_stream_id"], "")

    def test_progress_throttles_then_writes_offset(self) -> None:
        settings = Settings(plex_url="http://plex.test:32400", plex_token="server-token")
        user = type("U", (), {"id": "owner", "is_youth": False})()
        calls = []

        def fake_fetch(url, **_kwargs):
            calls.append(url)
            return b"", "text/plain", 200, url

        payload = start_playback(
            self.db,
            settings,
            rating_key="movie-1",
            user=user,
            fetch=fake_fetch,
        )
        from projectionist.library.playback import get_session

        session = get_session(payload["session_id"], user_id="owner")
        first = report_progress(
            self.db,
            session,
            state="playing",
            time_ms=5000,
            duration_ms=1000,
            now=100.0,
            fetch=fake_fetch,
        )
        second = report_progress(
            self.db,
            session,
            state="playing",
            time_ms=8000,
            duration_ms=1000,
            now=105.0,
            fetch=fake_fetch,
        )
        self.assertFalse(first["throttled"])
        self.assertTrue(second["throttled"])
        row = self.db.library_item_by_rating_key("movie-1")
        self.assertEqual(int(row["view_offset_ms"] or 0), 5000)

    def test_seek_restarts_hls_at_offset_without_changing_playlist_url(self) -> None:
        settings = Settings(plex_url="http://plex.test:32400", plex_token="server-token")
        user = type("U", (), {"id": "owner", "is_youth": False})()
        calls = []

        def fake_fetch(url, **_kwargs):
            calls.append(url)
            return b"#EXTM3U\n", "application/vnd.apple.mpegurl", 200, url

        started = start_playback(
            self.db,
            settings,
            rating_key="movie-1",
            user=user,
            fetch=fake_fetch,
        )
        from projectionist.library.playback import get_session

        session = get_session(started["session_id"], user_id="owner")
        calls.clear()
        payload = seek_playback(session, 15_000, fetch=fake_fetch, db=self.db)
        self.assertEqual(payload["stream_url"], started["stream_url"])
        self.assertEqual(payload["view_offset_ms"], 15_000)
        self.assertTrue(any("/transcode/universal/stop" in url for url in calls))
        self.assertTrue(any("start.m3u8" in url and "offset=15&" in url for url in calls))
        self.assertTrue(any("subtitles=none" in url for url in calls if "start.m3u8" in url))
        self.assertFalse(any("subtitleStreamID=" in url for url in calls if "start.m3u8" in url))

    def test_failed_seek_restores_the_previous_playable_offset(self) -> None:
        settings = Settings(plex_url="http://plex.test:32400", plex_token="server-token")
        user = type("U", (), {"id": "owner", "is_youth": False})()

        def ok_fetch(url, **_kwargs):
            return b"#EXTM3U\n", "application/vnd.apple.mpegurl", 200, url

        started = start_playback(
            self.db,
            settings,
            rating_key="movie-1",
            user=user,
            fetch=ok_fetch,
        )
        from projectionist.library.playback import get_session

        session = get_session(started["session_id"], user_id="owner")
        calls = []

        def failing_fetch(url, **_kwargs):
            calls.append(url)
            if "start.m3u8" in url and "offset=30&" in url:
                raise PlaybackError("transcode failed")
            return b"#EXTM3U\n", "application/vnd.apple.mpegurl", 200, url

        with self.assertRaises(PlaybackError):
            seek_playback(session, 30_000, fetch=failing_fetch, db=self.db)
        self.assertEqual(session.view_offset_ms, 0)
        self.assertTrue(any("start.m3u8" in url and "offset=0&" in url for url in calls))
        row = self.db.library_item_by_rating_key("movie-1")
        self.assertEqual(int(row["view_offset_ms"] or 0), 0)

    def test_burn_in_restart_then_off_restores_subtitles_none(self) -> None:
        settings = Settings(plex_url="http://plex.test:32400", plex_token="server-token")
        user = type("U", (), {"id": "owner", "is_youth": False})()
        calls: list[str] = []

        def fake_fetch(url, **_kwargs):
            calls.append(url)
            return b"#EXTM3U\n", "application/vnd.apple.mpegurl", 200, url

        started = start_playback(
            self.db,
            settings,
            rating_key="movie-1",
            user=user,
            fetch=fake_fetch,
        )
        from projectionist.library.playback import get_session

        session = get_session(started["session_id"], user_id="owner")
        self.assertTrue(any("subtitles=none" in url for url in calls if "start.m3u8" in url))
        calls.clear()
        burned = seek_playback(
            session,
            12_000,
            fetch=fake_fetch,
            db=self.db,
            subtitle_stream_id="9003",
        )
        self.assertEqual(burned["subtitle_stream_id"], "9003")
        self.assertEqual(burned["view_offset_ms"], 12_000)
        start_urls = [url for url in calls if "start.m3u8" in url]
        self.assertTrue(start_urls)
        self.assertIn("subtitles=burn", start_urls[-1])
        self.assertIn("subtitleStreamID=9003", start_urls[-1])
        self.assertIn("advancedSubtitles=burn", start_urls[-1])
        self.assertIn("offset=12&", start_urls[-1])
        calls.clear()
        seek_playback(session, 20_000, fetch=fake_fetch, db=self.db)
        kept = [url for url in calls if "start.m3u8" in url]
        self.assertTrue(kept)
        self.assertIn("subtitleStreamID=9003", kept[-1])
        calls.clear()
        off = seek_playback(
            session,
            20_000,
            fetch=fake_fetch,
            db=self.db,
            subtitle_stream_id=None,
        )
        self.assertEqual(off["subtitle_stream_id"], "")
        cleared = [url for url in calls if "start.m3u8" in url]
        self.assertTrue(cleared)
        self.assertIn("subtitles=none", cleared[-1])
        self.assertNotIn("subtitleStreamID=", cleared[-1])


class PlaybackApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        os.environ["DATA_DIR"] = str(self.data_dir)
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-playback-session-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        reset_playback_sessions()
        (self.data_dir / "settings.json").write_text(
            json.dumps(
                {
                    "plex_url": "http://plex.test:32400",
                    "plex_token": "server-token",
                    "features": {"multi_user_enabled": False},
                    "llm_provider": "ollama",
                    "youth": {"max_content_rating": "PG-13"},
                }
            ),
            encoding="utf-8",
        )
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db
        self.db.upsert_library_item(
            {
                "rating_key": "rk-heat",
                "media_type": "movie",
                "title": "Heat",
                "content_rating": "R",
                "view_offset_ms": 0,
                "duration_ms": 1000,
            }
        )
        self.db.upsert_library_item(
            {
                "rating_key": "rk-pg",
                "media_type": "movie",
                "title": "Paddington",
                "content_rating": "PG",
                "view_offset_ms": 0,
                "duration_ms": 1000,
            }
        )

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        reset_playback_sessions()
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("PROJECTIONIST_SESSION_SECRET", None)
        os.environ.pop("PROJECTIONIST_SETUP_STATE", None)
        self._tmpdir.cleanup()

    def test_start_and_playlist_hide_plex(self) -> None:
        playlist = (
            "#EXTM3U\n"
            "http://plex.test:32400/video/:/transcode/universal/session/abc/seg.ts?X-Plex-Token=server-token\n"
        )

        def fake_fetch(url, **_kwargs):
            return playlist.encode("utf-8"), "application/vnd.apple.mpegurl", 200, url

        with patch(
            "projectionist.connectors.plex.cached_machine_identifier",
            return_value="machine-1",
        ), patch("projectionist.library.playback.fetch_plex_bytes", side_effect=fake_fetch):
            resp = self.client.post("/api/library/playback/start", json={"rating_key": "rk-heat"})
            self.assertEqual(resp.status_code, 200, resp.text)
            body = resp.json()
            self.assertNotIn("server-token", resp.text)
            self.assertNotIn("plex.test", resp.text)
            stream = self.client.get(body["stream_url"])
        self.assertEqual(stream.status_code, 200)
        text = stream.text
        self.assertNotIn("server-token", text)
        self.assertNotIn("plex.test", text)
        self.assertIn("/api/library/playback/", text)

    def test_subtitles_endpoint_burns_then_clears(self) -> None:
        seen: list[str] = []

        def fake_fetch(url, **_kwargs):
            seen.append(url)
            return b"#EXTM3U\n", "application/vnd.apple.mpegurl", 200, url

        with patch(
            "projectionist.connectors.plex.cached_machine_identifier",
            return_value="machine-1",
        ), patch("projectionist.library.playback.fetch_plex_bytes", side_effect=fake_fetch):
            started = self.client.post("/api/library/playback/start", json={"rating_key": "rk-heat"})
            self.assertEqual(started.status_code, 200, started.text)
            session_id = started.json()["session_id"]
            seen.clear()
            burned = self.client.post(
                f"/api/library/playback/{session_id}/subtitles",
                json={"subtitle_stream_id": "9003", "offset_ms": 8000},
            )
            self.assertEqual(burned.status_code, 200, burned.text)
            self.assertEqual(burned.json()["subtitle_stream_id"], "9003")
            self.assertTrue(any("subtitles=burn" in url and "subtitleStreamID=9003" in url for url in seen))
            seen.clear()
            off = self.client.post(
                f"/api/library/playback/{session_id}/subtitles",
                json={"subtitle_stream_id": None, "offset_ms": 8000},
            )
            self.assertEqual(off.status_code, 200, off.text)
            self.assertEqual(off.json()["subtitle_stream_id"], "")
            self.assertTrue(any("subtitles=none" in url for url in seen if "start.m3u8" in url))
            self.assertFalse(any("subtitleStreamID=" in url for url in seen if "start.m3u8" in url))
            bad = self.client.post(
                f"/api/library/playback/{session_id}/subtitles",
                json={"subtitle_stream_id": "nope", "offset_ms": 0},
            )
            self.assertEqual(bad.status_code, 400)

    def test_watch_spa_shell(self) -> None:
        watch = self.client.get("/watch/plex-949")
        self.assertEqual(watch.status_code, 200, watch.text)
        self.assertIn("text/html", watch.headers.get("content-type", ""))
        self.assertNotIn("Not Found", watch.text)
        popout = self.client.get("/watch/plex-949/popout")
        self.assertEqual(popout.status_code, 200, popout.text)
        self.assertIn("text/html", popout.headers.get("content-type", ""))

    def test_hostile_start_key(self) -> None:
        resp = self.client.post("/api/library/playback/start", json={"rating_key": "../etc"})
        self.assertEqual(resp.status_code, 400)

    def test_youth_gate_403(self) -> None:
        # Single-owner mode is not youth. Force a youth user via patch.
        youth = type("U", (), {"id": "youth-1", "is_youth": True, "role": "member"})()
        with patch("projectionist.web.playback_routes.get_current_user_dep", return_value=youth):
            # FastAPI Depends is already bound; call the helper directly.
            from projectionist.library.playback import start_playback

            with self.assertRaises(YouthBlockedError):
                start_playback(
                    self.db,
                    Settings(
                        plex_url="http://plex.test:32400",
                        plex_token="server-token",
                        youth=YouthSettings(max_content_rating="PG-13"),
                    ),
                    rating_key="rk-heat",
                    user=youth,
                    fetch=lambda *a, **k: (b"", "", 200, ""),
                )


if __name__ == "__main__":
    unittest.main()
