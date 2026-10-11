"""Surprising neighbors need a story we can name, not missing shelf labels."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.library.db import Database
from projectionist.library.neighbors import compute_neighbors_for_seed
from projectionist.library.plot_kinship import specific_plot_link, surprising_plot_link
from projectionist.library.relations import list_relations_for_item

BAKE_PLOT = "Amateur bakers compete around a signature bake inside a failing colony."
SPY_PLOT = "Rivals reunite after amateur bakers compete and ruin a signature bake tonight."
GRAVITY_PLOT = "Astronauts fight to survive after debris destroys their orbiting shuttle."
MUSEUM_PLOT = (
    "A reality company builds museum exhibits, from dinosaur halls to a Titanic gallery, "
    "and the crew celebrates creative arts while installing each hall."
)
ALIEN_PLOT = (
    "Federal agents investigate aliens and a government conspiracy, and between cases "
    "they argue about creative arts in the bureau basement."
)
MUSEUM_PEER_PLOT = (
    "Installers spend a season placing museum exhibits inside a new natural history hall."
)


def _title(db: Database, **fields) -> int:
    payload = {
        "media_type": "movie",
        "year": 2015,
        "genres": ["Drama"],
        "keywords": [],
        "summary": "",
    }
    payload.update(fields)
    return db.upsert_library_item(payload)


class SurprisingPlotLinkTests(unittest.TestCase):
    def test_high_cosine_low_overlap_names_the_kinship(self) -> None:
        link = surprising_plot_link(
            cosine=0.86,
            overlap=0.0,
            seed_text=BAKE_PLOT,
            peer_text=SPY_PLOT,
            shelf_labels={"reality", "food", "thriller", "espionage"},
        )
        self.assertIsNotNone(link)
        assert link is not None
        sentence = str(link["sentence"])
        self.assertIn("amateur bakers", sentence)
        self.assertTrue(sentence.lower().startswith("both stories turn on"))
        self.assertNotIn("almost no shared", sentence.lower())
        self.assertNotIn("nothing in common", sentence.lower())
        self.assertEqual(link["shelf_note"], "Shelf labels barely overlap")

    def test_missing_labels_and_empty_plot_are_not_surprising(self) -> None:
        self.assertIsNone(
            surprising_plot_link(
                cosine=0.91,
                overlap=0.0,
                seed_text="",
                peer_text="",
                shelf_labels=set(),
            )
        )
        self.assertIsNone(
            surprising_plot_link(
                cosine=0.91,
                overlap=0.0,
                seed_text="Unknown",
                peer_text="No overview available",
                shelf_labels={"reality", "space"},
            )
        )
        self.assertIsNone(
            surprising_plot_link(
                cosine=0.91,
                overlap=None,
                seed_text=BAKE_PLOT,
                peer_text=SPY_PLOT,
                shelf_labels=set(),
            )
        )

    def test_unrelated_plots_are_excluded_even_with_strong_cosine(self) -> None:
        link = surprising_plot_link(
            cosine=0.88,
            overlap=0.0,
            seed_text=BAKE_PLOT,
            peer_text=GRAVITY_PLOT,
            shelf_labels={"reality", "food", "science fiction", "space"},
        )
        self.assertIsNone(link)

    def test_obvious_shelf_overlap_stays_off_the_surprising_rail(self) -> None:
        link = surprising_plot_link(
            cosine=0.9,
            overlap=0.8,
            seed_text=BAKE_PLOT,
            peer_text=SPY_PLOT,
            shelf_labels={"drama"},
        )
        self.assertIsNone(link)


class SurprisingRelationPayloadTests(unittest.TestCase):
    def test_named_kinship_is_eligible_and_label_noise_is_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "relations.db")
            seed = _title(
                db,
                rating_key="bake",
                tmdb_id=75817,
                title="The Great American Baking Show",
                media_type="show",
                genres=["Reality"],
                keywords=["food", "cooking competition"],
                summary=BAKE_PLOT,
            )
            twin = _title(
                db,
                rating_key="bake-dup",
                tmdb_id=75817,
                title="The Great American Baking Show",
                media_type="show",
                genres=["Reality"],
                keywords=["food"],
                summary=BAKE_PLOT,
            )
            kin = _title(
                db,
                rating_key="spy-bakers",
                tmdb_id=42,
                title="Covert Kitchen",
                genres=["Thriller"],
                keywords=["espionage"],
                summary=SPY_PLOT,
            )
            noise = _title(
                db,
                rating_key="gravity",
                tmdb_id=99,
                title="Gravity",
                genres=["Science Fiction"],
                keywords=["space"],
                summary=GRAVITY_PLOT,
            )
            empty = _title(
                db,
                rating_key="sparrow",
                tmdb_id=100,
                title="Red Sparrow",
                genres=["Thriller"],
                keywords=["assassin"],
                summary="Unknown",
            )
            db.replace_relations_of_types(
                {
                    "neighbor": [
                        (seed, twin, "neighbor", 0.99, "item_neighbors"),
                        (seed, kin, "neighbor", 0.84, "item_neighbors"),
                        (seed, noise, "neighbor", 0.86, "item_neighbors"),
                        (seed, empty, "neighbor", 0.83, "item_neighbors"),
                    ]
                }
            )

            payload = list_relations_for_item(db, seed, limit=10)
            by_title = {edge["title"]: edge for edge in payload["items"]}

            self.assertNotIn("The Great American Baking Show", by_title)
            self.assertIn("Covert Kitchen", by_title)
            self.assertNotIn("Gravity", by_title)
            self.assertNotIn("Red Sparrow", by_title)

            linked = by_title["Covert Kitchen"]["why"]
            self.assertTrue(linked["plot_link"])
            self.assertIn("amateur bakers", linked["plot_link"].lower())
            self.assertEqual(linked["surprise_flavor"], linked["plot_link"])
            self.assertNotIn("almost no shared", linked["plot_link"].lower())
            self.assertNotIn("nothing in common", linked["label"].lower())
            self.assertEqual(linked["shelf_note"], "Shelf labels barely overlap")

            for title in ("Gravity", "Red Sparrow"):
                self.assertNotIn(title, by_title)


class MuseumExhibitNeighborTests(unittest.TestCase):
    def test_generic_phrase_and_bare_cosine_do_not_match_a_museum_show(self) -> None:
        """A reality museum-exhibit plot must not pick up sci-fi via cosine or 'creative arts'."""
        self.assertIsNone(
            specific_plot_link(
                seed_text=MUSEUM_PLOT,
                peer_text=ALIEN_PLOT,
                shelf_labels={"reality", "documentary", "science fiction", "mystery"},
            )
        )
        self.assertIsNone(
            surprising_plot_link(
                cosine=0.91,
                overlap=0.0,
                seed_text=MUSEUM_PLOT,
                peer_text=ALIEN_PLOT,
                shelf_labels={"reality", "documentary", "science fiction", "mystery"},
            )
        )
        honest = specific_plot_link(
            seed_text=MUSEUM_PLOT,
            peer_text=MUSEUM_PEER_PLOT,
            shelf_labels={"reality", "documentary"},
        )
        self.assertIsNotNone(honest)
        assert honest is not None
        self.assertIn("museum exhibits", honest["sentence"].lower())
        self.assertNotIn("creative arts", honest["sentence"].lower())
        self.assertNotIn("plot kinship", honest["sentence"].lower())

        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "museum.db")
            seed = _title(
                db,
                rating_key="museum-men",
                tmdb_id=1,
                title="Museum Men",
                media_type="show",
                genres=["Reality"],
                keywords=["museum"],
                summary=MUSEUM_PLOT,
            )
            xfiles = _title(
                db,
                rating_key="xfiles",
                tmdb_id=2,
                title="The X-Files",
                genres=["Science Fiction", "Mystery"],
                keywords=["alien"],
                summary=ALIEN_PLOT,
            )
            peer = _title(
                db,
                rating_key="hall",
                tmdb_id=3,
                title="Hall Install",
                genres=["Reality"],
                keywords=["museum"],
                summary=MUSEUM_PEER_PLOT,
            )
            db.replace_relations_of_types(
                {
                    "neighbor": [
                        (seed, xfiles, "neighbor", 0.88, "item_neighbors"),
                        (seed, peer, "neighbor", 0.8, "item_neighbors"),
                    ]
                }
            )
            payload = list_relations_for_item(db, seed, limit=10)
            titles = {edge["title"] for edge in payload["items"]}
            self.assertNotIn("The X-Files", titles)
            self.assertIn("Hall Install", titles)
            why = next(edge["why"] for edge in payload["items"] if edge["title"] == "Hall Install")
            self.assertIn("museum exhibits", why["label"].lower())
            self.assertNotIn("Strong plot kinship", why["label"])
            self.assertNotIn("creative arts", why["label"].lower())


class MissingShelfSurpriseScoreTests(unittest.TestCase):
    def test_empty_shelf_labels_do_not_score_as_max_surprise(self) -> None:
        neighbors = compute_neighbors_for_seed(
            1,
            [1.0, 0.0],
            set(),
            [
                (2, [1.0, 0.0], set()),
                (3, [1.0, 0.0], {"drama"}),
            ],
        )
        by_id = {neighbor_id: surprise for neighbor_id, _score, surprise in neighbors}
        self.assertEqual(by_id[2], 0.0)
        self.assertEqual(by_id[3], 0.0)
        self.assertGreater(neighbors[0][1], 0.0)
