"""Tests for taste cluster tag filtering and refresh cleanup."""

from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from projectionist.config_store import Settings
from projectionist.library.db import BOOTSTRAP_OWNER_ID, DEFAULT_LENS_ID, Database
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
        good = [
            "family",
            "comedy",
            "sci-fi",
            "neo-noir",
            "noir",
            "science fiction",
            "tv movie",
            "musical",
        ]
        for tag in good:
            self.assertTrue(is_valid_cluster_tag(tag), tag)

    def test_refuses_abstract_unigrams(self) -> None:
        junk = [
            "plot",
            "story",
            "stories",
            "rated",
            "paying",
            "protagonist",
            "strong",
            "pulls",
            "rabbit",
            "spectacle",
            "royale",
            "rites",
            "hilarious",
            "vibes",
            "amused",
        ]
        for tag in junk:
            self.assertFalse(is_valid_cluster_tag(tag), tag)

    def test_normalize_strips_edge_punctuation(self) -> None:
        self.assertEqual(normalize_cluster_tag(" in. "), "in")
        self.assertEqual(normalize_cluster_tag("-"), "")
        self.assertEqual(normalize_cluster_tag("  Comedy "), "comedy")

    def test_tokens_from_prose_drop_filler(self) -> None:
        tokens = cluster_tokens_from_text(
            "Here's what you've got: a hilarious comedy with family vibes in."
        )
        self.assertIn("comedy", tokens)
        self.assertIn("family", tokens)
        for junk in ("hilarious", "vibes", "heres", "youve", "got", "what", "with", "in"):
            self.assertNotIn(junk, tokens)

    def test_filter_cluster_tags_on_structured_lists(self) -> None:
        self.assertEqual(
            filter_cluster_tags(["Comedy", "of", "sci-fi", "-", "you've", "rabbit"]),
            ["comedy", "sci-fi"],
        )
        self.assertEqual(
            filter_cluster_tags(["Action & Adventure", "Science Fiction", "cyberpunk"]),
            ["action adventure", "science fiction"],
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
        self.assertIn("comedy", tags)
        for junk in (
            "hilarious",
            "here's",
            "you've",
            "got",
            "of",
            "in.",
            "-",
            "in",
            "heres",
            "youve",
        ):
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
        with self.assertRaises(ValueError):
            self.db.set_user_taste_weight("u1", "rabbit", 0.9)

    def test_explicit_preference_does_not_lock_or_store_overweight(self) -> None:
        remember_preference(
            self.db,
            PreferenceSignal(signal_type="explicit", text="noir", weight=2.0),
        )
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT weight, explicit_lock FROM lens_taste_profile WHERE cluster_tag = 'noir'"
            ).fetchone()
            facts = conn.execute("SELECT weight FROM preference_facts").fetchall()
        self.assertIsNotNone(row)
        self.assertLessEqual(float(row["weight"]), 1.0)
        self.assertEqual(int(row["explicit_lock"]), 0)
        self.assertTrue(any(float(f["weight"]) == 2.0 for f in facts))

    def test_new_clusters_default_unlocked(self) -> None:
        self.db.set_lens_taste_weight(DEFAULT_LENS_ID, "comedy", 0.6)
        self.db.set_user_taste_weight(BOOTSTRAP_OWNER_ID, "noir", 0.9)
        with self.db.connect() as conn:
            lens = conn.execute(
                "SELECT explicit_lock FROM lens_taste_profile WHERE cluster_tag = 'comedy'"
            ).fetchone()
            user = conn.execute(
                "SELECT explicit_lock FROM user_taste_profile WHERE cluster_tag = 'noir'"
            ).fetchone()
        self.assertEqual(int(lens["explicit_lock"]), 0)
        self.assertEqual(int(user["explicit_lock"]), 0)

    def test_refresh_purges_locked_junk_including_rabbit(self) -> None:
        self.db.set_lens_taste_weight(DEFAULT_LENS_ID, "comedy", 0.8, explicit_lock=True)
        with self.db.connect() as conn:
            for junk in ("rabbit", "plot", "you've"):
                conn.execute(
                    """
                    INSERT INTO lens_taste_profile (lens_id, cluster_tag, weight, explicit_lock)
                    VALUES ('general', ?, 0.9, 1)
                    """,
                    (junk,),
                )
                conn.execute(
                    """
                    INSERT INTO user_taste_profile
                        (user_id, cluster_tag, weight, explicit_lock, last_updated)
                    VALUES (?, ?, 0.9, 1, 1.0)
                    """,
                    (BOOTSTRAP_OWNER_ID, junk),
                )
        self.db.add_preference("positive", "comedy", weight=1.0)
        result = asyncio.run(taste_refresh.run(self.db, Settings(), lambda: False))
        self.assertGreaterEqual(int(result.get("junk_purged") or 0), 1)
        profile = self.db.get_effective_taste_profile(BOOTSTRAP_OWNER_ID, limit=40)
        tags = {c["cluster_tag"] for c in profile}
        self.assertIn("comedy", tags)
        for junk in ("rabbit", "plot", "you've"):
            self.assertNotIn(junk, tags)
        with self.db.connect() as conn:
            leftover = {
                str(r["cluster_tag"])
                for r in conn.execute("SELECT cluster_tag FROM lens_taste_profile").fetchall()
            }
            leftover |= {
                str(r["cluster_tag"])
                for r in conn.execute("SELECT cluster_tag FROM user_taste_profile").fetchall()
            }
        for junk in ("rabbit", "plot", "you've"):
            self.assertNotIn(junk, leftover)


if __name__ == "__main__":
    unittest.main()
