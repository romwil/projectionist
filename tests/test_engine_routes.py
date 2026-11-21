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
            write_master(
                directory,
                kwargs.get("probe"),
                file_size=100,
                duration_ms=int(kwargs.get("duration_ms") or 600_000),
                captions=kwargs.get("captions"),
            )
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
                json={"rating_key": "121986", "profile": "apple-tv-4k-3", "engine_opt_in": True},
            )
        self.assertEqual(opened.status_code, 200, opened.text)
        body = opened.json()
        self.assertEqual(body["plan"], "remux")
        self.assertTrue(body["playable"])
        self.assertNotIn(str(self.media), opened.text)
        master = self.client.get(body["master_url"])
        self.assertEqual(master.status_code, 200, master.text)
        self.assertIn("BANDWIDTH=", master.text)
        self.assertNotIn("SUBTITLES", master.text)
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
                json={"rating_key": "121986", "profile": "chrome", "engine_opt_in": True},
            )
        self.assertEqual(chrome.status_code, 200, chrome.text)
        fallback = chrome.json()
        self.assertEqual(fallback["plan"], "audio")
        self.assertFalse(fallback["playable"])
        self.assertIn("AC-3", fallback["reason"])
        recorded = self.client.get(f"/api/playback/sessions/{fallback['session_id']}")
        self.assertEqual(recorded.status_code, 200)
        self.assertEqual(recorded.json()["reason"], fallback["reason"])

    def _map_movie(self) -> None:
        saved = self.client.put(
            "/api/playback/path-mappings",
            json={"mappings": [{"plex_prefix": "/data/media/movies", "container_prefix": str(self.data_dir)}]},
        )
        self.assertEqual(saved.status_code, 200, saved.text)

    def _open_with_probe(self, probe: ProbeResult):
        def fake_start(source, directory, **kwargs):
            from projectionist.engine.remux import write_master

            directory = Path(directory)
            write_master(
                directory,
                kwargs.get("probe"),
                file_size=100,
                duration_ms=int(kwargs.get("duration_ms") or 600_000),
                captions=kwargs.get("captions"),
            )
            av = directory / "av"
            av.mkdir(parents=True, exist_ok=True)
            (av / "stream.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")
            return None

        with patch(
            "projectionist.engine.routes.plex_part_paths",
            return_value=["/data/media/movies/film.mkv"],
        ), patch("projectionist.engine.source.probe_file", return_value=probe), patch(
            "projectionist.engine.session.start_remux",
            side_effect=fake_start,
        ):
            return self.client.post(
                "/api/playback/sessions",
                json={"rating_key": "121986", "profile": "apple-tv-4k-3", "engine_opt_in": True},
            )

    def test_household_webvtt_plays_through_the_engine(self) -> None:
        from projectionist.engine.captions import CAPTION_FALLBACK_REASON

        self._map_movie()
        self.db.upsert_library_item(
            {
                "rating_key": "121986",
                "media_type": "movie",
                "title": "A Foreign Film",
                "original_language": "ja",
                "duration_ms": 600_000,
            }
        )
        cache = self.data_dir / "subtitles" / "121986"
        cache.mkdir(parents=True)
        (cache / "en.srt").write_text(
            "1\n00:00:01,500 --> 00:00:03,000\nHello from the house\n",
            encoding="utf-8",
        )
        probe = _probe()
        probe.streams.append(
            MediaStream(
                index=4,
                codec_type="subtitle",
                codec="hdmv_pgs_subtitle",
                language="eng",
                subtitle_kind="image",
            )
        )
        opened = self._open_with_probe(probe)
        self.assertEqual(opened.status_code, 200, opened.text)
        body = opened.json()
        self.assertEqual(body["plan"], "remux")
        self.assertTrue(body["playable"])
        self.assertNotIn(CAPTION_FALLBACK_REASON, body["reason"])
        self.assertNotIn(str(self.media), opened.text)
        master = self.client.get(body["master_url"])
        self.assertEqual(master.status_code, 200, master.text)
        self.assertIn('SUBTITLES="subs"', master.text)
        self.assertIn('LANGUAGE="en"', master.text)
        self.assertIn("DEFAULT=YES", master.text)
        self.assertNotIn(str(self.media), master.text)
        base = body["master_url"].rsplit("/", 1)[0]
        playlist = self.client.get(f"{base}/subs/cached-en.m3u8")
        self.assertEqual(playlist.status_code, 200, playlist.text)
        self.assertIn("#EXT-X-PLAYLIST-TYPE:VOD", playlist.text)
        self.assertIn("cached-en.vtt", playlist.text)
        vtt = self.client.get(f"{base}/subs/cached-en.vtt")
        self.assertEqual(vtt.status_code, 200, vtt.text)
        self.assertIn("text/vtt", vtt.headers["content-type"])
        self.assertTrue(vtt.text.startswith("WEBVTT"))
        self.assertIn("Hello from the house", vtt.text)
        self.assertIn("00:00:01.500 --> 00:00:03.000", vtt.text)
        self.assertNotIn(str(self.media), vtt.text)

    def test_picture_captions_record_a_plex_fallback(self) -> None:
        from projectionist.engine.captions import CAPTION_FALLBACK_REASON

        self._map_movie()
        self.db.upsert_library_item(
            {
                "rating_key": "121986",
                "media_type": "movie",
                "title": "Pictures",
                "original_language": "ja",
                "duration_ms": 600_000,
            }
        )
        probe = _probe()
        probe.streams.append(
            MediaStream(
                index=4,
                codec_type="subtitle",
                codec="hdmv_pgs_subtitle",
                language="eng",
                subtitle_kind="image",
            )
        )
        opened = self._open_with_probe(probe)
        self.assertEqual(opened.status_code, 200, opened.text)
        body = opened.json()
        self.assertEqual(body["plan"], "plex-fallback")
        self.assertFalse(body["playable"])
        self.assertEqual(body["reason"], CAPTION_FALLBACK_REASON)
        self.assertEqual(body["master_url"], "")
        recorded = self.client.get(f"/api/playback/sessions/{body['session_id']}")
        self.assertEqual(recorded.status_code, 200, recorded.text)
        self.assertEqual(recorded.json()["reason"], CAPTION_FALLBACK_REASON)

    def test_missing_opt_in_stays_on_the_library_path(self) -> None:
        from projectionist.engine.session import OPT_IN_REASON

        self._map_movie()
        with patch("projectionist.engine.session.start_remux") as remux:
            opened = self.client.post(
                "/api/playback/sessions",
                json={"rating_key": "121986", "profile": "apple-tv-4k-3"},
            )
        self.assertEqual(opened.status_code, 200, opened.text)
        body = opened.json()
        self.assertEqual(body["plan"], "library")
        self.assertFalse(body["playable"])
        self.assertEqual(body["master_url"], "")
        self.assertEqual(body["session_id"], "")
        self.assertEqual(body["reason"], OPT_IN_REASON)
        self.assertNotIn(str(self.media), opened.text)
        remux.assert_not_called()

    def test_device_credential_plays_a_header_free_playlist(self) -> None:
        """A paired device has no session cookie. The playlist token is the credential."""
        from projectionist.devices.native_login import issue_device_credential
        from projectionist.engine.session import OPT_IN_REASON

        self._map_movie()
        self.db.upsert_plex_user(
            user_id="owner-device",
            display_name="Owner",
            email=None,
            plex_user_id="plex-device",
            role="owner",
        )
        issued = issue_device_credential(
            self.db, user_id="owner-device", kind="iphone", label="Phone"
        )
        credential = issued["credential"]
        settings_path = self.data_dir / "settings.json"
        current = json.loads(settings_path.read_text(encoding="utf-8"))
        features = dict(current.get("features") or {})
        features["multi_user_enabled"] = True
        current["features"] = features
        settings_path.write_text(json.dumps(current), encoding="utf-8")
        self.client.cookies.clear()
        bearer = {"Authorization": f"Bearer {credential}"}

        with patch("projectionist.engine.session.start_remux") as remux:
            declined = self.client.post(
                "/api/playback/sessions",
                json={"rating_key": "121986", "profile": "apple-tv-4k-3"},
                headers=bearer,
            )
        self.assertEqual(declined.status_code, 200, declined.text)
        self.assertEqual(declined.json()["plan"], "library")
        self.assertFalse(declined.json()["playable"])
        self.assertEqual(declined.json()["reason"], OPT_IN_REASON)
        remux.assert_not_called()
        self.assertEqual(
            self.client.post(
                "/api/playback/sessions",
                json={"rating_key": "121986", "engine_opt_in": True},
            ).status_code,
            401,
        )

        def fake_start(source, directory, **kwargs):
            from projectionist.engine.remux import write_master

            directory = Path(directory)
            write_master(
                directory,
                kwargs.get("probe"),
                file_size=100,
                duration_ms=int(kwargs.get("duration_ms") or 600_000),
                captions=kwargs.get("captions"),
            )
            av = directory / "av"
            av.mkdir(parents=True, exist_ok=True)
            (av / "stream.m3u8").write_text("#EXTM3U\n#EXT-X-ENDLIST\n", encoding="utf-8")
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
                json={
                    "rating_key": "121986",
                    "profile": "apple-tv-4k-3",
                    "engine_opt_in": True,
                },
                headers=bearer,
            )
        self.assertEqual(opened.status_code, 200, opened.text)
        body = opened.json()
        self.assertTrue(body["playable"], body)
        self.assertTrue(body["master_url"])
        self.client.cookies.clear()
        playlist = self.client.get(body["master_url"])
        self.assertEqual(playlist.status_code, 200, playlist.text)
        self.assertIn("#EXTM3U", playlist.text)
        with_bearer = self.client.get(body["master_url"], headers=bearer)
        self.assertEqual(with_bearer.status_code, 200, with_bearer.text)
        wrong = body["master_url"].replace(body["master_url"].split("/")[5], "not-the-token")
        rejected = self.client.get(wrong)
        self.assertEqual(rejected.status_code, 404, rejected.text)
        self.assertNotEqual(rejected.status_code, 401)
        self.assertEqual(
            self.client.get(f"/api/playback/sessions/{body['session_id']}").status_code,
            401,
        )
        self.assertEqual(
            self.client.post(
                f"/api/playback/sessions/{body['session_id']}/progress",
                json={"time_ms": 1, "duration_ms": 600000},
            ).status_code,
            401,
        )

    def test_prepared_text_plays_without_extracting_during_the_session(self) -> None:
        from projectionist.engine.caption_prep import extract_text_captions
        from projectionist.engine.source import MediaAsset

        self._map_movie()
        self.db.upsert_library_item(
            {
                "rating_key": "121986",
                "media_type": "movie",
                "title": "Adventures of Zatoichi",
                "original_language": "ja",
                "duration_ms": 600_000,
            }
        )
        probe = _probe()
        probe.streams.append(
            MediaStream(index=2, codec_type="subtitle", codec="subrip", language="eng", subtitle_kind="text")
        )
        asset = MediaAsset(
            rating_key="121986",
            readable=True,
            local_path=str(self.media),
            probe=probe,
        )

        def extract(source: Path, index: int, dest: Path) -> None:
            dest.write_text(
                "WEBVTT\n\n00:00:04.000 --> 00:00:05.000\nAlready WebVTT\n",
                encoding="utf-8",
            )

        self.assertEqual(extract_text_captions(asset, data_dir=self.data_dir, extractor=extract), "ready")
        with patch(
            "projectionist.engine.caption_prep.subprocess.run",
            side_effect=AssertionError("play must not extract captions"),
        ):
            opened = self._open_with_probe(probe)
        self.assertEqual(opened.status_code, 200, opened.text)
        body = opened.json()
        self.assertEqual(body["plan"], "remux", body)
        self.assertTrue(body["playable"])
        base = body["master_url"].rsplit("/", 1)[0]
        vtt = self.client.get(f"{base}/subs/s2.vtt")
        self.assertEqual(vtt.status_code, 200, vtt.text)
        self.assertIn("Already WebVTT", vtt.text)

    def test_text_not_ready_records_the_caption_fallback_and_queues_prep(self) -> None:
        from projectionist.engine.captions import CAPTION_PENDING_REASON

        self._map_movie()
        self.db.upsert_library_item(
            {
                "rating_key": "121986",
                "media_type": "movie",
                "title": "Adventures of Zatoichi",
                "original_language": "ja",
                "duration_ms": 600_000,
            }
        )
        probe = _probe()
        probe.streams.append(
            MediaStream(index=2, codec_type="subtitle", codec="subrip", language="eng", subtitle_kind="text")
        )
        calls = {"remux": 0}

        def fake_start(source, directory, **kwargs):
            calls["remux"] += 1
            raise AssertionError("captions that are not ready must not remux")

        with patch(
            "projectionist.engine.routes.plex_part_paths",
            return_value=["/data/media/movies/film.mkv"],
        ), patch("projectionist.engine.source.probe_file", return_value=probe), patch(
            "projectionist.engine.session.start_remux",
            side_effect=fake_start,
        ), patch(
            "projectionist.engine.caption_prep.subprocess.run",
            side_effect=AssertionError("play must not extract captions"),
        ):
            opened = self.client.post(
                "/api/playback/sessions",
                json={"rating_key": "121986", "profile": "apple-tv-4k-3", "engine_opt_in": True},
            )
        self.assertEqual(opened.status_code, 200, opened.text)
        body = opened.json()
        self.assertEqual(body["plan"], "plex-fallback")
        self.assertFalse(body["playable"])
        self.assertEqual(body["reason"], CAPTION_PENDING_REASON)
        self.assertEqual(calls["remux"], 0)
        queued = json.loads((self.data_dir / "caption_prep_queue.json").read_text(encoding="utf-8"))
        self.assertEqual(queued["items"][0]["rating_key"], "121986")
        self.assertEqual(queued["items"][0]["reason"], "play")
