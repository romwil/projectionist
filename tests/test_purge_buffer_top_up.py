"""Tests for purge candidate buffer top-up and visible-row enrichment."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from projectionist.config_store import Settings
from projectionist.library.db import Database
from projectionist.preferences.purge import enrich_purge_candidate_rows
from projectionist.scheduler.tasks.purge_candidates import (
    BUFFER_TARGET,
    REFILL_THRESHOLD,
    maybe_top_up_purge_candidates,
    needs_purge_buffer_refill,
    top_up_purge_candidates,
    write_purge_candidates_cache,
)


def _item(rating_key: str, *, title: str | None = None, score: float = 1.0) -> dict:
    return {
        "rating_key": rating_key,
        "title": title or rating_key,
        "purge_score": score,
        "media_type": "movie",
        "file_size": 2_000_000_000,
    }


class PurgeBufferTopUpTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "purge-topup.db")
        self.db.ensure_seed_data()
        self.settings = Settings()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_needs_refill_when_below_threshold(self) -> None:
        write_purge_candidates_cache(
            self.db,
            [_item(f"rk-{i}") for i in range(REFILL_THRESHOLD - 1)],
        )
        self.assertTrue(needs_purge_buffer_refill(self.db))

    def test_maybe_top_up_skips_when_above_threshold(self) -> None:
        write_purge_candidates_cache(
            self.db,
            [_item(f"rk-{i}") for i in range(REFILL_THRESHOLD)],
        )
        self.assertIsNone(maybe_top_up_purge_candidates(self.db, self.settings))

    @patch("projectionist.scheduler.tasks.purge_candidates.suggest_purge_candidates_rich")
    def test_top_up_appends_without_reshuffling(self, mock_rich) -> None:
        existing = [_item("keep-a", score=9.0), _item("keep-b", score=8.0)]
        write_purge_candidates_cache(self.db, existing, generated_at=10.0)
        mock_rich.return_value = [
            _item("keep-a", score=99.0),
            _item("new-1", score=7.0),
            _item("new-2", score=6.0),
            _item("new-3", score=5.0),
        ]
        payload = top_up_purge_candidates(self.db, self.settings, target=4)
        keys = [item["rating_key"] for item in payload["items"]]
        self.assertEqual(keys[:2], ["keep-a", "keep-b"])
        self.assertEqual(set(keys[2:]), {"new-1", "new-2"})
        self.assertEqual(payload["count"], 4)
        self.assertFalse(payload["refilling"])
        self.assertEqual(payload["buffer_target"], BUFFER_TARGET)
        self.assertEqual(payload["page_size"], 20)
        kwargs = mock_rich.call_args.kwargs
        self.assertEqual(kwargs.get("exclude_rating_keys"), {"keep-a", "keep-b"})

    def test_enrich_prefers_library_file_size(self) -> None:
        self.db.upsert_library_item(
            {
                "rating_key": "show-1",
                "media_type": "show",
                "title": "Huge Show",
                "year": 2020,
                "file_size": 9_000_000_000,
                "total_episode_count": 10,
                "unwatched_episode_count": 10,
                "view_count": 0,
            }
        )
        enriched = enrich_purge_candidate_rows(
            self.db,
            self.settings,
            [
                {
                    "rating_key": "show-1",
                    "media_type": "show",
                    "title": "Stale",
                    "file_size": 1,
                    "taste_match": 40.0,
                }
            ],
        )
        self.assertEqual(len(enriched), 1)
        self.assertEqual(enriched[0]["file_size"], 9_000_000_000)
        self.assertEqual(enriched[0]["title"], "Huge Show")
        self.assertEqual(enriched[0]["total_episode_count"], 10)


class PurgeEnrichApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)
        self.db = jobs.get_job_manager().db

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_enrich_endpoint_returns_library_sizes(self) -> None:
        self.db.upsert_library_item(
            {
                "rating_key": "rk-enrich",
                "media_type": "movie",
                "title": "Enrich Me",
                "year": 2019,
                "file_size": 3_500_000_000,
                "view_count": 0,
            }
        )
        write_purge_candidates_cache(
            self.db,
            [
                {
                    "rating_key": "rk-enrich",
                    "media_type": "movie",
                    "title": "Enrich Me",
                    "file_size": 1,
                    "purge_score": 2.0,
                }
            ],
        )
        resp = self.client.post(
            "/api/library/purge-candidates/enrich",
            json={"rating_keys": ["rk-enrich"]},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["file_size"], 3_500_000_000)

    def test_get_includes_buffer_metadata(self) -> None:
        write_purge_candidates_cache(self.db, [_item("meta-1")], generated_at=42.0)
        resp = self.client.get("/api/library/purge-candidates")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["page_size"], 20)
        self.assertEqual(body["buffer_target"], BUFFER_TARGET)
        self.assertFalse(body["refilling"])


if __name__ == "__main__":
    unittest.main()
