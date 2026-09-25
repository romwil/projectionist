"""Scholar walks — lineage, canon, map, compare, seminar, consented gaps."""

from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from projectionist.library.db import BOOTSTRAP_OWNER_ID, Database
from projectionist.reviews.store import save_review
from projectionist.syllabus import build_syllabus_for_course
from projectionist.syllabus.walks import (
    WALK_KIND_CANON,
    WALK_KIND_COMPARE,
    WALK_KIND_GAPS,
    WALK_KIND_LINEAGE,
    WALK_KIND_MAP,
    WALK_KIND_SEMINAR,
    build_scholar_walk,
    detect_walk_kind,
    normalize_walk_kind,
    scholar_walk_chat_prompt,
    walk_specialty_summary,
)


class ScholarWalkHelpersTests(unittest.TestCase):
    def test_normalizes_and_detects_kinds(self) -> None:
        self.assertEqual(normalize_walk_kind("compare-two-rated"), WALK_KIND_COMPARE)
        self.assertEqual(normalize_walk_kind("Silent seminar"), WALK_KIND_SEMINAR)
        self.assertEqual(detect_walk_kind("Walk the Kurosawa lineage"), WALK_KIND_LINEAGE)
        self.assertEqual(detect_walk_kind("Open a thematic map of New Wave"), WALK_KIND_MAP)
        self.assertIsNone(detect_walk_kind("What's good tonight?"))


class ScholarWalkBuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")
        self.db.ensure_bootstrap_owner()
        self.user_id = BOOTSTRAP_OWNER_ID
        self.list_id = uuid.uuid4().hex
        self.db.upsert_library_item(
            {
                "rating_key": "rk-rashomon",
                "media_type": "movie",
                "title": "Rashomon",
                "year": 1950,
                "tmdb_id": 1000,
                "directors": ["Akira Kurosawa"],
            }
        )
        self.db.create_curated_list(
            list_id=self.list_id,
            user_id=None,
            name="Kurosawa Lab",
            description="Study the masters",
            list_kind="course",
        )
        for idx, title in enumerate(("Rashomon", "Seven Samurai", "Ikiru", "High and Low")):
            self.db.add_curated_list_item(
                item_id=uuid.uuid4().hex,
                list_id=self.list_id,
                user_id=None,
                tmdb_id=1000 + idx,
                tvdb_id=None,
                media_type="movie",
                title=title,
            )
        self.db.set_curated_list_visibility(self.list_id, visibility="published")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_lineage_uses_course_and_library_with_walk_footnotes(self) -> None:
        walk = build_scholar_walk(
            self.db, user_id=self.user_id, kind="lineage", topic="Kurosawa"
        )
        self.assertTrue(walk["ok"])
        self.assertEqual(walk["kind"], WALK_KIND_LINEAGE)
        self.assertFalse(walk["public"])
        self.assertIn("influence", walk["why"].casefold())
        titles = [stop["title"] for stop in walk["stops"]]
        self.assertIn("Rashomon", titles)
        self.assertTrue(any(c["id"].startswith("lineage-") for c in walk["citations"]))
        self.assertIn("[^lineage-1]:", walk["chat_prompt"])
        self.assertIn("no public page", walk["chat_prompt"].casefold())

    def test_canon_marks_owned_stops(self) -> None:
        walk = build_scholar_walk(
            self.db, user_id=self.user_id, kind="canon", topic="Kurosawa"
        )
        self.assertTrue(walk["ok"])
        owned = [stop for stop in walk["stops"] if stop.get("owned")]
        missing = [stop for stop in walk["stops"] if stop.get("owned") is False]
        self.assertGreaterEqual(len(owned), 1)
        self.assertGreaterEqual(len(missing), 1)
        self.assertIn("Kurosawa Lab", walk["focus_note"])

    def test_map_has_three_regions(self) -> None:
        walk = build_scholar_walk(
            self.db, user_id=self.user_id, kind="map", topic="Kurosawa"
        )
        self.assertTrue(walk["ok"])
        regions = [stop["title"] for stop in walk["stops"]]
        self.assertIn("Origins", regions)
        self.assertTrue(any(c["id"].startswith("map-") for c in walk["citations"]))

    def test_compare_two_rated_uses_reviews(self) -> None:
        save_review(
            self.db,
            stars=5,
            title="Rashomon",
            media_type="movie",
            rating_key="rk-rashomon",
            tmdb_id=1000,
            review_text="Courtyard geometry.",
            user_id=self.user_id,
        )
        save_review(
            self.db,
            stars=4,
            title="Ikiru",
            media_type="movie",
            rating_key="rk-ikiru",
            tmdb_id=1002,
            review_text="A life still unused.",
            user_id=self.user_id,
        )
        walk = build_scholar_walk(
            self.db,
            user_id=self.user_id,
            kind="compare-two-rated",
            titles=("Rashomon", "Ikiru"),
        )
        self.assertTrue(walk["ok"])
        self.assertEqual(len(walk["stops"]), 2)
        self.assertIn("Rashomon", walk["compared_titles"])
        self.assertIn("5★", walk["stops"][0]["note"] + walk["stops"][1]["note"])
        self.assertIn("[^compare-1]:", walk["chat_prompt"])

    def test_compare_refuses_without_two_ratings(self) -> None:
        walk = build_scholar_walk(
            self.db, user_id=self.user_id, kind="compare_two_rated"
        )
        self.assertFalse(walk["ok"])
        self.assertIn("two titles", walk["message"].casefold())

    def test_silent_seminar_stays_private_and_invites_professor(self) -> None:
        walk = build_scholar_walk(
            self.db, user_id=self.user_id, kind="silent seminar", topic="Kurosawa"
        )
        self.assertTrue(walk["ok"])
        self.assertFalse(walk["public"])
        self.assertEqual(walk["village"]["lead"], "The Professor")
        self.assertIn("seminar-", walk["citations"][0]["id"])
        self.assertIn("silent seminar", walk["chat_prompt"].casefold())

    def test_gap_reading_list_waits_for_confirm(self) -> None:
        proposed = build_scholar_walk(
            self.db, user_id=self.user_id, kind="gap reading list", topic="Kurosawa"
        )
        self.assertTrue(proposed["needs_confirm"])
        self.assertFalse(proposed["ok"])
        self.assertEqual(proposed["stops"], [])
        self.assertGreaterEqual(proposed["proposed_count"], 1)
        self.assertIn("does not request", proposed["confirm_message"].casefold())
        self.assertIn("confirm", proposed["chat_prompt"].casefold())

        confirmed = build_scholar_walk(
            self.db,
            user_id=self.user_id,
            kind="gap_reading_list",
            topic="Kurosawa",
            confirm=True,
        )
        self.assertTrue(confirmed["ok"])
        self.assertFalse(confirmed["needs_confirm"])
        self.assertTrue(all(stop.get("owned") is False for stop in confirmed["stops"]))
        self.assertNotIn("Rashomon", [stop["title"] for stop in confirmed["stops"]])
        self.assertIn("[^gap-1]:", confirmed["chat_prompt"])

    def test_walk_attaches_syllabus_resume_pointer(self) -> None:
        built = build_syllabus_for_course(
            self.db, user_id=self.user_id, list_id=self.list_id
        )
        walk = build_scholar_walk(
            self.db, user_id=self.user_id, kind="lineage", topic="Kurosawa"
        )
        self.assertIn("resume", walk)
        self.assertEqual(walk["resume"]["session_id"], built["sessions"][0]["id"])
        self.assertIn("Resume", walk["resume"]["resume_label"])
        self.assertIn(walk["resume"]["resume_label"], walk["chat_prompt"])

    def test_specialty_summary_is_compact_and_private(self) -> None:
        walk = build_scholar_walk(
            self.db, user_id=self.user_id, kind="canon", topic="Kurosawa"
        )
        summary = walk_specialty_summary(walk)
        self.assertEqual(summary["kind"], WALK_KIND_CANON)
        self.assertFalse(summary["public"])
        self.assertTrue(summary["stop_titles"])
        prompt = scholar_walk_chat_prompt(walk)
        self.assertIn("Confirm before any fleet", prompt)


if __name__ == "__main__":
    unittest.main()
