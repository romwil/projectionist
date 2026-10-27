"""Surprising neighbors need a story we can name, not missing shelf labels."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from projectionist.library.db import Database
from projectionist.library.feeds import neighbors_payload
from projectionist.library.neighbors import compute_neighbors_for_seed, enrich_neighbors_with_explanations
from projectionist.library.plot_kinship import (
    honest_plot_link,
    specific_plot_link,
    surprising_items_if_distinct,
    surprising_plot_link,
)
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


class HonestPlotLinkCopyTests(unittest.TestCase):
    """For you / More Like This copy names a subject, or stays empty."""

    HOUSE_PLOT = (
        "The team try to cure complex and rare diseases from very ill ordinary people "
        "in the United States of America."
    )
    BEAUTY_PLOT = (
        "They uncover a sexually transmitted virus that transforms ordinary people "
        "into visions of physical perfection, but with terrifying consequences."
    )
    HIGH_POTENTIAL_PLOT = (
        "High Potential is an American crime comedy drama television series created "
        "by Drew Goddard for ABC. In January 2025, the series was renewed for a "
        "second season which premiered on September 16, 2025."
    )
    TED_LASSO_PLOT = (
        "Ted Lasso is an American sports comedy-drama television series developed "
        "by Jason Sudeikis. It was renewed for a fourth season, which premiered "
        "on August 5, 2026. The series has received critical acclaim."
    )
    TROPICAL_BAKE_PLOT = (
        "The bakers dive into desserts from tropical climates featuring Latin "
        "America's favorite, Flan; the Cuban puff pastry treat, Pastelitos; "
        "and a tiered take on Pavlova."
    )
    FIREFLY_INSECT_PLOT = (
        "Photinus beetles trap their males as prey. Fireflies are found in "
        "temperate and tropical climates. Many live in marshes or in wet, "
        "wooded areas where their larvae have abundant sources of food."
    )

    def test_ordinary_people_is_not_a_named_subject(self) -> None:
        link = specific_plot_link(
            seed_text=self.HOUSE_PLOT,
            peer_text=self.BEAUTY_PLOT,
            shelf_labels={"drama", "science fiction"},
        )
        self.assertIsNone(link)

    def test_drama_television_and_which_premiered_are_refused(self) -> None:
        link = specific_plot_link(
            seed_text=self.HIGH_POTENTIAL_PLOT,
            peer_text=self.TED_LASSO_PLOT,
            shelf_labels={"comedy", "drama"},
        )
        self.assertIsNone(link)

    def test_tropical_climates_is_not_a_named_subject(self) -> None:
        link = specific_plot_link(
            seed_text=self.TROPICAL_BAKE_PLOT,
            peer_text=self.FIREFLY_INSECT_PLOT,
            shelf_labels={"reality", "science fiction"},
        )
        self.assertIsNone(link)

    def test_junk_sentence_never_gets_an_article_glued_on(self) -> None:
        for terms in (
            ["ordinary people"],
            ["drama television"],
            ["which premiered"],
            ["drama television", "which premiered"],
            ["tropical climates"],
        ):
            rebuilt = honest_plot_link(
                {"sentence": "Both stories turn on an ordinary people.", "terms": terms}
            )
            self.assertIsNone(rebuilt, terms)

    def test_honest_subject_still_names_amateur_bakers(self) -> None:
        link = specific_plot_link(
            seed_text=BAKE_PLOT,
            peer_text=SPY_PLOT,
            shelf_labels={"reality", "thriller"},
        )
        self.assertIsNotNone(link)
        assert link is not None
        sentence = str(link["sentence"]).lower()
        self.assertIn("amateur bakers", sentence)
        self.assertTrue(sentence.startswith("both stories turn on"))
        self.assertNotIn("an ordinary people", sentence)
        self.assertNotIn("a drama television", sentence)
        self.assertNotIn("a which premiered", sentence)


SCREENSHOT_TRIVIA_TERMS = (
    ["cult following", "box office"],
    ["mixed reviews", "united states"],
    ["principal photography", "pinewood studios"],
    ["united kingdom", "york city"],
    ["working title"],
    ["united states"],
    ["team investigates"],
    ["victorian mansion"],
)

SCREENSHOT_TRIVIA_SENTENCES = (
    "Both stories turn on a cult following and a box office.",
    "Both stories turn on mixed reviews and united states.",
    "Both stories turn on a principal photography and pinewood studios.",
    "Both stories turn on an united kingdom and a york city.",
    "Both stories turn on a working title.",
    "Both stories turn on united states.",
    "Both stories turn on team investigates.",
    "Both stories turn on a victorian mansion.",
)


class ProductionTriviaPlotLinkTests(unittest.TestCase):
    """Infobox leftovers are not a named plot subject — omit the peer."""

    LAST_JEDI_TRIVIA = (
        "The Resistance faces the First Order after mixed reviews in the United States. "
        "Principal photography took place at Pinewood Studios. The working title leaked."
    )
    RANDOM_TRIVIA = (
        "A slasher opens to mixed reviews and a cult following at the box office. "
        "Principal photography was at Pinewood Studios in the United Kingdom and New York City. "
        "The working title changed after the United States release."
    )
    HIGH_POTENTIAL_GLUE = (
        "The team investigates a murder in a victorian mansion after the consultant joins the squad."
    )
    BLACK_HOLE_GLUE = (
        "Scientists watch a ship vanish. The team investigates wreckage near a victorian mansion."
    )

    def test_screenshot_terms_are_refused_by_honest_plot_link(self) -> None:
        for terms, sentence in zip(SCREENSHOT_TRIVIA_TERMS, SCREENSHOT_TRIVIA_SENTENCES):
            rebuilt = honest_plot_link({"sentence": sentence, "terms": terms})
            self.assertIsNone(rebuilt, sentence)

    def test_last_jedi_trivia_overlap_is_not_a_named_subject(self) -> None:
        link = specific_plot_link(
            seed_text=self.LAST_JEDI_TRIVIA,
            peer_text=self.RANDOM_TRIVIA,
            shelf_labels={"science fiction", "horror"},
        )
        self.assertIsNone(link)

    def test_team_investigates_and_victorian_mansion_are_refused(self) -> None:
        link = specific_plot_link(
            seed_text=self.HIGH_POTENTIAL_GLUE,
            peer_text=self.BLACK_HOLE_GLUE,
            shelf_labels={"crime", "science fiction"},
        )
        self.assertIsNone(link)

    def test_similar_and_surprising_omit_trivia_peers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "trivia.db")
            seed = _title(
                db,
                rating_key="claw",
                tmdb_id=26774,
                title="The Blood on Satan's Claw",
                year=1971,
                genres=["Horror"],
                summary=self.LAST_JEDI_TRIVIA,
            )
            peer = _title(
                db,
                rating_key="mufasa",
                tmdb_id=762509,
                title="Mufasa: The Lion King",
                year=2024,
                genres=["Animation", "Family"],
                summary=self.RANDOM_TRIVIA,
            )
            db.set_neighbors(
                seed,
                enrich_neighbors_with_explanations(db, seed, [(peer, 0.88, 0.8)]),
            )
            db.replace_relations_of_types(
                {"neighbor": [(seed, peer, "neighbor", 0.88, "item_neighbors")]}
            )
            relations = list_relations_for_item(db, seed, limit=10)
            self.assertEqual(relations["items"], [])
            similar = neighbors_payload(db, seed, mode="similar", limit=8)
            surprising = neighbors_payload(db, seed, mode="surprising", limit=8)
            self.assertEqual(similar["items"], [])
            self.assertEqual(surprising["items"], [])
            blob = " ".join(
                str(item.get("plot_link") or "")
                for item in similar["items"] + surprising["items"]
            ).lower()
            self.assertNotIn("united states", blob)
            self.assertNotIn("principal photography", blob)
            self.assertNotIn("box office", blob)


class SimilarSurprisingDistinctRailTests(unittest.TestCase):
    def test_carbon_copy_surprising_rail_is_empty(self) -> None:
        similar = [{"rating_key": "a"}, {"rating_key": "b"}]
        self.assertEqual(surprising_items_if_distinct(similar, similar), [])

    def test_honest_peers_on_both_tabs_differ_in_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "rails.db")
            seed = _title(
                db,
                rating_key="seed",
                tmdb_id=1,
                title="Seed",
                genres=["Sci-Fi"],
                summary=BAKE_PLOT,
            )
            twin = _title(
                db,
                rating_key="twin",
                tmdb_id=2,
                title="Twin",
                genres=["Sci-Fi"],
                summary=SPY_PLOT,
            )
            odd = _title(
                db,
                rating_key="odd",
                tmdb_id=3,
                title="Odd",
                genres=["Romance"],
                summary=SPY_PLOT,
            )
            db.set_neighbors(
                seed,
                enrich_neighbors_with_explanations(
                    db, seed, [(twin, 0.99, 0.1), (odd, 0.9, 0.85)]
                ),
            )
            similar = neighbors_payload(db, seed, mode="similar", limit=5)
            surprising = neighbors_payload(db, seed, mode="surprising", limit=5)
            similar_keys = [item["rating_key"] for item in similar["items"]]
            surprising_keys = [item["rating_key"] for item in surprising["items"]]
            self.assertIn("twin", similar_keys)
            self.assertTrue(similar["items"])
            self.assertTrue(surprising["items"])
            self.assertNotEqual(similar_keys, surprising_keys)
            self.assertEqual(surprising_keys, ["odd"])
            self.assertNotIn("cult following", str(similar).lower())
            self.assertNotIn("united states", str(surprising).lower())


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


BLOOD_BEAST_PLOT = (
    "Night of the Blood Beast is a 1958 independently made American science-fiction "
    "horror film, produced and directed by Bernard L. Kowalski, co-produced by Gene "
    "Corman, and starring Michael Emmet, Ed Nelson, and Angela Greene. Distributed by "
    "American International Pictures. An astronaut crash lands and a previously used "
    "alien organism infects the crew."
)
CARS_3_PLOT = (
    "Lightning McQueen trains at a previously used racing facility before one last "
    "season around the oval with a new crew of trainers and a young prodigy."
)
GIANT_LEECHES_PLOT = (
    "Attack of the Giant Leeches is an American International Pictures horror film "
    "directed by Bernard Kowalski. Swamp creatures drag swimmers into underwater caves "
    "near a lonely marina."
)
HAUNTED_CAVE_PLOT = (
    "Beast from Haunted Cave was produced by Roger Corman. A gang hides in a cavern "
    "where a spider-like creature hunts them one by one after a robbery."
)
MAD_MAGICIAN_PLOT = (
    "A Victorian magician uses a crematorium to hide bodies and vows to kill again "
    "after his wife betrays him during a packed stage show."
)
COMEBACK_PLOT = (
    "A faded singer returns to a seaside hotel and the murders begin; the killer "
    "will kill again before the comeback concert in the ballroom."
)
APES_PLOT = (
    "An astronaut crash lands on a planet ruled by apes and discovers an underground "
    "city of mutated humans living beneath the ruins."
)


class ScreenshotPlotSubjectTests(unittest.TestCase):
    """iPhone For you screenshots — named NP, crew, or empty. Never junk grammar."""

    def test_previously_used_is_not_a_named_subject(self) -> None:
        link = specific_plot_link(
            seed_text=BLOOD_BEAST_PLOT,
            peer_text=CARS_3_PLOT,
            shelf_labels={"science fiction", "animation"},
        )
        self.assertIsNone(link)
        rebuilt = honest_plot_link(
            {
                "sentence": "Both stories turn on a previously used.",
                "terms": ["previously used"],
            }
        )
        self.assertIsNone(rebuilt)

    def test_american_international_and_kowalski_are_not_plot_subjects(self) -> None:
        link = specific_plot_link(
            seed_text=BLOOD_BEAST_PLOT,
            peer_text=GIANT_LEECHES_PLOT,
            shelf_labels={"horror", "science fiction", "bernard kowalski"},
        )
        self.assertIsNone(link)
        for terms, sentence in (
            (["american international"], "Both stories turn on an american international."),
            (["bernard kowalski"], "Both stories turn on a bernard kowalski."),
        ):
            rebuilt = honest_plot_link(
                {"sentence": sentence, "terms": terms},
                shelf_labels={"bernard kowalski"},
            )
            self.assertIsNone(rebuilt, sentence)

    def test_roger_corman_is_not_a_turn_on_subject(self) -> None:
        link = specific_plot_link(
            seed_text=BLOOD_BEAST_PLOT,
            peer_text=HAUNTED_CAVE_PLOT,
            shelf_labels={"horror", "roger corman"},
        )
        blob = str((link or {}).get("sentence") or "").lower()
        self.assertNotIn("roger corman", blob)
        self.assertNotIn("turn on a roger", blob)
        rebuilt = honest_plot_link(
            {
                "sentence": "Both stories turn on a roger corman.",
                "terms": ["roger corman"],
            },
            shelf_labels={"roger corman"},
        )
        self.assertIsNone(rebuilt)

    def test_kill_again_is_not_a_named_subject(self) -> None:
        link = specific_plot_link(
            seed_text=MAD_MAGICIAN_PLOT,
            peer_text=COMEBACK_PLOT,
            shelf_labels={"horror", "thriller"},
        )
        self.assertIsNone(link)
        rebuilt = honest_plot_link(
            {"sentence": "Both stories turn on a kill again.", "terms": ["kill again"]}
        )
        self.assertIsNone(rebuilt)

    def test_crash_lands_is_not_a_named_subject(self) -> None:
        link = specific_plot_link(
            seed_text=BLOOD_BEAST_PLOT,
            peer_text=APES_PLOT,
            shelf_labels={"science fiction"},
        )
        blob = str((link or {}).get("sentence") or "").lower()
        self.assertNotIn("crash lands", blob)
        rebuilt = honest_plot_link(
            {"sentence": "Both stories turn on crash lands.", "terms": ["crash lands"]}
        )
        self.assertIsNone(rebuilt)

    def test_real_noun_phrases_still_render(self) -> None:
        bakers = specific_plot_link(
            seed_text=BAKE_PLOT,
            peer_text=SPY_PLOT,
            shelf_labels={"reality", "thriller"},
        )
        self.assertIsNotNone(bakers)
        assert bakers is not None
        self.assertIn("amateur bakers", bakers["sentence"].lower())
        museum = specific_plot_link(
            seed_text=MUSEUM_PLOT,
            peer_text=MUSEUM_PEER_PLOT,
            shelf_labels={"reality", "documentary"},
        )
        self.assertIsNotNone(museum)
        assert museum is not None
        self.assertIn("museum exhibits", museum["sentence"].lower())

    def test_credit_names_do_not_mark_neighbors_explainable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "credits.db")
            seed = _title(
                db,
                rating_key="blood-beast",
                tmdb_id=10,
                title="Night of the Blood Beast",
                year=1958,
                genres=["Horror"],
                summary=BLOOD_BEAST_PLOT,
            )
            peer = _title(
                db,
                rating_key="haunted-cave",
                tmdb_id=11,
                title="Beast from Haunted Cave",
                year=1959,
                genres=["Horror"],
                summary=HAUNTED_CAVE_PLOT,
            )
            credit = [
                {
                    "tmdb_person_id": 2710,
                    "name": "Roger Corman",
                    "department": "Directing",
                    "job": "Director",
                    "billing_order": 0,
                }
            ]
            db.upsert_credits_for_item(seed, credit)
            db.upsert_credits_for_item(peer, credit)
            enriched = enrich_neighbors_with_explanations(db, seed, [(peer, 0.9, 0.8)])
            self.assertEqual(enriched[0][3], 0)
            blob = (enriched[0][4] or "").lower()
            self.assertNotIn("roger corman", blob)
            self.assertNotIn("previously used", blob)


class InfoboxStripTests(unittest.TestCase):
    def test_directed_by_and_studio_trailers_are_not_tokenized_as_subjects(self) -> None:
        seed = (
            "A swamp siege. Directed by Bernard Kowalski. Starring Michael Emmet. "
            "Distributed by American International Pictures. Produced by Roger Corman."
        )
        peer = (
            "A cavern siege. Directed by Bernard Kowalski. Starring Ed Nelson. "
            "American International Pictures released it. Produced by Roger Corman."
        )
        link = specific_plot_link(
            seed_text=seed,
            peer_text=peer,
            shelf_labels=set(),
        )
        blob = str((link or {}).get("sentence") or "").lower()
        self.assertNotIn("bernard kowalski", blob)
        self.assertNotIn("roger corman", blob)
        self.assertNotIn("american international", blob)
        self.assertNotIn("michael emmet", blob)
