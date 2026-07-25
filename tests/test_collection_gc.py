"""Tests for ephemeral Plex collection TTL tagging and GC dry-run."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from projectionist.config_store import FeatureFlags, Settings
from projectionist.connectors.plex_collections import (
    apply_ephemeral_title_prefix,
    is_ephemeral_collection_title,
)
from projectionist.library.db import EPHEMERAL_COLLECTION_PREFIX, Database
from projectionist.scheduler.tasks.collection_gc import prune_expired_ephemeral_collections


class EphemeralTitleHelpersTests(unittest.TestCase):
    def test_prefix_applied_once(self) -> None:
        titled = apply_ephemeral_title_prefix("Movie Night", prefix=EPHEMERAL_COLLECTION_PREFIX)
        self.assertTrue(titled.startswith(EPHEMERAL_COLLECTION_PREFIX))
        again = apply_ephemeral_title_prefix(titled, prefix=EPHEMERAL_COLLECTION_PREFIX)
        self.assertEqual(titled, again)
        self.assertTrue(is_ephemeral_collection_title(titled, prefix=EPHEMERAL_COLLECTION_PREFIX))
        self.assertFalse(
            is_ephemeral_collection_title("My Evergreen Shelf", prefix=EPHEMERAL_COLLECTION_PREFIX)
        )


class CollectionGcTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_record_and_list_expired(self) -> None:
        self.db.record_ephemeral_plex_collection(
            plex_rating_key="1001",
            section_id="1",
            title=f"{EPHEMERAL_COLLECTION_PREFIX}Movie Night",
            media_type="movie",
            ttl_hours=1,
        )
        # Force expiry.
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE ephemeral_plex_collections SET expires_at = ?",
                (time.time() - 10,),
            )
        expired = self.db.list_expired_ephemeral_plex_collections()
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0]["plex_rating_key"], "1001")

    def test_dry_run_does_not_delete(self) -> None:
        self.db.record_ephemeral_plex_collection(
            plex_rating_key="2002",
            section_id="1",
            title=f"{EPHEMERAL_COLLECTION_PREFIX}Weekend",
            media_type="movie",
            ttl_hours=1,
        )
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE ephemeral_plex_collections SET expires_at = ?",
                (time.time() - 10,),
            )
        settings = Settings(
            plex_url="http://plex.local:32400",
            plex_token="token",
            features=FeatureFlags(
                plex_collections_enabled=True,
                ephemeral_collection_gc_enabled=True,
                ephemeral_collection_gc_dry_run=True,
            ),
        )
        with mock.patch(
            "projectionist.connectors.plex_collections.delete_collection"
        ) as delete_mock:
            result = prune_expired_ephemeral_collections(self.db, settings)
        self.assertTrue(result.get("dry_run"))
        self.assertEqual(result.get("deleted"), 0)
        self.assertEqual(result.get("expired"), 1)
        delete_mock.assert_not_called()
        # Row still present.
        self.assertEqual(len(self.db.list_ephemeral_plex_collections()), 1)

    def test_disabled_skips(self) -> None:
        settings = Settings(
            plex_url="http://plex.local:32400",
            plex_token="token",
            features=FeatureFlags(ephemeral_collection_gc_enabled=False),
        )
        result = prune_expired_ephemeral_collections(self.db, settings)
        self.assertEqual(result["status"], "skipped")

    def test_prune_deletes_only_tracked_rows(self) -> None:
        self.db.record_ephemeral_plex_collection(
            plex_rating_key="3003",
            section_id="1",
            title=f"{EPHEMERAL_COLLECTION_PREFIX}Gone",
            media_type="movie",
            ttl_hours=1,
        )
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE ephemeral_plex_collections SET expires_at = ?",
                (time.time() - 10,),
            )
        settings = Settings(
            plex_url="http://plex.local:32400",
            plex_token="token",
            features=FeatureFlags(
                ephemeral_collection_gc_enabled=True,
                ephemeral_collection_gc_dry_run=False,
            ),
        )
        with mock.patch("projectionist.connectors.plex.PlexClient"), mock.patch(
            "projectionist.connectors.plex_collections.delete_collection"
        ) as delete_mock:
            result = prune_expired_ephemeral_collections(self.db, settings)
        self.assertEqual(result.get("deleted"), 1)
        delete_mock.assert_called_once()
        self.assertEqual(len(self.db.list_ephemeral_plex_collections()), 0)


if __name__ == "__main__":
    unittest.main()
