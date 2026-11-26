"""The web remote reads an engine session the preroll handoff already accepts."""

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
from projectionist.engine.session import get_engine_session, reset_engine_sessions
from projectionist.library.db import BOOTSTRAP_OWNER_ID
from projectionist.sessions.shared import reset_shared_sessions
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import (
    SESSION_COOKIE_NAME,
    clear_session_secret_cache,
    create_session_token,
)


def _probe() -> ProbeResult:
    return ProbeResult(
        container="mkv",
        format_name="matroska,webm",
        duration_s=600.066,
        bitrate=4_500_000,
        size=337_500_000,
        streams=[
            MediaStream(
                index=0, codec_type="video", codec="h264", width=1920, height=1080, level="41"
            ),
            MediaStream(index=1, codec_type="audio", codec="ac3", language="eng", channels=2),
        ],
    )


class RemoteEngineSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)
        (self.data_dir / "film.mkv").write_bytes(b"not-a-real-mkv")
        os.environ["DATA_DIR"] = str(self.data_dir)
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-remote-engine-session-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        clear_session_secret_cache()
        clear_rate_limits()
        reset_engine_sessions()
        reset_shared_sessions()
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
        turned = self.client.patch("/api/auth/me", json={"play_through_just_for_me": True})
        self.assertEqual(turned.status_code, 200, turned.text)
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
        saved = self.client.put(
            "/api/playback/path-mappings",
            json={
                "mappings": [
                    {"plex_prefix": "/data/media/movies", "container_prefix": str(self.data_dir)}
                ]
            },
        )
        self.assertEqual(saved.status_code, 200, saved.text)

    def tearDown(self) -> None:
        reset_engine_sessions()
        reset_shared_sessions()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in (
            "DATA_DIR",
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "PROJECTIONIST_SETUP_STATE",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _open(self):
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

        with (
            patch(
                "projectionist.engine.routes.plex_part_paths",
                return_value=["/data/media/movies/film.mkv"],
            ),
            patch("projectionist.engine.source.probe_file", return_value=_probe()),
            patch(
                "projectionist.engine.session.start_remux",
                side_effect=fake_start,
            ),
        ):
            return self.client.post(
                "/api/playback/sessions",
                json={"rating_key": "121986", "profile": "apple-tv-4k-3", "engine_opt_in": True},
            )

    def test_remote_reads_the_engine_session_handoff_accepts(self) -> None:
        opened = self._open()
        self.assertEqual(opened.status_code, 200, opened.text)
        session_id = opened.json()["session_id"]
        handed = self.client.get(
            f"/api/playback/sessions/{session_id}",
            params={"handoff": "true"},
        )
        self.assertEqual(handed.status_code, 200, handed.text)
        self.assertTrue(handed.json()["ready_at_handoff"])

        remote = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(remote.status_code, 200, remote.text)
        body = remote.json()
        self.assertNotIn("detail", body)
        self.assertEqual(body["id"], session_id)
        self.assertEqual(body["state"], "playing")
        self.assertEqual(body["engine_session_id"], session_id)

        self.client.cookies.set(SESSION_COOKIE_NAME, create_session_token(BOOTSTRAP_OWNER_ID))
        with self.client.websocket_connect(f"/api/sessions/{session_id}/live") as socket:
            hello = socket.receive_json()
        self.assertEqual(hello["type"], "state")
        self.assertEqual(hello["state"], "playing")
        self.assertNotEqual(hello.get("detail"), "That session is not available.")

        paused = self.client.post(
            f"/api/sessions/{session_id}/commands",
            json={"command": "pause"},
        )
        self.assertEqual(paused.status_code, 200, paused.text)
        self.assertEqual(paused.json()["state"], "paused")

    def test_remote_hides_an_engine_session_handoff_would_refuse(self) -> None:
        opened = self._open()
        self.assertEqual(opened.status_code, 200, opened.text)
        session_id = opened.json()["session_id"]
        get_engine_session(session_id).user_id = "someone-else"
        remote = self.client.get(f"/api/sessions/{session_id}")
        self.assertEqual(remote.status_code, 404, remote.text)
        self.assertEqual(remote.json()["detail"], "That session is not available.")
        handed = self.client.get(
            f"/api/playback/sessions/{session_id}",
            params={"handoff": "true"},
        )
        self.assertEqual(handed.status_code, 404, handed.text)
