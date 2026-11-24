"""docker-release.sh builds the tagged commit and checks the revision label.

The Hub image for a version has to be that tag's commit. v1.41.2 was built
from an earlier branch commit, then the tag was placed on the merge.
"""

from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "docker-release.sh"


def _run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class DockerReleaseRevisionTests(unittest.TestCase):
    def test_dockerfile_stamps_revision_from_vcs_ref(self) -> None:
        dockerfile = (_REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")
        self.assertIn('org.opencontainers.image.revision="${VCS_REF}"', dockerfile)

    def test_script_resolves_the_tag_commit(self) -> None:
        text = _SCRIPT.read_text(encoding="utf-8")
        self.assertIn("${TAG_NAME}^{commit}", text)
        self.assertIn("org.opencontainers.image.revision", text)
        self.assertIn("Refusing to create or push", text)
        self.assertNotIn("git tag -f", text)
        self.assertNotIn("git rev-parse --short HEAD", text)

    def test_builds_tagged_commit_when_checkout_is_earlier(self) -> None:
        with self._repo() as (repo, tagged, earlier):
            self._checkout(repo, earlier)
            (repo / "DIRTY").write_text("local only\n", encoding="utf-8")
            capture = repo / "docker-capture.txt"
            result = self._release(repo, capture)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            recorded = capture.read_text(encoding="utf-8")
            self.assertIn(f"vcs={tagged}", recorded)
            self.assertIn("marker=tagged", recorded)
            self.assertIn("dirty=no", recorded)
            self.assertEqual(self._head(repo), earlier)
            worktrees = _run(["git", "worktree", "list"], repo).stdout.splitlines()
            self.assertEqual(len(worktrees), 1)

    def test_fails_when_published_label_differs_from_the_tag(self) -> None:
        with self._repo() as (repo, tagged, earlier):
            self._checkout(repo, earlier)
            capture = repo / "docker-capture.txt"
            result = self._release(
                repo,
                capture,
                extra_env={"STUB_REVISION_LABEL": "0" * 40},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("The image revision must match the tag.", result.stderr)
            self.assertIn(tagged, result.stderr)
            self.assertIn(f"vcs={tagged}", capture.read_text(encoding="utf-8"))
            self.assertEqual(self._head(repo), earlier)

    def test_fails_when_the_version_tag_is_missing(self) -> None:
        with self._repo() as (repo, _tagged, earlier):
            self._checkout(repo, earlier)
            capture = repo / "docker-capture.txt"
            env = self._env(repo, capture)
            result = _run(["bash", "scripts/docker-release.sh", "9.9.9"], repo, env)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing to create or push v9.9.9.", result.stderr)
            self.assertIn("missing heading ## [9.9.9]", result.stderr)
            self.assertNotEqual(_run(["git", "rev-parse", "--verify", "v9.9.9"], repo).returncode, 0)
            self.assertFalse(capture.exists())
            self.assertEqual(self._head(repo), earlier)

    def test_missing_heading_does_not_create_or_push_a_tag(self) -> None:
        with self._repo() as (repo, _tagged, _earlier):
            _run(["git", "tag", "-d", "v1.2.3"], repo)
            (repo / "CHANGELOG.md").write_text("## [Unreleased]\n", encoding="utf-8")
            git = ["git", "-c", "user.email=release-test@example.com", "-c", "user.name=Release Test"]
            _must(git + ["add", "CHANGELOG.md"], repo)
            _must(git + ["commit", "-m", "drop heading"], repo)
            head = _run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
            capture = repo / "docker-capture.txt"
            result = self._release(repo, capture)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Refusing to create or push v1.2.3.", result.stderr)
            self.assertIn(head, result.stderr)
            self.assertNotEqual(_run(["git", "rev-parse", "--verify", "v1.2.3"], repo).returncode, 0)
            self.assertFalse(capture.exists())
            self.assertEqual(self._head(repo), head)

    def test_creates_annotated_tag_when_heading_is_present(self) -> None:
        with self._repo() as (repo, tagged, _earlier):
            _run(["git", "tag", "-d", "v1.2.3"], repo)
            capture = repo / "docker-capture.txt"
            result = self._release(repo, capture)
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            peeled = _run(["git", "rev-parse", "v1.2.3^{commit}"], repo)
            self.assertEqual(peeled.stdout.strip(), tagged)
            kind = _run(["git", "cat-file", "-t", "v1.2.3"], repo)
            self.assertEqual(kind.stdout.strip(), "tag")
            self.assertIn(f"vcs={tagged}", capture.read_text(encoding="utf-8"))
            self.assertEqual(self._head(repo), tagged)

    def _repo(self):
        return _ReleaseRepo()

    def _checkout(self, repo: Path, commit: str) -> None:
        result = _run(["git", "checkout", "--detach", commit], repo)
        self.assertEqual(result.returncode, 0, result.stderr)

    def _head(self, repo: Path) -> str:
        result = _run(["git", "rev-parse", "HEAD"], repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def _env(self, repo: Path, capture: Path, extra_env: dict[str, str] | None = None) -> dict[str, str]:
        env = os.environ.copy()
        stub_dir = repo / "stub-bin"
        env["PATH"] = str(stub_dir) + os.pathsep + env.get("PATH", "")
        env["DOCKER_CAPTURE"] = str(capture)
        env.pop("STUB_REVISION_LABEL", None)
        if extra_env:
            env.update(extra_env)
        return env

    def _release(
        self,
        repo: Path,
        capture: Path,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return _run(
            ["bash", "scripts/docker-release.sh", "1.2.3"],
            repo,
            self._env(repo, capture, extra_env),
        )


class _ReleaseRepo:
    """Tiny git repo whose release script is the real docker-release.sh."""

    def __enter__(self) -> tuple[Path, str, str]:
        self._tmpdir = tempfile.TemporaryDirectory()
        repo = Path(self._tmpdir.name)
        scripts = repo / "scripts"
        scripts.mkdir()
        stub_bin = repo / "stub-bin"
        stub_bin.mkdir()
        (scripts / "docker-release.sh").write_text(_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
        (scripts / "generate-release-notes.sh").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (scripts / "docker-dep-manifests.sh").write_text(
            "#!/bin/sh\nmkdir -p .docker-deps\nexit 0\n",
            encoding="utf-8",
        )
        (stub_bin / "docker").write_text(_DOCKER_STUB, encoding="utf-8")
        for path in (
            scripts / "docker-release.sh",
            scripts / "generate-release-notes.sh",
            scripts / "docker-dep-manifests.sh",
            stub_bin / "docker",
        ):
            path.chmod(path.stat().st_mode | stat.S_IEXEC)
        (repo / "marker").write_text("early\n", encoding="utf-8")
        git = ["git", "-c", "user.email=release-test@example.com", "-c", "user.name=Release Test"]
        _must(git + ["init", "-b", "main"], repo)
        _must(["git", "config", "user.email", "release-test@example.com"], repo)
        _must(["git", "config", "user.name", "Release Test"], repo)
        _must(git + ["add", "scripts", "marker"], repo)
        _must(git + ["commit", "-m", "earlier"], repo)
        earlier = _must(["git", "rev-parse", "HEAD"], repo).stdout.strip()
        (repo / "marker").write_text("tagged\n", encoding="utf-8")
        (repo / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [1.2.3] — 2026-01-01\n\nA note.\n\n### Highlights\n- Works.\n",
            encoding="utf-8",
        )
        _must(git + ["add", "marker", "CHANGELOG.md"], repo)
        _must(git + ["commit", "-m", "tagged"], repo)
        tagged = _must(["git", "rev-parse", "HEAD"], repo).stdout.strip()
        _must(git + ["tag", "-a", "v1.2.3", "-m", "v1.2.3"], repo)
        self.repo = repo
        return repo, tagged, earlier

    def __exit__(self, exc_type, exc, tb) -> None:
        self._tmpdir.cleanup()


def _must(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = _run(cmd, cwd)
    if result.returncode != 0:
        raise AssertionError(f"{cmd} failed\n{result.stdout}\n{result.stderr}")
    return result


_DOCKER_STUB = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import os
    import sys
    from pathlib import Path

    args = sys.argv[1:]
    log = Path(os.environ["DOCKER_CAPTURE"]).with_name("docker-log.txt")
    with log.open("a", encoding="utf-8") as handle:
        handle.write(" ".join(args) + "\\n")

    if args[:2] == ["buildx", "build"]:
        vcs = ""
        previous = ""
        for arg in args:
            if previous == "--build-arg" and arg.startswith("VCS_REF="):
                vcs = arg.split("=", 1)[1]
            previous = arg
        context = Path(args[-1])
        marker = (context / "marker").read_text(encoding="utf-8").strip()
        dirty = "yes" if (context / "DIRTY").exists() else "no"
        Path(os.environ["DOCKER_CAPTURE"]).write_text(
            f"vcs={vcs}\\nmarker={marker}\\ndirty={dirty}\\n",
            encoding="utf-8",
        )
        raise SystemExit(0)

    if args[:3] == ["buildx", "imagetools", "inspect"]:
        fmt = ""
        if "--format" in args:
            fmt = args[args.index("--format") + 1]
        if ".Manifest.MediaType" in fmt:
            print("application/vnd.docker.distribution.manifest.list.v2+json")
        elif "range .Manifest.Manifests" in fmt:
            print("sha256:" + "ab" * 32)
        elif ".Manifest.Digest" in fmt:
            print("sha256:" + "cd" * 32)
        elif "org.opencontainers.image.revision" in fmt:
            forced = os.environ.get("STUB_REVISION_LABEL", "")
            if forced:
                print(forced)
            else:
                for line in Path(os.environ["DOCKER_CAPTURE"]).read_text(encoding="utf-8").splitlines():
                    if line.startswith("vcs="):
                        print(line.split("=", 1)[1])
                        break
        else:
            print("Name: romwil/projectionist:1.2.3")
            print("MediaType: docker.distribution.manifest.list.v2+json")
            print("Digest: sha256:" + "cd" * 32)
        raise SystemExit(0)

    print("unexpected docker invocation: " + " ".join(args), file=sys.stderr)
    raise SystemExit(1)
    """
)


if __name__ == "__main__":
    unittest.main()
