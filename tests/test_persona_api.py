"""Tests for persona template API endpoints, auth rules, and chat integration."""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from curatorx.library.db import BUILTIN_PERSONA_IDS


class PersonaApiTests(unittest.TestCase):
    """HTTP-level tests for /api/personas endpoints."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["CURATORX_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        import curatorx.web.jobs as jobs

        jobs._manager = None
        import curatorx.web.app as app_mod

        importlib.reload(app_mod)
        self.client = TestClient(app_mod.app)

    def tearDown(self) -> None:
        import curatorx.web.jobs as jobs

        jobs._manager = None
        os.environ.pop("CURATORX_SKIP_DOTENV", None)
        os.environ.pop("LLM_PROVIDER", None)
        self._tmpdir.cleanup()

    # ── GET /api/personas ──

    def test_list_personas_returns_builtins(self) -> None:
        resp = self.client.get("/api/personas")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsInstance(body, list)
        ids = {p["id"] for p in body}
        for builtin_id in BUILTIN_PERSONA_IDS:
            self.assertIn(builtin_id, ids)

    def test_list_personas_includes_seven_sliders(self) -> None:
        resp = self.client.get("/api/personas")
        body = resp.json()
        first = body[0]
        for key in (
            "val_bro_prof", "val_dipl_snark", "val_pass_auto",
            "val_depth", "val_obscurity", "val_verbosity", "val_formality",
        ):
            self.assertIn(key, first, f"Missing slider: {key}")

    # ── POST /api/personas ──

    def test_create_persona(self) -> None:
        resp = self.client.post("/api/personas", json={
            "name": "Test Persona",
            "val_bro_prof": 0.3,
            "val_depth": 0.9,
            "val_obscurity": 0.7,
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["name"], "Test Persona")
        self.assertAlmostEqual(body["val_bro_prof"], 0.3)
        self.assertAlmostEqual(body["val_depth"], 0.9)
        self.assertEqual(body["visibility"], "shared")

    def test_create_persona_validates_slider_range(self) -> None:
        resp = self.client.post("/api/personas", json={
            "name": "Bad Sliders",
            "val_bro_prof": 1.5,
        })
        self.assertEqual(resp.status_code, 422)

    def test_create_persona_requires_name(self) -> None:
        resp = self.client.post("/api/personas", json={
            "name": "",
        })
        self.assertEqual(resp.status_code, 422)

    # ── PUT /api/personas/{id} ──

    def test_update_custom_persona(self) -> None:
        create = self.client.post("/api/personas", json={"name": "Editable"})
        persona_id = create.json()["id"]

        resp = self.client.put(f"/api/personas/{persona_id}", json={
            "name": "Edited",
            "val_formality": 0.8,
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["name"], "Edited")
        self.assertAlmostEqual(resp.json()["val_formality"], 0.8)

    def test_update_builtin_rejected(self) -> None:
        resp = self.client.put("/api/personas/classic-curator", json={
            "name": "Hacked",
        })
        self.assertEqual(resp.status_code, 403)

    # ── DELETE /api/personas/{id} ──

    def test_delete_custom_persona(self) -> None:
        create = self.client.post("/api/personas", json={"name": "Deletable"})
        persona_id = create.json()["id"]

        resp = self.client.delete(f"/api/personas/{persona_id}")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["deleted"])

        listing = self.client.get("/api/personas").json()
        ids = {p["id"] for p in listing}
        self.assertNotIn(persona_id, ids)

    def test_delete_builtin_rejected(self) -> None:
        resp = self.client.delete("/api/personas/classic-curator")
        self.assertEqual(resp.status_code, 403)

    def test_delete_nonexistent_returns_404(self) -> None:
        resp = self.client.delete("/api/personas/no-such-id")
        self.assertEqual(resp.status_code, 404)

    # ── PUT /api/personas/{id}/default ──

    def test_set_default_persona(self) -> None:
        resp = self.client.put("/api/personas/classic-curator/default")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["default_persona_id"], "classic-curator")

        listing = self.client.get("/api/personas").json()
        defaults = [p for p in listing if p["is_default"]]
        self.assertEqual(len(defaults), 1)
        self.assertEqual(defaults[0]["id"], "classic-curator")

    def test_set_default_nonexistent_returns_404(self) -> None:
        resp = self.client.put("/api/personas/no-such/default")
        self.assertEqual(resp.status_code, 404)

    # ── Thread persona ──

    def test_create_thread_with_persona_id(self) -> None:
        resp = self.client.post("/api/chat/threads", json={
            "persona_id": "blunt-archivist",
        })
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["persona_id"], "blunt-archivist")

    def test_thread_list_includes_persona_id(self) -> None:
        self.client.post("/api/chat/threads", json={
            "persona_id": "night-owl-host",
        })
        resp = self.client.get("/api/chat/threads")
        self.assertEqual(resp.status_code, 200)
        threads = resp.json()
        self.assertTrue(len(threads) > 0)
        persona_threads = [t for t in threads if t.get("persona_id") == "night-owl-host"]
        self.assertTrue(len(persona_threads) > 0)


if __name__ == "__main__":
    unittest.main()
