"""Tests for scheduled purge-candidate caching and API cache reads."""

from __future__ import annotations

import importlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from curatorx.config_store import Settings
from curatorx.library.db import Database
from curatorx.scheduler.tasks.purge_candidates import (
    CACHE_KEY,
    drop_cached_purge_keys,
    read_cached_purge_candidates,
    recompute_purge_candidates,
    write_purge_candidates_cache,
)


class PurgeCandidatesCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "purge-cache.db")
        self.db.ensure_seed_data()
        self.settings = Settings()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_read_returns_none_when_empty(self) -> None:
        self.assertIsNone(read_cached_purge_candidates(self.db))

    def test_write_and_read_roundtrip(self) -> None:
        items = [
            {
                "title": "Big Unwatched",
                "rating_key": "rk-1",
                "purge_score": 4.2,
            }
        ]
        payload = write_purge_candidates_cache(self.db, items, generated_at=123.0)
        self.assertEqual(payload["count"], 1)
        self.assertFalse(payload["stale"])
        self.assertTrue(payload["cached"])

        cached = read_cached_purge_candidates(self.db)
        assert cached is not None
        self.assertEqual(cached["count"], 1)
        self.assertEqual(cached["items"][0]["rating_key"], "rk-1")
        self.assertEqual(cached["generated_at"], 123.0)

    def test_drop_cached_purge_keys_filters_items(self) -> None:
        write_purge_candidates_cache(
            self.db,
            [
                {"title": "Keep", "rating_key": "keep"},
                {"title": "Drop", "rating_key": "drop"},
            ],
            generated_at=50.0,
        )
        updated = drop_cached_purge_keys(self.db, ["drop"])
        assert updated is not None
        self.assertEqual(updated["count"], 1)
        self.assertEqual(updated["items"][0]["rating_key"], "keep")
        self.assertEqual(updated["generated_at"], 50.0)

    @patch("curatorx.scheduler.tasks.purge_candidates.suggest_purge_candidates_rich")
    def test_recompute_writes_cache(self, mock_rich) -> None:
        mock_rich.return_value = [{"title": "Computed", "rating_key": "rk-9"}]
        payload = recompute_purge_candidates(self.db, self.settings, limit=5)
        self.assertEqual(payload["count"], 1)
        raw = self.db.get_config(CACHE_KEY)
        assert raw is not None
        data = json.loads(raw)
        self.assertEqual(data["items"][0]["title"], "Computed")
        mock_rich.assert_called_once()


class PurgeCandidatesApiCacheTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_get_returns_stale_empty_when_uncached(self) -> None:
        resp = self.client.get("/api/library/purge-candidates")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["items"], [])
        self.assertTrue(body["stale"])
        self.assertFalse(body["cached"])

    def test_get_returns_cached_payload(self) -> None:
        write_purge_candidates_cache(
            self.db,
            [{"title": "Cached Title", "rating_key": "cached-1", "purge_score": 3.1}],
            generated_at=999.0,
        )
        resp = self.client.get("/api/library/purge-candidates")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["title"], "Cached Title")
        self.assertFalse(body["stale"])
        self.assertTrue(body["cached"])

    @patch("curatorx.web.app.recompute_purge_candidates")
    def test_refresh_endpoint_recomputes(self, mock_recompute) -> None:
        mock_recompute.return_value = {
            "items": [{"title": "Fresh", "rating_key": "fresh-1"}],
            "count": 1,
            "generated_at": 111.0,
            "stale": False,
            "cached": True,
        }
        resp = self.client.post("/api/library/purge-candidates/refresh?limit=10")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["items"][0]["title"], "Fresh")
        mock_recompute.assert_called_once()


if __name__ == "__main__":
    unittest.main()
