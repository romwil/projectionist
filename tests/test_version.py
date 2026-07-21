"""Version smoke test."""

import json
import unittest
from pathlib import Path

from curatorx import __version__

_REPO_ROOT = Path(__file__).resolve().parent.parent


class VersionTests(unittest.TestCase):
    def test_version(self) -> None:
        self.assertTrue(__version__)

    def test_root_package_json_version_matches(self) -> None:
        package_json = json.loads((_REPO_ROOT / "package.json").read_text())
        self.assertEqual(package_json["version"], __version__)


if __name__ == "__main__":
    unittest.main()
