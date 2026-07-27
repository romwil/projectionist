"""Tests for taste cluster tag filtering and refresh cleanup."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from projectionist.config_store import Settings
from projectionist.library.db import DEFAULT_LENS_ID, Database
from projectionist.models.schemas import PreferenceSignal
from projectionist.preferences.store import remember_preference
from projectionist.scheduler.tasks import taste_refresh
from projectionist.taste.clusters import (
    cluster_tokens_from_text,
    filter_cluster_tags,
    is_valid_cluster_tag,
    normalize_cluster_tag,
)


class ClusterTagFilterTests(unittest.TestCase):
    def test_rejects_punctuation_stopwords_and_contractions(self) -> None:
        junk = ["-", "of", "in.", "you've", "here's", "got", "a", "the", "to"]
        for tag in junk:
            self.assertFalse(is_valid_cluster_tag(tag), tag)

    def test_keeps_meaningful_genres_and_moods(self) -> None:
        good = ["amused", "family", "hilarious", "comedy", "sci-fi", "neo-noir", "strong"]
        for tag in good:
            self.assertTrue(is_valid_cluster_tag(tag), tag)

    def test_normalize_strips_edge_punctuation(self) -> None:
        self.assertEqual(normalize_cluster_tag(" in. "), "in")
        self.assertEqual(normalize_cluster_tag("-"), "")
        self.assertEqual(normalize_cluster_tag("  Comedy "), "comedy")

    def test_tokens_from_prose_drop_filler(self) -> None:
        tokens = cluster_tokens_from_text(
            "Here's what you've got: a hilarious comedy with family vibes in."
        )
        self.assertIn("hilarious", tokens)
        self.assertIn("comedy", tokens)
        self.assertIn("family", tokens)
        self.assertIn("vibes", tokens)
        for junk in ("heres", "youve", "got", "what", "with", "in"):
            self.assertNotIn(junk, tokens)

    def test_filter_cluster_tags_on_structured_lists(self) -> None:
        self.assertEqual(
            filter_cluster_tags(["Comedy", "of", "sci-fi", "-", "you've"]),
            ["comedy", "sci-fi"],
        )


class TasteRefreshCleanupTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_refresh_skips_junk_tokens_from_preference_prose(self) -> None:
        self.db.add_preference(
            "positive",
            "here's what you've got of hilarious comedy in.",
            weight=2.0,
        )
        result = asyncio.run(taste_refresh.run(self.db, Settings(), lambda: False))
        self.assertEqual(result["status"], "completed")
        with self.db.connect() as conn:
            tags = {
                str(r["cluster_tag"])
                for r in conn.execute(
                    "SELECT cluster_tag FROM lens_taste_profile WHERE lens_id = 'general'"
                ).fetchall()
            }
        self.assertIn("hilarious", tags)
        self.assertIn("comedy", tags)
        for junk in ("here's", "you've", "got", "of", "in.", "-", "in", "heres", "youve"):
            self.assertNotIn(junk, tags)

    def test_refresh_purges_existing_unlocked_junk_rows(self) -> None:
        self.db.set_lens_taste_weight(DEFAULT_LENS_ID, "comedy", 0.8, explicit_lock=False)
        with self.db.connect() as conn:
            for junk in ("you've", "of", "in.", "-", "got", "here's"):
                conn.execute(
                    """
                    INSERT INTO lens_taste_profile (lens_id, cluster_tag, weight, explicit_lock)
                    VALUES ('general', ?, 0.7, 0)
                    """,
                    (junk,),
                )
        # Seed a real signal so refresh has work to do.
        self.db.add_preference("positive", "comedy", weight=1.0)
        result = asyncio.run(taste_refresh.run(self.db, Settings(), lambda: False))
        self.assertGreaterEqual(int(result.get("junk_purged") or 0), 1)
        profile = self.db.get_effective_taste_profile(None, limit=40)
        tags = {c["cluster_tag"] for c in profile}
        self.assertIn("comedy", tags)
        for junk in ("you've", "of", "in.", "-", "got", "here's"):
            self.assertNotIn(junk, tags)

    def test_effective_profile_hides_junk_before_purge(self) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO lens_taste_profile (lens_id, cluster_tag, weight, explicit_lock)
                VALUES
                  ('general', 'comedy', 0.8, 0),
                  ('general', 'you''ve', 0.7, 0),
                  ('general', 'of', 0.6, 0)
                """
            )
        profile = self.db.get_effective_taste_profile(None, limit=40)
        tags = [c["cluster_tag"] for c in profile]
        self.assertEqual(tags, ["comedy"])

    def test_remember_preference_does_not_store_sentence_as_cluster(self) -> None:
        remember_preference(
            self.db,
            PreferenceSignal(
                signal_type="explicit",
                text="you've got to see more comedy",
            ),
        )
        with self.db.connect() as conn:
            tags = {
                str(r["cluster_tag"])
                for r in conn.execute("SELECT cluster_tag FROM lens_taste_profile").fetchall()
            }
        self.assertNotIn("you've got to see more comedy", tags)
        self.assertEqual(tags, {"comedy"})
        # Preference fact is still recorded for memory.
        facts = self.db.preference_facts(limit=5)
        self.assertTrue(any("comedy" in str(f["text"]) for f in facts))

    def test_remember_preference_promotes_clean_short_tag(self) -> None:
        remember_preference(
            self.db,
            PreferenceSignal(signal_type="explicit", text="noir", weight=2.0),
        )
        profile = self.db.get_effective_taste_profile(None, limit=10)
        self.assertTrue(any(c["cluster_tag"] == "noir" for c in profile))

    def test_set_user_taste_weight_rejects_junk(self) -> None:
        with self.assertRaises(ValueError):
            self.db.set_user_taste_weight("u1", "you've", 0.9)


if __name__ == "__main__":
    unittest.main()
