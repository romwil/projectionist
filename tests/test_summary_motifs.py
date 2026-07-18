"""Tests for summary motif extraction (normalization, bigrams, Kill Bill budget)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from curatorx.library.db import Database
from curatorx.scheduler.tasks.summary_motifs import (
    extract_motif_rows,
    keyword_stems,
    normalize_token,
    tokenize_plot_text,
)


class MotifNormalizationTests(unittest.TestCase):
    def test_normalize_possessives(self) -> None:
        self.assertEqual(normalize_token("bride's"), "bride")
        self.assertEqual(normalize_token("Bride's"), "bride")
        self.assertEqual(normalize_token("coma"), "coma")

    def test_tokenize_includes_unigrams_and_bigrams(self) -> None:
        tokens = tokenize_plot_text(
            "The Bride awakens from a coma and starts a death list."
        )
        self.assertIn("bride", tokens)
        self.assertIn("coma", tokens)
        self.assertIn("the bride", tokens)
        self.assertIn("death list", tokens)
        self.assertNotIn("the", tokens)

    def test_tokenize_uses_tagline_and_logline(self) -> None:
        tokens = tokenize_plot_text(
            "",
            "",
            "Revenge is a dish best served cold",
            "A bride hunts her betrayers after a coma.",
        )
        self.assertIn("revenge", tokens)
        self.assertIn("bride", tokens)
        self.assertIn("coma", tokens)

    def test_keyword_stems_from_phrases(self) -> None:
        stems = keyword_stems(["martial arts", "revenge"])
        self.assertIn("martial", stems)
        self.assertIn("arts", stems)
        self.assertIn("revenge", stems)
        self.assertIn("martial arts", stems)


class KillBillMotifExtractionTests(unittest.TestCase):
    def test_extract_keeps_bride_and_coma_despite_budget_pressure(self) -> None:
        """Kill Bill-like plot must retain bride+coma even with many competing tokens."""
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "lib.db")
            # Target title: high-signal tokens buried among many rare words.
            db.upsert_library_item(
                {
                    "rating_key": "kb1",
                    "media_type": "movie",
                    "title": "Kill Bill: Vol. 1",
                    "year": 2003,
                    "summary": (
                        "The Bride awakens from a coma and tracks a death list of "
                        "betrayers across bullet payback showdowns with Okinawa "
                        "swordsmith Hattori Hanzo while seeking vengeance."
                    ),
                    "tmdb_overview": "A former assassin seeks revenge after a wedding massacre.",
                    "tagline": "Revenge is a dish best served cold.",
                    "keywords": ["revenge", "martial arts", "assassin"],
                }
            )
            # Second title carries bride's (possessive) + coma so DF >= 2.
            db.upsert_library_item(
                {
                    "rating_key": "kb2",
                    "media_type": "movie",
                    "title": "Kill Bill: Vol. 2",
                    "year": 2004,
                    "summary": "The bride's journey continues after the coma aftermath.",
                    "keywords": ["revenge"],
                }
            )
            # Filler corpus so DF band is meaningful and rare tokens compete for slots.
            fillers = [
                ("f1", "Okinawa swordsmith crafts a legendary katana for a warrior."),
                ("f2", "Bullet payback showdowns erupt in a Tokyo nightclub."),
                ("f3", "Wedding massacre survivors plot their next move."),
                ("f4", "Assassin tracks betrayers across continents for vengeance."),
                ("f5", "Swordsmith Hattori trains a quiet apprentice in secrecy."),
                ("f6", "Nightclub dancers witness a sudden violent confrontation."),
                ("f7", "Continents blur as the warrior follows a death list."),
                ("f8", "Apprentice learns secrecy before facing the assassin."),
                ("f9", "Tokyo streets hide another bullet payback encounter."),
                ("f10", "Legendary katana changes hands after the wedding massacre."),
            ]
            for key, summary in fillers:
                db.upsert_library_item(
                    {
                        "rating_key": key,
                        "media_type": "movie",
                        "title": f"Filler {key}",
                        "year": 2000,
                        "summary": summary,
                    }
                )

            rows = extract_motif_rows(db)
            by_item: dict[int, set[str]] = {}
            for item_id, facet_type, value in rows:
                self.assertEqual(facet_type, "motif")
                by_item.setdefault(item_id, set()).add(value)

            titles = {
                str(row["title"]): int(row["id"]) for row in db.all_library_items()
            }
            vol1 = by_item[titles["Kill Bill: Vol. 1"]]
            self.assertIn("bride", vol1)
            self.assertIn("coma", vol1)
            # Possessive on Vol. 2 should normalize into the same unigram.
            vol2 = by_item[titles["Kill Bill: Vol. 2"]]
            self.assertIn("bride", vol2)
            self.assertNotIn("bride's", vol2)


if __name__ == "__main__":
    unittest.main()
