"""Tests for persona_templates data model: CRUD, seed data, migration, visibility rules."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from curatorx.library.db import (
    BOOTSTRAP_OWNER_ID,
    BUILTIN_PERSONA_IDS,
    BUILTIN_PERSONA_SEEDS,
    Database,
)


class PersonaTemplateDbTests(unittest.TestCase):
    """Low-level database tests for the persona_templates table."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self._tmpdir.name) / "test.db")

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    # ── Seed data ──

    def test_builtin_presets_seeded_on_init(self) -> None:
        templates = self.db.list_persona_templates()
        builtin_ids = {t["id"] for t in templates if t["visibility"] == "builtin"}
        self.assertEqual(builtin_ids, BUILTIN_PERSONA_IDS)

    def test_builtin_count_matches_seeds(self) -> None:
        templates = self.db.list_persona_templates()
        builtins = [t for t in templates if t["visibility"] == "builtin"]
        self.assertEqual(len(builtins), len(BUILTIN_PERSONA_SEEDS))

    def test_builtin_slider_values(self) -> None:
        for seed in BUILTIN_PERSONA_SEEDS:
            with self.subTest(seed["id"]):
                template = self.db.get_persona_template(str(seed["id"]))
                self.assertIsNotNone(template)
                self.assertEqual(template["name"], seed["name"])
                self.assertAlmostEqual(template["val_bro_prof"], float(seed["val_bro_prof"]))
                self.assertAlmostEqual(template["val_depth"], float(seed["val_depth"]))
                self.assertAlmostEqual(template["val_obscurity"], float(seed["val_obscurity"]))
                self.assertAlmostEqual(template["val_verbosity"], float(seed["val_verbosity"]))
                self.assertAlmostEqual(template["val_formality"], float(seed["val_formality"]))

    def test_builtin_has_seven_slider_dimensions(self) -> None:
        template = self.db.get_persona_template("classic-curator")
        self.assertIsNotNone(template)
        for key in (
            "val_bro_prof", "val_dipl_snark", "val_pass_auto",
            "val_depth", "val_obscurity", "val_verbosity", "val_formality",
        ):
            self.assertIn(key, template)
            self.assertIsInstance(template[key], float)

    # ── CRUD ──

    def test_create_shared_template(self) -> None:
        created = self.db.create_persona_template(
            template_id="test-shared",
            name="Test Shared",
            visibility="shared",
            owner_user_id=BOOTSTRAP_OWNER_ID,
            val_bro_prof=0.7,
            val_depth=0.9,
        )
        self.assertEqual(created["id"], "test-shared")
        self.assertEqual(created["name"], "Test Shared")
        self.assertEqual(created["visibility"], "shared")
        self.assertAlmostEqual(created["val_bro_prof"], 0.7)
        self.assertAlmostEqual(created["val_depth"], 0.9)
        self.assertAlmostEqual(created["val_obscurity"], 0.5)

    def test_create_private_template(self) -> None:
        created = self.db.create_persona_template(
            template_id="test-private",
            name="My Secret",
            visibility="private",
            owner_user_id="user-abc",
        )
        self.assertEqual(created["visibility"], "private")
        self.assertEqual(created["owner_user_id"], "user-abc")

    def test_get_persona_template(self) -> None:
        template = self.db.get_persona_template("classic-curator")
        self.assertIsNotNone(template)
        self.assertEqual(template["name"], "Classic Curator")

    def test_get_nonexistent_returns_none(self) -> None:
        self.assertIsNone(self.db.get_persona_template("no-such-template"))

    def test_update_custom_template(self) -> None:
        self.db.create_persona_template(
            template_id="editable",
            name="Before",
            visibility="shared",
            owner_user_id=BOOTSTRAP_OWNER_ID,
        )
        updated = self.db.update_persona_template(
            "editable",
            name="After",
            val_depth=0.8,
        )
        self.assertEqual(updated["name"], "After")
        self.assertAlmostEqual(updated["val_depth"], 0.8)

    def test_update_builtin_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.db.update_persona_template("classic-curator", name="Nope")

    def test_delete_custom_template(self) -> None:
        self.db.create_persona_template(
            template_id="deletable",
            name="Deletable",
            visibility="shared",
            owner_user_id=BOOTSTRAP_OWNER_ID,
        )
        self.assertTrue(self.db.delete_persona_template("deletable"))
        self.assertIsNone(self.db.get_persona_template("deletable"))

    def test_delete_builtin_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.db.delete_persona_template("classic-curator")

    def test_delete_nonexistent_returns_false(self) -> None:
        self.assertFalse(self.db.delete_persona_template("no-such"))

    # ── Visibility rules ──

    def test_list_without_user_shows_builtin_and_shared(self) -> None:
        self.db.create_persona_template(
            template_id="shared-1", name="Shared", visibility="shared",
            owner_user_id=BOOTSTRAP_OWNER_ID,
        )
        self.db.create_persona_template(
            template_id="priv-1", name="Private", visibility="private",
            owner_user_id="user-x",
        )
        templates = self.db.list_persona_templates()
        ids = {t["id"] for t in templates}
        self.assertIn("classic-curator", ids)
        self.assertIn("shared-1", ids)
        self.assertNotIn("priv-1", ids)

    def test_list_with_owner_shows_own_private(self) -> None:
        self.db.create_persona_template(
            template_id="priv-mine", name="Mine", visibility="private",
            owner_user_id="user-a",
        )
        self.db.create_persona_template(
            template_id="priv-other", name="Other", visibility="private",
            owner_user_id="user-b",
        )
        templates = self.db.list_persona_templates(user_id="user-a")
        ids = {t["id"] for t in templates}
        self.assertIn("priv-mine", ids)
        self.assertNotIn("priv-other", ids)

    # ── Thread persona ──

    def test_set_and_get_thread_persona(self) -> None:
        self.db.ensure_chat_session("sess-1", "general")
        self.db.set_thread_persona("sess-1", "classic-curator")
        self.assertEqual(self.db.get_thread_persona_id("sess-1"), "classic-curator")

    def test_create_thread_with_persona(self) -> None:
        thread = self.db.create_chat_thread(
            "sess-2", persona_id="blunt-archivist",
        )
        self.assertEqual(thread["persona_id"], "blunt-archivist")

    def test_thread_summary_includes_persona_id(self) -> None:
        self.db.create_chat_thread("sess-3", persona_id="academic-critic")
        thread = self.db.get_chat_thread("sess-3")
        self.assertIsNotNone(thread)
        self.assertEqual(thread["persona_id"], "academic-critic")

    def test_thread_without_persona_has_none(self) -> None:
        self.db.create_chat_thread("sess-4")
        thread = self.db.get_chat_thread("sess-4")
        self.assertIsNone(thread["persona_id"])

    # ── User default persona ──

    def test_set_user_default_persona(self) -> None:
        self.db.set_user_default_persona(BOOTSTRAP_OWNER_ID, "night-owl-host")
        result = self.db.get_user_default_persona_id(BOOTSTRAP_OWNER_ID)
        self.assertEqual(result, "night-owl-host")

    def test_user_default_none_initially(self) -> None:
        result = self.db.get_user_default_persona_id(BOOTSTRAP_OWNER_ID)
        self.assertIsNone(result)

    # ── Migration: legacy persona to template ──

    def test_legacy_custom_persona_migrated(self) -> None:
        self.db.upsert_persona(val_bro_prof=0.8, val_dipl_snark=0.3)
        db2 = Database(self.db.path)
        template = db2.get_persona_template("migrated-persona")
        self.assertIsNotNone(template)
        self.assertEqual(template["visibility"], "shared")
        self.assertAlmostEqual(template["val_bro_prof"], 0.8)

    def test_default_persona_not_migrated(self) -> None:
        template = self.db.get_persona_template("migrated-persona")
        self.assertIsNone(template)


if __name__ == "__main__":
    unittest.main()
