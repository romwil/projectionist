"""Tests for persona prompt assembly and presets."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.library.db import Database
from projectionist.persona import (
    CURATOR_NAME_PLACEHOLDER,
    build_assembled_persona_prompt,
    build_behavioral_prompt_from_sliders,
    build_persona_prompt,
    build_rendered_behavioral_prompt,
    derive_persona_mode,
    format_review_prompt,
    get_preset,
    persona_ui_for,
    slider_band,
    substitute_curator_name,
)
from projectionist.persona.presets import PERSONA_PRESETS, welcome_greeting_for


class PersonaPromptTests(unittest.TestCase):
    def test_derive_persona_mode_from_override(self) -> None:
        self.assertEqual(derive_persona_mode({"persona_prompt_override": "Custom tone"}), "custom")
        self.assertEqual(derive_persona_mode({"persona_prompt_override": ""}), "sliders")
        self.assertEqual(derive_persona_mode({}), "sliders")

    def test_slider_band_thresholds(self) -> None:
        self.assertEqual(slider_band(0.0), "low")
        self.assertEqual(slider_band(0.34), "low")
        self.assertEqual(slider_band(0.35), "mid")
        self.assertEqual(slider_band(0.5), "mid")
        self.assertEqual(slider_band(0.65), "mid")
        self.assertEqual(slider_band(0.66), "high")
        self.assertEqual(slider_band(1.0), "high")

    def test_build_persona_prompt_concatenates_identity_and_behavior(self) -> None:
        persona = {
            "curator_name": "Atlas",
            "persona_identity": "I am a noir obsessive.",
            "val_bro_prof": 0.5,
            "val_dipl_snark": 0.5,
            "val_pass_auto": 0.5,
        }
        prompt = build_persona_prompt(persona)
        self.assertIn("I am a noir obsessive.", prompt)
        self.assertIn("Atlas", prompt)
        self.assertIn("Vocabulary", prompt)
        self.assertIn("Library curation:", prompt)
        self.assertIn("could not confirm ownership", prompt)
        self.assertIn("Review memory:", prompt)
        self.assertIn("get_user_reviews", prompt)

    def test_slider_template_uses_name_placeholder(self) -> None:
        template = build_behavioral_prompt_from_sliders(
            {"val_bro_prof": 0.5, "val_dipl_snark": 0.5, "val_pass_auto": 0.5}
        )
        self.assertIn(CURATOR_NAME_PLACEHOLDER, template)
        self.assertNotIn("Curator", template)

    def test_low_vocabulary_band_uses_casual_guidance(self) -> None:
        prompt = build_behavioral_prompt_from_sliders(
            {"val_bro_prof": 0.1, "val_dipl_snark": 0.5, "val_pass_auto": 0.5}
        )
        self.assertIn("casual film-fan", prompt)
        self.assertIn("bro", prompt.lower())

    def test_high_directness_band_uses_snark_guidance(self) -> None:
        prompt = build_behavioral_prompt_from_sliders(
            {"val_bro_prof": 0.5, "val_dipl_snark": 0.9, "val_pass_auto": 0.5}
        )
        self.assertIn("lead with conclusions", prompt.lower())
        self.assertIn("headline first", prompt.lower())

    def test_high_initiative_band_uses_autonomous_guidance(self) -> None:
        prompt = build_behavioral_prompt_from_sliders(
            {"val_bro_prof": 0.5, "val_dipl_snark": 0.5, "val_pass_auto": 0.95}
        )
        self.assertIn("autonomous", prompt.lower())
        self.assertIn("concrete next steps", prompt.lower())

    def test_preset_includes_archetype_anchor_and_behavioral_anchor(self) -> None:
        preset = get_preset("classic-curator")
        assert preset is not None
        prompt = build_behavioral_prompt_from_sliders(
            {
                "persona_preset_id": preset.id,
                "val_bro_prof": preset.val_bro_prof,
                "val_dipl_snark": preset.val_dipl_snark,
                "val_pass_auto": preset.val_pass_auto,
            }
        )
        self.assertIn("Classic Curator", prompt)
        self.assertIn(preset.behavioral_anchor, prompt)

    def test_substitute_curator_name_renders_placeholder(self) -> None:
        rendered = substitute_curator_name(f"You are {CURATOR_NAME_PLACEHOLDER}.", "Marcus")
        self.assertEqual(rendered, "You are Marcus.")

    def test_name_change_preserves_slider_template(self) -> None:
        base = {"val_bro_prof": 0.5, "val_dipl_snark": 0.5, "val_pass_auto": 0.5}
        template = build_behavioral_prompt_from_sliders(base)
        rendered_a = build_rendered_behavioral_prompt({**base, "curator_name": "Curator"})
        rendered_b = build_rendered_behavioral_prompt({**base, "curator_name": "Marcus"})
        self.assertEqual(template, build_behavioral_prompt_from_sliders({**base, "curator_name": "Marcus"}))
        self.assertIn("Curator", rendered_a)
        self.assertIn("Marcus", rendered_b)
        self.assertNotIn("Curator", rendered_b)

    def test_custom_override_with_placeholder_updates_name(self) -> None:
        persona = {
            "curator_name": "Marcus",
            "persona_prompt_override": f"Always greet as {CURATOR_NAME_PLACEHOLDER}.",
        }
        rendered = build_rendered_behavioral_prompt(persona)
        self.assertIn("Marcus", rendered)
        self.assertNotIn(CURATOR_NAME_PLACEHOLDER, rendered)

    def test_override_replaces_slider_behavioral_text(self) -> None:
        persona = {
            "curator_name": "Atlas",
            "persona_identity": "Core identity stays.",
            "persona_prompt_override": "Always speak in haiku.",
            "val_bro_prof": 0.9,
            "val_dipl_snark": 0.1,
            "val_pass_auto": 0.5,
        }
        prompt = build_persona_prompt(persona)
        self.assertIn("Core identity stays.", prompt)
        self.assertIn("Always speak in haiku.", prompt)
        self.assertNotIn("Vocabulary", prompt)

    def test_archetype_presets_exist(self) -> None:
        self.assertEqual(len(PERSONA_PRESETS), 5)
        for preset_id in (
            "classic-curator",
            "blunt-archivist",
            "enthusiastic-scout",
            "academic-critic",
            "night-owl-host",
        ):
            preset = get_preset(preset_id)
            assert preset is not None
            self.assertTrue(preset.identity_blurb)
            self.assertTrue(preset.behavioral_anchor)
            self.assertTrue(preset.tagline)
            self.assertTrue(preset.composer_placeholders)
            self.assertTrue(preset.welcome_greeting)
            self.assertTrue(preset.welcome_starters)
            self.assertIn("near_complete", preset.review_prompt_templates)
            self.assertTrue(preset.accent_hue)

    def test_persona_ui_for_includes_immersion_fields(self) -> None:
        ui = persona_ui_for("blunt-archivist", "Flemming")
        self.assertIn("Flemming", ui["welcome_greeting"])
        self.assertGreater(len(ui["composer_placeholders"]), 0)
        self.assertGreater(len(ui["welcome_starters"]), 0)
        self.assertIn("near_complete", ui["review_prompt_templates"])
        self.assertTrue(str(ui["accent_hue"]).startswith("hsl("))

    def test_format_review_prompt_substitutes_title_and_pct(self) -> None:
        message = format_review_prompt(
            "enthusiastic-scout",
            "near_complete",
            curator_name="Scout",
            title="Dune",
            completion_pct=87.4,
        )
        self.assertIn("Dune", message)
        self.assertIn("87", message)

    def test_welcome_greeting_uses_curator_name(self) -> None:
        greeting = welcome_greeting_for("classic-curator", "Atlas")
        self.assertIn("Atlas", greeting)
        self.assertNotIn("{curator_name}", greeting)

    def test_apply_preset_via_db(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(Path(tmp) / "test.db")
            preset = get_preset("enthusiastic-scout")
            assert preset is not None
            row = db.upsert_persona(
                persona_preset_id=preset.id,
                val_bro_prof=preset.val_bro_prof,
                val_dipl_snark=preset.val_dipl_snark,
                val_pass_auto=preset.val_pass_auto,
                persona_identity=preset.identity_blurb,
            )
            self.assertEqual(float(row["val_bro_prof"]), preset.val_bro_prof)
            self.assertEqual(str(row["persona_preset_id"]), preset.id)

    def test_clear_override_regenerates_behavioral_prompt(self) -> None:
        persona = {
            "curator_name": "Curator",
            "persona_prompt_override": "Custom only.",
            "val_bro_prof": 0.2,
            "val_dipl_snark": 0.8,
            "val_pass_auto": 0.4,
        }
        cleared = {**persona, "persona_prompt_override": None}
        behavioral = build_behavioral_prompt_from_sliders(cleared)
        self.assertIn("casual film-fan", behavioral)
        self.assertIn("lead with conclusions", behavioral.lower())

    def test_assembled_prompt_matches_identity_plus_behavior(self) -> None:
        persona = {
            "curator_name": "Morgan",
            "persona_identity": "Line one.",
            "val_bro_prof": 0.5,
            "val_dipl_snark": 0.5,
            "val_pass_auto": 0.5,
        }
        assembled = build_assembled_persona_prompt(persona)
        self.assertTrue(assembled.startswith("Line one."))
        self.assertIn("Morgan", assembled)


class PersonaApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("PROJECTIONIST_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    def test_persona_payload_includes_new_fields(self) -> None:
        resp = self.client.get("/api/persona")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        for key in (
            "persona_identity",
            "persona_preset_id",
            "persona_prompt_override",
            "persona_mode",
            "behavioral_prompt",
            "assembled_prompt",
            "persona_ui",
        ):
            self.assertIn(key, body)
        self.assertEqual(body["persona_mode"], "sliders")
        self.assertIn("Library curation:", body["behavioral_prompt"])
        self.assertIn("welcome_greeting", body["persona_ui"])
        self.assertIn("composer_placeholders", body["persona_ui"])
        self.assertIn("Review memory:", body["assembled_prompt"])

    def test_persona_presets_list(self) -> None:
        resp = self.client.get("/api/persona/presets")
        self.assertEqual(resp.status_code, 200)
        presets = resp.json()
        self.assertEqual(len(presets), 5)
        ids = {item["id"] for item in presets}
        self.assertEqual(
            ids,
            {
                "classic-curator",
                "blunt-archivist",
                "enthusiastic-scout",
                "academic-critic",
                "night-owl-host",
            },
        )
        classic = next(item for item in presets if item["id"] == "classic-curator")
        self.assertIn("tagline", classic)
        self.assertIn("behavioral_anchor", classic)
        self.assertTrue(classic["behavioral_anchor"])
        self.assertIn("composer_placeholders", classic)
        self.assertIn("welcome_greeting", classic)
        self.assertIn("accent_hue", classic)
        self.assertEqual(classic["nickname"], "The Steward")
        professor = next(item for item in presets if item["id"] == "academic-critic")
        self.assertEqual(professor["nickname"], "The Professor")

    def test_custom_override_blocks_slider_change_until_confirmed(self) -> None:
        put = self.client.put(
            "/api/persona",
            json={"persona_prompt_override": "Speak like a pirate."},
        )
        self.assertEqual(put.status_code, 200)
        self.assertEqual(put.json()["persona_mode"], "custom")

        conflict = self.client.put("/api/persona", json={"val_bro_prof": 0.9})
        self.assertEqual(conflict.status_code, 409)

        cleared = self.client.put(
            "/api/persona",
            json={"val_bro_prof": 0.9, "clear_persona_override": True},
        )
        self.assertEqual(cleared.status_code, 200)
        self.assertEqual(cleared.json()["persona_mode"], "sliders")
        self.assertIn("professorial", cleared.json()["behavioral_prompt"].lower())

    def test_apply_preset_endpoint(self) -> None:
        resp = self.client.put("/api/persona", json={"apply_preset": "academic-critic"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["persona_preset_id"], "academic-critic")
        self.assertGreater(body["val_bro_prof"], 0.85)
        self.assertIn("Academic Critic", body["behavioral_prompt"])

    def test_apply_preset_preserves_existing_identity(self) -> None:
        custom_identity = "My custom identity stays."
        seeded = self.client.put("/api/persona", json={"persona_identity": custom_identity})
        self.assertEqual(seeded.status_code, 200)

        applied = self.client.put("/api/persona", json={"apply_preset": "night-owl-host"})
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(applied.json()["persona_identity"], custom_identity)

    def test_persona_preview_endpoint(self) -> None:
        resp = self.client.get("/api/persona/preview", params={"persona_identity": "Preview identity"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("Preview identity", body["assembled_prompt"])

    def test_curator_name_only_update_preserves_slider_prompt(self) -> None:
        baseline = self.client.get("/api/persona").json()
        self.assertEqual(baseline["persona_mode"], "sliders")
        slider_template = build_behavioral_prompt_from_sliders(baseline)

        renamed = self.client.put("/api/persona", json={"curator_name": "Marcus"})
        self.assertEqual(renamed.status_code, 200)
        body = renamed.json()
        self.assertEqual(body["curator_name"], "Marcus")
        self.assertEqual(body["persona_mode"], "sliders")
        self.assertIn("Marcus", body["behavioral_prompt"])
        self.assertIn("Marcus", body["assembled_prompt"])
        self.assertEqual(
            build_behavioral_prompt_from_sliders({**baseline, "curator_name": "Marcus"}),
            slider_template,
        )

    def test_curator_name_only_update_preserves_custom_override(self) -> None:
        custom = self.client.put(
            "/api/persona",
            json={"persona_prompt_override": f"Speak as {CURATOR_NAME_PLACEHOLDER}, always."},
        )
        self.assertEqual(custom.status_code, 200)
        self.assertEqual(custom.json()["persona_mode"], "custom")

        renamed = self.client.put("/api/persona", json={"curator_name": "The Curator"})
        self.assertEqual(renamed.status_code, 200)
        body = renamed.json()
        self.assertEqual(body["persona_mode"], "custom")
        self.assertIn("The Curator", body["behavioral_prompt"])
        self.assertNotIn(CURATOR_NAME_PLACEHOLDER, body["behavioral_prompt"])


if __name__ == "__main__":
    unittest.main()
