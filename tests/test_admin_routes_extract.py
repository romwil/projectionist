"""Admin routes moved out of ``app.py`` keep their paths, owner gate, and status codes (ARCH-005)."""

from __future__ import annotations

import importlib
import json
import os
import re
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.web.auth import _hash_password
from projectionist.web.rate_limit import clear_rate_limits
from projectionist.web.session_tokens import (
    SESSION_COOKIE_NAME,
    clear_session_secret_cache,
    create_session_token,
)

APP_PY = Path(__file__).resolve().parents[1] / "projectionist" / "web" / "app.py"

# Ratchet: lower this when routes leave app.py. Never raise it.
APP_PY_ROUTE_DECORATOR_CAP = 113

MOVED_ROUTES = [
    ("GET", "/api/admin/grooming/actions"),
    ("POST", "/api/admin/grooming/actions/{action_id}/undo"),
    ("GET", "/api/admin/logs"),
    ("GET", "/api/admin/logs/stream"),
    ("GET", "/api/admin/scheduled-tasks"),
    ("POST", "/api/admin/scheduled-tasks/optimize-rates"),
    ("PUT", "/api/admin/scheduled-tasks/{name}"),
    ("POST", "/api/admin/scheduled-tasks/{name}/run"),
    ("GET", "/api/admin/scheduled-tasks/{name}/log"),
    ("GET", "/api/admin/scheduled-tasks/{name}/history"),
    ("GET", "/api/admin/scheduled-tasks/{name}/rate"),
    ("GET", "/api/admin/scheduled-tasks-log"),
    ("GET", "/api/admin/scheduled-tasks-history"),
    ("POST", "/api/admin/scheduled-tasks/{name}/reset"),
    ("GET", "/api/admin/telemetry/summary"),
    ("GET", "/api/admin/telemetry/events"),
    ("GET", "/api/admin/llm/usage"),
    ("GET", "/api/admin/llm/models"),
]


def _concrete(path: str) -> str:
    return path.replace("{action_id}", "no-such-action").replace("{name}", "no_such_task")


class AppPyFreezeTests(unittest.TestCase):
    def test_app_py_route_decorators_do_not_grow(self) -> None:
        source = APP_PY.read_text(encoding="utf-8")
        count = len(re.findall(r"^@app\.(get|post|put|patch|delete)\(", source, flags=re.M))
        self.assertLessEqual(
            count,
            APP_PY_ROUTE_DECORATOR_CAP,
            "New routes belong in a *_routes.py module (admin: owner_ops_routes.py), not app.py.",
        )

    def test_moved_routes_are_not_declared_in_app_py(self) -> None:
        source = APP_PY.read_text(encoding="utf-8")
        for method, path in MOVED_ROUTES:
            self.assertNotIn(f'@app.{method.lower()}("{path}"', source)


class AdminRoutesExtractApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["DATA_DIR"] = self._tmpdir.name
        os.environ["PROJECTIONIST_SKIP_DOTENV"] = "1"
        os.environ["LLM_PROVIDER"] = "ollama"
        os.environ["PROJECTIONIST_SESSION_SECRET"] = "test-admin-extract-secret"
        os.environ["PROJECTIONIST_SETUP_STATE"] = "active"
        Path(self._tmpdir.name, "settings.json").write_text(
            json.dumps(
                {
                    "features": {"multi_user_enabled": True},
                    "llm_provider": "ollama",
                    "auth": {"mode": "local", "plex_login_enabled": False, "local_login_enabled": True},
                }
            ),
            encoding="utf-8",
        )
        clear_session_secret_cache()
        clear_rate_limits()
        import projectionist.web.jobs as jobs

        jobs._manager = None
        import projectionist.web.app as app_mod

        importlib.reload(app_mod)
        self.app_mod = app_mod
        self._client_cm = TestClient(app_mod.app)
        self._client_cm.__enter__()
        db = jobs.get_job_manager().db
        for user_id, role in (("local-owner1", "owner"), ("local-member1", "member")):
            db.create_local_user(
                user_id=user_id,
                display_name=user_id,
                password_hash=_hash_password("password123"),
                role=role,
            )
        self.owner = TestClient(app_mod.app)
        self.owner.cookies.set(SESSION_COOKIE_NAME, create_session_token("local-owner1"))
        self.member = TestClient(app_mod.app)
        self.member.cookies.set(SESSION_COOKIE_NAME, create_session_token("local-member1"))

    def tearDown(self) -> None:
        import projectionist.web.jobs as jobs

        try:
            self._client_cm.__exit__(None, None, None)
        except Exception:
            pass
        jobs._manager = None
        clear_session_secret_cache()
        clear_rate_limits()
        for key in ("PROJECTIONIST_SKIP_DOTENV", "LLM_PROVIDER", "PROJECTIONIST_SESSION_SECRET", "PROJECTIONIST_SETUP_STATE"):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_moved_routes_live_in_owner_ops_routes(self) -> None:
        served = {}

        def walk(routes):
            for route in routes:
                inner = getattr(route, "original_router", None)
                if inner is not None:
                    walk(inner.routes)
                    continue
                for method in getattr(route, "methods", None) or ():
                    served[(method, getattr(route, "path", ""))] = route.endpoint.__module__

        walk(self.app_mod.app.routes)
        for key in MOVED_ROUTES:
            self.assertEqual(served.get(key), "projectionist.web.owner_ops_routes", key)

    def test_member_is_denied_every_moved_route(self) -> None:
        for method, path in MOVED_ROUTES:
            response = self.member.request(method, _concrete(path), json={} if method == "PUT" else None)
            self.assertEqual(response.status_code, 403, f"{method} {path}: {response.text}")

    def test_owner_status_codes_unchanged(self) -> None:
        expected = [
            ("GET", "/api/admin/grooming/actions", None, 200),
            ("POST", "/api/admin/grooming/actions/no-such-action/undo", None, 404),
            ("GET", "/api/admin/logs", None, 200),
            ("GET", "/api/admin/logs?level=nonsense", None, 400),
            ("GET", "/api/admin/logs/stream?level=nonsense", None, 400),
            ("GET", "/api/admin/scheduled-tasks", None, 200),
            ("POST", "/api/admin/scheduled-tasks/optimize-rates?dry_run=true", None, 200),
            ("PUT", "/api/admin/scheduled-tasks/no_such_task", {"enabled": False}, 404),
            ("PUT", "/api/admin/scheduled-tasks/taste_refresh", {"run_interval_seconds": 1}, 422),
            ("POST", "/api/admin/scheduled-tasks/no_such_task/run", None, 404),
            ("GET", "/api/admin/scheduled-tasks/no_such_task/log", None, 404),
            ("GET", "/api/admin/scheduled-tasks/no_such_task/history", None, 404),
            ("GET", "/api/admin/scheduled-tasks/no_such_task/rate", None, 404),
            ("GET", "/api/admin/scheduled-tasks-log", None, 200),
            ("GET", "/api/admin/scheduled-tasks-history", None, 200),
            ("POST", "/api/admin/scheduled-tasks/no_such_task/reset", None, 404),
            ("GET", "/api/admin/telemetry/summary", None, 200),
            ("GET", "/api/admin/telemetry/events", None, 200),
            ("GET", "/api/admin/llm/usage", None, 200),
        ]
        for method, url, body, status in expected:
            response = self.owner.request(method, url, json=body)
            self.assertEqual(response.status_code, status, f"{method} {url}: {response.text}")


if __name__ == "__main__":
    unittest.main()
