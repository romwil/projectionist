"""ENG-001 routes: owner path mappings and a path-free media description."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.engine.probe import MediaStream, ProbeResult
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache


def _probe() -> ProbeResult:
    return ProbeResult(
        container="mkv",
        format_name="matroska,webm",
        duration_s=600.066,
        bitrate=4_500_000,
        size=337_500_000,
        streams=[
            MediaStream(index=0, codec_type="video", codec="h264", width=1920, height=1080, level="41"),
            MediaStream(index=1, codec_type="audio", codec="ac3", language="eng", channels=2),
        ],
    )


class EngineRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        self.media = self.data_dir / "film.mkv"
        self.media.write_bytes(b"not-a-real-mkv")
        os.environ["DATA_DIR"] = str(self.data_dir)
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-engine-session-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        (self.data_dir / "settings.json").write_text(
            json.dumps(
                {
                    "plex_url": "http://plex.test:32400",
                    "plex_token": "server-token",
                    "features": {"multi_user_enabled": False},
                    "llm_provider": "ollama",
                }
            ),
            encoding="utf-8",
        )
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db
        self.db.upsert_library_item(
            {
                "rating_key": "121986",
                "media_type": "movie",
                "title": "3 Ninjas",
                "tmdb_id": 8856,
                "imdb_id": "tt0103596",
                "duration_ms": 600_000,
            }
        )

    def tearDown(self) -> None:
        from projectionist.engine.session import reset_engine_sessions

        reset_engine_sessions()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("PROJECTIONIST_SESSION_SECRET", None)
        os.environ.pop("PROJECTIONIST_SETUP_STATE", None)
        self._tmpdir.cleanup()

    def test_owner_saves_mappings_and_media_hides_paths(self) -> None:
        saved = self.client.put(
            "/api/playback/path-mappings",
            json={
                "mappings": [
                    {"plex_prefix": "/data/media/movies", "container_prefix": str(self.data_dir)}
                ]
            },
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["mappings"][0]["plex_prefix"], "/data/media/movies")
        listed = self.client.get("/api/playback/path-mappings")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["mappings"]), 1)

        with patch(
            "projectionist.engine.routes.plex_part_paths",
            return_value=["/data/media/movies/film.mkv"],
        ), patch("projectionist.engine.source.probe_file", return_value=_probe()):
            media = self.client.get("/api/playback/media/121986")
        self.assertEqual(media.status_code, 200, media.text)
        body = media.json()
        self.assertNotIn(str(self.media), media.text)
        self.assertNotIn("/data/media", media.text)
        self.assertNotIn("server-token", media.text)
        self.assertTrue(body["readable"])
        self.assertTrue(body["probed"])
        self.assertEqual(body["container"], "mkv")
        self.assertEqual(body["identity"]["tmdb_id"], 8856)
        self.assertEqual(body["identity"]["imdb_id"], "tt0103596")
        self.assertEqual(body["streams"][0]["codec"], "h264")

    def test_bad_mapping_is_rejected(self) -> None:
        resp = self.client.put(
            "/api/playback/path-mappings",
            json={"mappings": [{"plex_prefix": "relative", "container_prefix": "/movies"}]},
        )
        self.assertEqual(resp.status_code, 400)

    def test_hostile_rating_key_is_rejected(self) -> None:
        resp = self.client.get("/api/playback/media/bad%20key")
        self.assertEqual(resp.status_code, 400)

    def test_settings_put_keeps_path_mappings(self) -> None:
        saved = self.client.put(
            "/api/playback/path-mappings",
            json={"mappings": [{"plex_prefix": "/plex/movies", "container_prefix": "/movies"}]},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        partial = self.client.put("/api/settings", json={"movies_root": "/media/movies"})
        self.assertEqual(partial.status_code, 200, partial.text)
        listed = self.client.get("/api/playback/path-mappings")
        self.assertEqual(listed.json()["mappings"][0]["plex_prefix"], "/plex/movies")

    def test_plan_names_a_remux_without_a_file_path(self) -> None:
        saved = self.client.put(
            "/api/playback/path-mappings",
            json={"mappings": [{"plex_prefix": "/data/media/movies", "container_prefix": str(self.data_dir)}]},
        )
        self.assertEqual(saved.status_code, 200, saved.text)
        with patch(
            "projectionist.engine.routes.plex_part_paths",
            return_value=["/data/media/movies/film.mkv"],
        ), patch("projectionist.engine.source.probe_file", return_value=_probe()):
            plan = self.client.get("/api/playback/plan", params={"rating_key": "121986", "profile": "apple-tv-4k-3"})
        self.assertEqual(plan.status_code, 200, plan.text)
        body = plan.json()
        self.assertEqual(body["plan"], "remux")
        self.assertNotIn(str(self.media), plan.text)
        self.assertNotIn("/data/media", plan.text)
        unknown = self.client.get("/api/playback/plan", params={"rating_key": "121986", "profile": "nope"})
        self.assertEqual(unknown.status_code, 400)

    def test_session_token_serves_media_and_records_a_fallback(self) -> None:
        saved = self.client.put(
            "/api/playback/path-mappings",
            json={"mappings": [{"plex_prefix": "/data/media/movies", "container_prefix": str(self.data_dir)}]},
        )
        self.assertEqual(saved.status_code, 200, saved.text)

        def fake_start(source, directory, **kwargs):
            from projectionist.engine.remux import write_master

            directory = Path(directory)
            write_master(directory, kwargs.get("probe"), file_size=100, duration_ms=600_000)
            av = directory / "av"
            av.mkdir(parents=True, exist_ok=True)
            (av / "stream.m3u8").write_text(
                "#EXTM3U\n#EXT-X-PLAYLIST-TYPE:VOD\n#EXT-X-ENDLIST\n",
                encoding="utf-8",
            )
            return None

        with patch(
            "projectionist.engine.routes.plex_part_paths",
            return_value=["/data/media/movies/film.mkv"],
        ), patch("projectionist.engine.source.probe_file", return_value=_probe()), patch(
            "projectionist.engine.session.start_remux",
            side_effect=fake_start,
        ):
            opened = self.client.post(
                "/api/playback/sessions",
                json={"rating_key": "121986", "profile": "apple-tv-4k-3"},
            )
        self.assertEqual(opened.status_code, 200, opened.text)
        body = opened.json()
        self.assertEqual(body["plan"], "remux")
        self.assertTrue(body["playable"])
        self.assertNotIn(str(self.media), opened.text)
        master = self.client.get(body["master_url"])
        self.assertEqual(master.status_code, 200, master.text)
        self.assertIn("BANDWIDTH=", master.text)
        self.assertIn("#EXT-X-ENDLIST", self.client.get(body["master_url"].rsplit("/", 1)[0] + "/av/stream.m3u8").text)
        broken = body["master_url"].replace(body["master_url"].split("/")[5], "not-the-token")
        self.assertEqual(self.client.get(broken).status_code, 404)
        progress = self.client.post(
            f"/api/playback/sessions/{body['session_id']}/progress",
            json={"time_ms": 15000, "duration_ms": 600000},
        )
        self.assertEqual(progress.status_code, 200, progress.text)
        self.assertEqual(int(self.db.library_item_by_rating_key("121986")["view_offset_ms"]), 15000)

        with patch(
            "projectionist.engine.routes.plex_part_paths",
            return_value=["/data/media/movies/film.mkv"],
        ), patch("projectionist.engine.source.probe_file", return_value=_probe()):
            chrome = self.client.post(
                "/api/playback/sessions",
                json={"rating_key": "121986", "profile": "chrome"},
            )
        self.assertEqual(chrome.status_code, 200, chrome.text)
        fallback = chrome.json()
        self.assertEqual(fallback["plan"], "audio")
        self.assertFalse(fallback["playable"])
        self.assertIn("AC-3", fallback["reason"])
        recorded = self.client.get(f"/api/playback/sessions/{fallback['session_id']}")
        self.assertEqual(recorded.status_code, 200)
        self.assertEqual(recorded.json()["reason"], fallback["reason"])
