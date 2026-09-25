"""License metadata for new releases is AGPL-3.0-only."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _pyproject_text() -> str:
    return (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")


class LicenseMetadataTests(unittest.TestCase):
    def test_license_file_is_official_agpl_v3(self) -> None:
        text = (_REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
        first_lines = "\n".join(text.splitlines()[:8])
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", first_lines)
        self.assertIn("Version 3, 19 November 2007", first_lines)
        self.assertIn("Copyright (C) 2007 Free Software Foundation", first_lines)
        self.assertNotIn("MIT License", first_lines)
        self.assertIn("END OF TERMS AND CONDITIONS", text)

    def test_pyproject_spdx_and_classifier(self) -> None:
        text = _pyproject_text()
        self.assertRegex(text, r'license\s*=\s*\{\s*text\s*=\s*"AGPL-3\.0-only"\s*\}')
        self.assertIn("License :: OSI Approved :: GNU Affero General Public License v3", text)
        self.assertNotIn("License :: OSI Approved :: MIT License", text)

    def test_about_page_states_agpl_and_mit_history(self) -> None:
        about = (_REPO_ROOT / "frontend/src/pages/AboutPage.jsx").read_text(encoding="utf-8")
        self.assertIn("AGPL-3.0-only", about)
        self.assertIn("Previous releases through 1.36.0 were MIT", about)
        self.assertIn("not a grant to call forks", about)
        self.assertNotIn("License · MIT", about)

    def test_package_json_spdx(self) -> None:
        for rel in ("package.json", "frontend/package.json"):
            data = json.loads((_REPO_ROOT / rel).read_text(encoding="utf-8"))
            with self.subTest(rel=rel):
                self.assertEqual(data.get("license"), "AGPL-3.0-only")

    def test_docker_label_spdx(self) -> None:
        dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn('org.opencontainers.image.licenses="AGPL-3.0-only"', dockerfile)
        self.assertNotIn('org.opencontainers.image.licenses="MIT"', dockerfile)
