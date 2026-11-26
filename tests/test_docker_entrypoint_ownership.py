"""Entrypoint ownership repair: stray files, not a recursive chown of a good tree."""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve().parents[1] / "scripts" / "docker-entrypoint.sh"


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


class EntrypointOwnershipTests(unittest.TestCase):
    def _run(self, root: Path, *, uid: str, stat_uid: str, stat_gid: str, find_paths: str, forbid_find: bool, args: list[str]):
        bin_dir = root / "bin"
        bin_dir.mkdir()
        chown_log = root / "chown.log"
        gosu_log = root / "gosu.log"
        find_log = root / "find.log"
        find_paths_file = root / "find-paths.txt"
        find_paths_file.write_text(find_paths, encoding="utf-8")
        marker = root / "marker"
        _write(
            bin_dir / "id",
            "#!/bin/sh\n"
            f"echo {uid}\n",
        )
        _write(
            bin_dir / "stat",
            "#!/bin/sh\n"
            "fmt=\n"
            "while [ $# -gt 0 ]; do\n"
            "  case \"$1\" in\n"
            "    -c) fmt=\"$2\"; shift 2 ;;\n"
            "    *) shift ;;\n"
            "  esac\n"
            "done\n"
            "case \"$fmt\" in\n"
            f"  *%u*) echo {stat_uid} ;;\n"
            f"  *%g*) echo {stat_gid} ;;\n"
            "esac\n",
        )
        _write(
            bin_dir / "find",
            "#!/bin/sh\n"
            "if [ \"$FORBID_FIND\" = 1 ]; then echo ran >> \"$FIND_LOG\"; exit 99; fi\n"
            "cat \"$FIND_PATHS_FILE\"\n",
        )
        _write(
            bin_dir / "chown",
            "#!/bin/sh\n"
            "echo \"$@\" >> \"$CHOWN_LOG\"\n",
        )
        _write(
            bin_dir / "gosu",
            "#!/bin/sh\n"
            "echo \"$@\" >> \"$GOSU_LOG\"\n",
        )
        _write(
            bin_dir / "marker",
            "#!/bin/sh\n"
            "echo ran >> \"$MARKER\"\n",
        )
        env = os.environ.copy()
        env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
        env["PROJECTIONIST_CONFIG_DIR"] = str(root / "config")
        env["CHOWN_LOG"] = str(chown_log)
        env["GOSU_LOG"] = str(gosu_log)
        env["FIND_LOG"] = str(find_log)
        env["FIND_PATHS_FILE"] = str(find_paths_file)
        env["FORBID_FIND"] = "1" if forbid_find else "0"
        env["MARKER"] = str(marker)
        (root / "config").mkdir()
        (root / "config" / "curatorx.db").write_bytes(b"real-database-bytes")
        return subprocess.run(
            ["sh", str(ENTRYPOINT), *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        ), chown_log, gosu_log, find_log, marker

    def test_stray_file_is_chowned_and_named_without_rewriting_the_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stray = root / "config" / "projectionist.db"
            completed, chown_log, gosu_log, find_log, _marker = self._run(
                root,
                uid="0",
                stat_uid="1000",
                stat_gid="1000",
                find_paths=f"{stray}\n",
                forbid_find=False,
                args=["marker"],
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn(f"fixing ownership of {stray}", completed.stderr)
            log = chown_log.read_text(encoding="utf-8")
            self.assertIn(f"projectionist:projectionist {stray}", log)
            self.assertNotIn("-R", log)
            self.assertNotIn("curatorx.db", log)
            self.assertFalse(find_log.exists())
            self.assertIn("projectionist marker", gosu_log.read_text(encoding="utf-8"))

    def test_already_correct_tree_skips_chown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            completed, chown_log, gosu_log, _find_log, _marker = self._run(
                root,
                uid="0",
                stat_uid="1000",
                stat_gid="1000",
                find_paths="",
                forbid_find=False,
                args=["marker"],
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertNotIn("fixing ownership", completed.stderr)
            self.assertFalse(chown_log.exists())
            self.assertTrue(gosu_log.exists())

    def test_wrong_directory_owner_is_one_recursive_chown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config"
            completed, chown_log, _gosu_log, find_log, _marker = self._run(
                root,
                uid="0",
                stat_uid="0",
                stat_gid="0",
                find_paths="",
                forbid_find=True,
                args=["marker"],
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn(f"fixing ownership of {config}", completed.stderr)
            self.assertEqual(
                chown_log.read_text(encoding="utf-8").strip(),
                f"-R projectionist:projectionist {config}",
            )
            self.assertFalse(find_log.exists())

    def test_root_owned_settings_is_chowned_before_the_app_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = root / "config" / "settings.json"
            completed, chown_log, gosu_log, _find_log, _marker = self._run(
                root,
                uid="0",
                stat_uid="1000",
                stat_gid="1000",
                find_paths=f"{settings}\n",
                forbid_find=False,
                args=["marker"],
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn(f"fixing ownership of {settings}", completed.stderr)
            self.assertIn(
                f"projectionist:projectionist {settings}",
                chown_log.read_text(encoding="utf-8"),
            )
            self.assertIn("projectionist marker", gosu_log.read_text(encoding="utf-8"))

    def test_non_root_does_not_chown(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            completed, chown_log, gosu_log, find_log, marker = self._run(
                root,
                uid="1000",
                stat_uid="1000",
                stat_gid="1000",
                find_paths="",
                forbid_find=True,
                args=["marker"],
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertFalse(chown_log.exists())
            self.assertFalse(gosu_log.exists())
            self.assertFalse(find_log.exists())
            self.assertEqual(marker.read_text(encoding="utf-8").strip(), "ran")


if __name__ == "__main__":
    unittest.main()
