"""Library + chat routes live in dedicated modules, not app.py."""

from __future__ import annotations

import ast
import importlib
import inspect
import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from projectionist.library.admin_execution import reset_admin_execution_for_tests

WEB = Path(__file__).resolve().parents[1] / "projectionist" / "web"


def _module_imports_app(path: Path) -> bool:
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "projectionist.web.app" or alias.name.startswith(
                    "projectionist.web.app."
                ):
                    return True
        if isinstance(node, ast.ImportFrom) and node.module == "projectionist.web.app":
            return True
    return False


class LibraryChatCarveTests(unittest.TestCase):
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
        for key in ("PROJECTIONIST_SKIP_DOTENV", "LLM_PROVIDER", "DATA_DIR"):
            os.environ.pop(key, None)
        self._tmpdir.cleanup()

    def test_route_modules_do_not_import_app(self) -> None:
        self.assertFalse(_module_imports_app(WEB / "library_routes.py"))
        self.assertFalse(_module_imports_app(WEB / "chat_routes.py"))

    def test_register_factories_match_house_pattern(self) -> None:
        from projectionist.web.chat_routes import register_chat_routes
        from projectionist.web.library_routes import register_library_routes

        for fn in (register_library_routes, register_chat_routes):
            params = inspect.signature(fn).parameters
            self.assertIn("db_factory", params)
            self.assertIn("settings_factory", params)
            self.assertTrue(params["db_factory"].kind is inspect.Parameter.KEYWORD_ONLY)
            self.assertTrue(params["settings_factory"].kind is inspect.Parameter.KEYWORD_ONLY)

    def test_library_and_chat_still_served(self) -> None:
        stats = self.client.get("/api/library/stats")
        self.assertEqual(stats.status_code, 200, stats.text)
        self.assertIn("movies", stats.json())

        threads = self.client.get("/api/chat/threads")
        self.assertEqual(threads.status_code, 200, threads.text)
        self.assertIsInstance(threads.json(), list)

        gone = self.client.get("/api/chat/stream", params={"message": "hi"})
        self.assertEqual(gone.status_code, 410)

    def test_app_py_no_longer_defines_those_handlers(self) -> None:
        self.assertFalse(hasattr(self.app_mod, "library_stats"))
        self.assertFalse(hasattr(self.app_mod, "chat"))
        self.assertFalse(hasattr(self.app_mod, "chat_stream"))
        from projectionist.web import chat_routes, library_routes

        self.assertTrue(hasattr(library_routes, "library_stats"))
        self.assertTrue(hasattr(chat_routes, "chat"))
        self.assertTrue(hasattr(chat_routes, "chat_stream"))
