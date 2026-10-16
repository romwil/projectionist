"""Tunarr is not part of the running product."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROD = ROOT / "projectionist"
ADMIN = ROOT / "frontend" / "src" / "pages" / "admin" / "LiveChannelsAdvanced.jsx"


def _imports_tunarr_client(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "projectionist.connectors.tunarr" or module.endswith(".tunarr"):
                return True
            for alias in node.names:
                if alias.name in {"TunarrClient", "tunarr_reachable"}:
                    return True
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("connectors.tunarr") or alias.name.endswith(".tunarr"):
                    return True
    return False


class TunarrRemovedTests(unittest.TestCase):
    def test_no_production_module_imports_the_tunarr_client(self) -> None:
        offenders = [
            str(path.relative_to(ROOT))
            for path in PROD.rglob("*.py")
            if _imports_tunarr_client(path)
        ]
        self.assertEqual(offenders, [])
        self.assertFalse((PROD / "connectors" / "tunarr.py").exists())
        self.assertFalse((PROD / "live_channels" / "docker.py").exists())
        self.assertFalse((PROD / "live_channels" / "stream_proxy.py").exists())

    def test_admin_live_setup_has_no_tunarr_url_field(self) -> None:
        text = ADMIN.read_text(encoding="utf-8")
        self.assertNotIn('data-testid="tunarr-url"', text)
        self.assertNotIn("chrisbenincasa/tunarr", text)
        self.assertNotIn("docker_orchestration", text)
        self.assertNotIn("Start the broadcast", text)
        self.assertNotIn('data-testid="live-channels-tuner-url"', text)

    def test_live_play_does_not_need_tunarr(self) -> None:
        from tests.test_live_native_schedule import NativeScheduleTests

        case = NativeScheduleTests()
        case.test_guide_and_channels_when_tunarr_http_is_refused()
        case.test_now_playing_source_is_library_play_session()
