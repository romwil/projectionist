"""SEC-008 / SEC-010: the container owner passcode locks a fresh install.

A fresh data directory serves only GET /api/health, GET /api/ready, and the
lock page until PROJECTIONIST_OWNER_PASSWORD is entered. Ready is a probe,
not the app. A data directory that already has an owner boots straight in.
"""

from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.library.db import Database
from projectionist.web.auth import _hash_password, has_real_owner
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import clear_session_secret_cache

_PASSCODE = "correct-horse"


def _plant_owner(data_dir: str) -> None:
    database = Database(Path(data_dir) / "projectionist.db")
    try:
        database.create_local_user(
            user_id="local-existing-owner",
            display_name="Ada",
            password_hash=_hash_password("already-set-pw"),
            role="owner",
        )
    finally:
        database._write_serializer.shutdown(timeout=5.0)


class _LockCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-setup-lock-session-secret-xx"
        os.environ["HOST"] = "0.0.0.0"
        os.environ.pop("PROJECTIONIST_SETUP_STATE", None)
        os.environ.pop("PROJECTIONIST_OWNER_PASSWORD", None)
        os.environ.pop("PROJECTIONIST_OWNER_USERNAME", None)
        clear_session_secret_cache()
        clear_rate_limits()
        self.app_mod = None
        self.client = None

    def tearDown(self) -> None:
        if self.client is not None:
            self.client.close()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in (
            "PROJECTIONIST_SKIP_DOTENV",
            "LLM_PROVIDER",
            "PROJECTIONIST_SESSION_SECRET",
            "DATA_DIR",
            "HOST",
            "PROJECTIONIST_SETUP_STATE",
            "PROJECTIONIST_OWNER_PASSWORD",
            "PROJECTIONIST_OWNER_USERNAME",
        ):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def _boot(self) -> TestClient:
        if self.client is not None:
            self.client.close()
            self.client = None
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self.client = TestClient(app_mod.app, client=("192.168.1.20", 43210))
        return self.client


class FreshInstallLockTests(_LockCase):
    def test_fresh_data_dir_serves_only_health_until_passcode(self) -> None:
        client = self._boot()
        self.app_mod.app.state.ready = True
        health = client.get("/api/health")
        self.assertEqual(health.status_code, 200, health.text)
        self.assertEqual(health.json().get("status"), "ok")
        ready = client.get("/api/ready")
        self.assertEqual(ready.status_code, 200, ready.text)
        self.assertEqual(ready.json().get("status"), "ready")
        self.assertNotIn("items", ready.json())

        blocked = (
            ("GET", "/api/features"),
            ("GET", "/api/settings"),
            ("GET", "/api/auth/me"),
            ("GET", "/api/chat/threads"),
            ("GET", "/api/library/query?media_type=movie"),
            ("GET", "/api/setup/handshake"),
            ("POST", "/api/setup/commit"),
            ("POST", "/api/auth/local/login"),
            ("POST", "/api/auth/plex/pin"),
            ("GET", "/api/auth/oidc/authorize"),
        )
        for method, path in blocked:
            kwargs = {"json": {}} if method == "POST" else {}
            resp = client.request(method, path, **kwargs)
            self.assertNotEqual(
                resp.status_code, 200, f"{method} {path} -> {resp.status_code} {resp.text}"
            )
            if "application/json" in resp.headers.get("content-type", ""):
                body = resp.json()
                self.assertNotIn("items", body)
                self.assertNotIn("threads", body)
                self.assertNotIn("settings", body)

        from projectionist.web.jobs import get_job_manager

        self.assertFalse(has_real_owner(get_job_manager().db))

        page = client.get("/")
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn("setup-lock", page.text)
        self.assertIn("setup-lock-unset", page.text)
        self.assertIn("PROJECTIONIST_OWNER_PASSWORD", page.text)
        self.assertNotIn("setup-lock-passcode", page.text)
        login_page = client.get("/login")
        self.assertIn("setup-lock", login_page.text)

        os.environ["PROJECTIONIST_OWNER_PASSWORD"] = _PASSCODE
        form = client.get("/")
        self.assertIn("setup-lock-passcode", form.text)
        bad = client.post("/api/setup/unlock", json={"passcode": "not-the-passcode"})
        self.assertEqual(bad.status_code, 401, bad.text)
        self.assertEqual(client.get("/api/features").status_code, 404)
        self.assertEqual(client.get("/api/chat/threads").status_code, 404)

        good = client.post("/api/setup/unlock", json={"passcode": _PASSCODE})
        self.assertEqual(good.status_code, 200, good.text)
        self.assertTrue(good.json()["ok"])
        self.assertEqual(client.get("/api/setup/handshake").status_code, 200)
        ready = client.get("/api/ready")
        self.assertEqual(ready.status_code, 200, ready.text)
        self.assertNotEqual(client.get("/api/library/query?media_type=movie").status_code, 200)
        self.assertNotEqual(client.get("/api/settings").status_code, 200)
        self.assertNotEqual(client.get("/api/chat/threads").status_code, 200)
        raced = client.post(
            "/api/auth/local/login",
            json={"username": "eve", "password": "password123"},
        )
        self.assertNotEqual(raced.status_code, 200, raced.text)
        plex = client.post("/api/auth/plex/pin", json={})
        self.assertNotEqual(plex.status_code, 200, plex.text)
        oidc = client.get("/api/auth/oidc/authorize")
        self.assertNotEqual(oidc.status_code, 200, oidc.text)
        self.assertFalse(has_real_owner(get_job_manager().db))

        commit = client.post(
            "/api/setup/commit",
            json={
                "profile": "private",
                "username": "ada",
                "password": "password123",
                "plex_url": "http://plex.local:32400",
                "plex_token": "plex-token-value",
            },
        )
        self.assertEqual(commit.status_code, 200, commit.text)
        self.assertNotIn("plex-token-value", commit.text)
        self.assertTrue(commit.json()["plex_bound"])
        self.assertTrue(has_real_owner(get_job_manager().db))
        settings = self.app_mod._settings()
        self.assertEqual(settings.plex_url, "http://plex.local:32400")
        self.assertEqual(settings.plex_token, "plex-token-value")
        self.assertTrue(settings.features.multi_user_enabled)

        features = client.get("/api/features")
        self.assertEqual(features.status_code, 200, features.text)
        self.assertEqual(features.json()["setup_state"], "active")
        home = client.get("/")
        self.assertNotIn("setup-lock", home.text)

    def test_missing_owner_reopens_setup_with_the_same_passcode(self) -> None:
        _plant_owner(self._tmpdir.name)
        client = self._boot()
        self.assertNotIn("setup-lock", client.get("/").text)
        from projectionist.web.jobs import get_job_manager

        get_job_manager().db.delete_user("local-existing-owner")
        os.environ["PROJECTIONIST_OWNER_PASSWORD"] = _PASSCODE
        client = self._boot()
        page = client.get("/")
        self.assertEqual(page.status_code, 200, page.text)
        self.assertIn("setup-lock", page.text)
        self.assertIn("PROJECTIONIST_OWNER_PASSWORD", page.text)
        raced = client.post(
            "/api/auth/local/login",
            json={"username": "eve", "password": "password123"},
        )
        self.assertEqual(raced.status_code, 404, raced.text)
        self.assertFalse(has_real_owner(get_job_manager().db))
        unlock = client.post("/api/setup/unlock", json={"passcode": _PASSCODE})
        self.assertEqual(unlock.status_code, 200, unlock.text)
        self.assertEqual(client.get("/api/setup/handshake").status_code, 200)
        self.assertEqual(client.get("/api/library/query?media_type=movie").status_code, 404)
        self.assertFalse(has_real_owner(get_job_manager().db))


class ExistingOwnerLockTests(_LockCase):
    def test_existing_owner_boots_straight_into_the_app(self) -> None:
        _plant_owner(self._tmpdir.name)
        client = self._boot()
        health = client.get("/api/health")
        self.assertEqual(health.status_code, 200, health.text)
        home = client.get("/")
        self.assertEqual(home.status_code, 200, home.text)
        self.assertNotIn("setup-lock", home.text)
        features = client.get("/api/features")
        self.assertEqual(features.status_code, 200, features.text)
        self.assertNotEqual(features.json().get("setup_state"), "setup")
        library = client.get("/api/library/query?media_type=movie")
        self.assertEqual(library.status_code, 200, library.text)
        threads = client.get("/api/chat/threads")
        self.assertEqual(threads.status_code, 200, threads.text)
        from projectionist.web.jobs import get_job_manager

        self.assertTrue(has_real_owner(get_job_manager().db))


if __name__ == "__main__":
    unittest.main()
