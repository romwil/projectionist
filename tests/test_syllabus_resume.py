"""Scholar course resume pointer — next unfinished syllabus session."""

from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from projectionist.library.db import BOOTSTRAP_OWNER_ID, Database
from projectionist.syllabus import (
    build_syllabus_for_course,
    course_resume_pointer,
    mark_syllabus_session,
)


class CourseResumePointerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "projectionist.db")
        self.db.ensure_bootstrap_owner()
        list_id = uuid.uuid4().hex
        self.db.create_curated_list(
            list_id=list_id,
            user_id=None,
            name="Kurosawa Lab",
            description="Study the masters",
            list_kind="course",
        )
        for idx, title in enumerate(("Rashomon", "Seven Samurai", "Ikiru")):
            self.db.add_curated_list_item(
                item_id=uuid.uuid4().hex,
                list_id=list_id,
                user_id=None,
                tmdb_id=1000 + idx,
                tvdb_id=None,
                media_type="movie",
                title=title,
            )
        self.db.set_curated_list_visibility(list_id, visibility="published")
        self.list_id = list_id
        self.user_id = BOOTSTRAP_OWNER_ID

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_no_syllabus_returns_none(self) -> None:
        self.assertIsNone(
            course_resume_pointer(self.db, user_id=self.user_id, list_id=self.list_id)
        )

    def test_points_at_first_unfinished_session(self) -> None:
        built = build_syllabus_for_course(
            self.db, user_id=self.user_id, list_id=self.list_id
        )
        pointer = course_resume_pointer(
            self.db, user_id=self.user_id, list_id=self.list_id
        )
        self.assertIsNotNone(pointer)
        assert pointer is not None
        self.assertEqual(pointer["list_id"], self.list_id)
        self.assertEqual(pointer["course_name"], "Kurosawa Lab")
        self.assertEqual(pointer["session_id"], built["sessions"][0]["id"])
        self.assertFalse(pointer["completed"])
        self.assertIn("Resume", pointer["resume_label"])
        self.assertIn(built["sessions"][0]["title"], pointer["resume_label"])
        self.assertIn("multi-session syllabus", pointer["chat_prompt"])
        self.assertGreaterEqual(pointer["remaining_sessions"], 2)

    def test_skips_completed_sessions(self) -> None:
        built = build_syllabus_for_course(
            self.db, user_id=self.user_id, list_id=self.list_id
        )
        first = built["sessions"][0]
        mark_syllabus_session(
            self.db,
            user_id=self.user_id,
            session_id=first["id"],
            completed=True,
            chat_session_id="chat-session-1",
        )
        pointer = course_resume_pointer(self.db, user_id=self.user_id)
        self.assertIsNotNone(pointer)
        assert pointer is not None
        self.assertEqual(pointer["session_id"], built["sessions"][1]["id"])
        self.assertFalse(pointer["completed"])
        self.assertEqual(pointer["remaining_sessions"], len(built["sessions"]) - 1)

    def test_finished_course_points_at_completion(self) -> None:
        built = build_syllabus_for_course(
            self.db, user_id=self.user_id, list_id=self.list_id
        )
        for session in built["sessions"]:
            mark_syllabus_session(
                self.db,
                user_id=self.user_id,
                session_id=session["id"],
                completed=True,
            )
        pointer = course_resume_pointer(
            self.db, user_id=self.user_id, list_id=self.list_id
        )
        self.assertIsNotNone(pointer)
        assert pointer is not None
        self.assertTrue(pointer["completed"])
        self.assertEqual(pointer["remaining_sessions"], 0)
        self.assertIn("Finished", pointer["resume_label"])
        self.assertIn("Kurosawa Lab", pointer["resume_label"])
