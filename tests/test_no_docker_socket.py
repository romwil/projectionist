"""CI fails when shipped packaging mounts a Docker socket."""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECK = REPO / "scripts" / "security" / "check-no-docker-socket.py"


class NoDockerSocketTests(unittest.TestCase):
    def test_repo_packaging_has_no_socket_mount(self) -> None:
        result = subprocess.run(
            [sys.executable, str(CHECK), str(REPO)],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_checker_flags_a_template_target(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("check_no_docker_socket", CHECK)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        text = '<Config Name="Docker Socket" Target="/var/run/docker.sock" Default="" />'
        self.assertTrue(module._XML_TARGET.search(text))
