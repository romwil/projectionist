"""Version lockstep smoke test.

Asserts every release-managed version field matches ``curatorx.__version__``.
See docs/RELEASE.md (Version parity).
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from curatorx import __version__

_REPO_ROOT = Path(__file__).resolve().parent.parent
_UNRAID_XML_PATHS = (
    "templates/curatorx.xml",
    "unraid/curatorx.xml",
)


def _pyproject_project_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        tomllib = None  # type: ignore[assignment]
    if tomllib is not None:
        return tomllib.loads(text)["project"]["version"]
    in_project = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "[project]":
            in_project = True
            continue
        if in_project and stripped.startswith("["):
            break
        if in_project:
            match = re.match(r'version\s*=\s*"([^"]+)"', stripped)
            if match:
                return match.group(1)
    raise AssertionError(f"no [project].version in {path}")


def _lockfile_version_fields(path: Path) -> list[tuple[str, str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    fields: list[tuple[str, str]] = []
    if "version" in data:
        fields.append(("top-level", data["version"]))
    root_pkg = (data.get("packages") or {}).get("")
    if isinstance(root_pkg, dict) and "version" in root_pkg:
        fields.append(("packages['']", root_pkg["version"]))
    return fields


class VersionTests(unittest.TestCase):
    def test_version_nonempty(self) -> None:
        self.assertTrue(__version__)

    def test_version_lockstep(self) -> None:
        expected = __version__
        major_minor = ".".join(expected.split(".")[:2])

        sources: dict[str, str] = {
            "package.json": json.loads((_REPO_ROOT / "package.json").read_text(encoding="utf-8"))[
                "version"
            ],
            "frontend/package.json": json.loads(
                (_REPO_ROOT / "frontend/package.json").read_text(encoding="utf-8")
            )["version"],
            "pyproject.toml": _pyproject_project_version(_REPO_ROOT / "pyproject.toml"),
        }
        for label, actual in sources.items():
            with self.subTest(source=label):
                self.assertEqual(actual, expected)

        for lock_rel in ("package-lock.json", "frontend/package-lock.json"):
            fields = _lockfile_version_fields(_REPO_ROOT / lock_rel)
            self.assertTrue(fields, f"{lock_rel} has no version fields to check")
            for field, actual in fields:
                with self.subTest(source=f"{lock_rel}:{field}"):
                    self.assertEqual(actual, expected)

        xml_texts: list[str] = []
        for xml_rel in _UNRAID_XML_PATHS:
            text = (_REPO_ROOT / xml_rel).read_text(encoding="utf-8")
            xml_texts.append(text)
            with self.subTest(source=f"{xml_rel}:comment"):
                self.assertIn(f"CuratorX {expected}", text)
            with self.subTest(source=f"{xml_rel}:changes-head"):
                match = re.search(r"<Changes>\s*###\s*([0-9]+\.[0-9]+\.[0-9]+)", text)
                self.assertIsNotNone(match, f"{xml_rel}: missing ### X.Y.Z under <Changes>")
                assert match is not None
                self.assertEqual(match.group(1), expected)
            with self.subTest(source=f"{xml_rel}:pin-examples"):
                self.assertIn(f"pin `:{major_minor}` / `:{expected}`", text)

        with self.subTest(source="unraid-xml-identical"):
            self.assertEqual(
                xml_texts[0],
                xml_texts[1],
                "templates/curatorx.xml and unraid/curatorx.xml must stay identical",
            )


if __name__ == "__main__":
    unittest.main()
