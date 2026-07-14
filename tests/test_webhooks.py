"""Tests for Plex webhook ingest."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.config_store import Settings, save_settings
from curatorx.library.db import Database
from curatorx.reviews.store import list_pending_prompts
from curatorx.web.webhooks import (
    completion_from_plex_metadata,
    handle_plex_webhook,
    media_type_from_plex_metadata,
    title_from_plex_metadata,
)


def _movie_stop_payload(*, view_offset: int = 5_400_000, duration: int = 6_000_000) -> dict:
    return {
        "event": "media.stop",
        "user": True,
        "owner": True,
        "Metadata": {
            "librarySectionType": "movie",
            "ratingKey": "movie-plex-1",
            "type": "movie",
            "title": "Inception",
            "viewOffset": view_offset,
            "duration": duration,
        },
    }


def _episode_scrobble_payload() -> dict:
    return {
        "event": "media.scrobble",
        "Metadata": {
            "librarySectionType": "show",
            "ratingKey": "episode-plex-9",
            "type": "episode",
            "grandparentTitle": "Severance",
            "parentIndex": 1,
            "index": 3,
            "title": "In Perpetuity",
        },
    }


class PlexWebhookParserTests(unittest.TestCase):
    def test_completion_from_metadata(self) -> None:
        pct = completion_from_plex_metadata({"viewOffset": 5_400_000, "duration": 6_000_000})
        self.assertAlmostEqual(pct or 0, 90.0)

    def test_title_and_media_type_for_episode(self) -> None:
        metadata = _episode_scrobble_payload()["Metadata"]
        self.assertEqual(title_from_plex_metadata(metadata), "Severance — S01E03")
        self.assertEqual(media_type_from_plex_metadata(metadata), "show")


class PlexWebhookHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "webhooks.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_stop_event_queues_near_complete_movie(self) -> None:
        result = handle_plex_webhook(self.db, _movie_stop_payload())
        self.assertTrue(result["handled"])
        self.assertTrue(result["queued"])
        prompts = list_pending_prompts(self.db)
        self.assertEqual(len(prompts), 1)
        self.assertEqual(prompts[0]["title"], "Inception")
        self.assertGreaterEqual(prompts[0]["completion_pct"], 85.0)

    def test_stop_event_ignores_low_completion(self) -> None:
        result = handle_plex_webhook(self.db, _movie_stop_payload(view_offset=1_000_000, duration=6_000_000))
        self.assertFalse(result["handled"])
        self.assertEqual(result["reason"], "below_threshold")
        self.assertEqual(list_pending_prompts(self.db), [])

    def test_scrobble_event_queues_without_view_offset(self) -> None:
        result = handle_plex_webhook(self.db, _episode_scrobble_payload())
        self.assertTrue(result["handled"])
        self.assertTrue(result["queued"])
        prompts = list_pending_prompts(self.db)
        self.assertEqual(prompts[0]["title"], "Severance — S01E03")


class PlexWebhookApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        self._secret = "test-webhook-secret"
        save_settings(Path(self._tmpdir.name), Settings(webhook_secret=self._secret))
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        self._headers = {"X-CuratorX-Webhook-Secret": self._secret}

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_post_multipart_payload_queues_prompt(self) -> None:
        payload = json.dumps(_movie_stop_payload())
        response = self.client.post(
            "/api/webhooks/plex",
            files={"payload": (None, payload, "application/json")},
            headers=self._headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["handled"])
        self.assertTrue(body["queued"])

    def test_post_json_payload_queues_prompt(self) -> None:
        response = self.client.post(
            "/api/webhooks/plex",
            json=_movie_stop_payload(),
            headers=self._headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["queued"])

    def test_webhook_rejects_empty_secret_config(self) -> None:
        save_settings(Path(os.environ["DATA_DIR"]), Settings(webhook_secret=""))
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        client = TestClient(app_mod.app)
        response = client.post("/api/webhooks/plex", json=_movie_stop_payload())
        self.assertEqual(response.status_code, 503)

    def test_webhook_rejects_missing_secret_when_configured(self) -> None:
        save_settings(
            Path(os.environ["DATA_DIR"]),
            Settings(webhook_secret="super-secret"),
        )
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        client = TestClient(app_mod.app)
        response = client.post("/api/webhooks/plex", json=_movie_stop_payload())
        self.assertEqual(response.status_code, 401)

    def test_webhook_accepts_matching_secret_header(self) -> None:
        save_settings(
            Path(os.environ["DATA_DIR"]),
            Settings(webhook_secret="super-secret"),
        )
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        client = TestClient(app_mod.app)
        response = client.post(
            "/api/webhooks/plex",
            json=_movie_stop_payload(),
            headers={"X-CuratorX-Webhook-Secret": "super-secret"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["queued"])


if __name__ == "__main__":
    unittest.main()
