#!/usr/bin/env bash
# Write version-stripped dependency manifests for the Docker build.
#
# Patch releases rewrite the version in package.json, the lockfile, and
# pyproject.toml. Those bytes used to sit in front of `npm ci` and
# `pip install`, so every ship reinstalled dependencies. The files under
# .docker-deps/ keep the dependency set and pin the version to 0.0.0 so
# those layers stay cached. The image still copies the real manifests
# after the installs.
#
# docker-release.sh runs this. A bare `docker build` needs it first.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

python3 - <<'PY'
import pathlib
import re

root = pathlib.Path(".")
out = root / ".docker-deps"
frontend = out / "frontend"
frontend.mkdir(parents=True, exist_ok=True)

def rewrite_version_fields(path: pathlib.Path, dest: pathlib.Path, expected: int) -> None:
    text = path.read_text(encoding="utf-8")
    match = re.search(r'"version": "([^"]+)"', text)
    if not match:
        raise SystemExit(f"{path}: no version field")
    version = match.group(1)
    needle = f'"version": "{version}"'
    count = text.count(needle)
    if count < expected:
        raise SystemExit(f"{path}: expected at least {expected} {needle!r}, found {count}")
    # Only the root manifest version (and lockfile packages[""]). A dependency
    # that happens to share the same version string stays intact.
    rewritten = text.replace(needle, '"version": "0.0.0"', expected)
    dest.write_text(rewritten, encoding="utf-8")

rewrite_version_fields(
    root / "frontend/package.json",
    frontend / "package.json",
    1,
)
rewrite_version_fields(
    root / "frontend/package-lock.json",
    frontend / "package-lock.json",
    2,
)

pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")
normalized, n = re.subn(
    r'(?m)^version\s*=\s*"[^"]*"',
    'version = "0.0.0"',
    pyproject,
    count=1,
)
if n != 1:
    raise SystemExit("pyproject.toml: could not normalize [project].version")
(out / "pyproject.toml").write_text(normalized, encoding="utf-8")

# README badge changes every release. pip reads readme= from pyproject, so the
# dep layer gets a constant stub. The Dockerfile copies the real README after.
(out / "README.md").write_text(
    "# Projectionist\n\n"
    "Stub README for the Docker dependency layer. "
    "The image build copies the real README after wheels are installed.\n",
    encoding="utf-8",
)
(out / "LICENSE").write_bytes((root / "LICENSE").read_bytes())
print(f"Wrote {out}/ (dependency manifests with version 0.0.0)")
PY
