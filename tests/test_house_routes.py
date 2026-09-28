"""Owner house letter HTTP routes."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.library.admin_execution import reset_admin_execution_for_tests


class HouseRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        reset_admin_execution_for_tests()
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        reset_admin_execution_for_tests()
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_letter_and_diary_are_owner_readable(self) -> None:
        letter = self.client.get("/api/admin/house/letter")
        self.assertEqual(letter.status_code, 200, letter.text)
        payload = letter.json()
        self.assertEqual(payload["title"], "A letter about the house")
        self.assertIn("paragraphs", payload)
        self.assertIn("stats", payload)

        diary = self.client.get("/api/admin/house/trust-diary")
        self.assertEqual(diary.status_code, 200, diary.text)
        self.assertIn("entries", diary.json())

        gifts = self.client.get("/api/admin/house/gifts")
        self.assertEqual(gifts.status_code, 200, gifts.text)
        self.assertEqual(gifts.json()["pending_count"], 0)

        preview = self.client.get("/api/admin/house/seasonal-preview")
        self.assertEqual(preview.status_code, 200, preview.text)
        self.assertIn("rails", preview.json())
