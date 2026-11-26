#!/usr/bin/env python3
"""Fail when a shipped template or compose file mounts a Docker socket or a read-write library.

The library paths are /tv, /movies, and /preroll. /config stays read-write.
An optional /copies folder may be read-write because copies are not the library.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIBRARY_TARGETS = ("/tv", "/movies", "/preroll")
COMPOSE_FILES = (
    ROOT / "docker-compose.yml",
    ROOT / "docker-compose.unraid.yml",
)
TEMPLATE_PAIRS = (
    (ROOT / "unraid" / "projectionist.xml", ROOT / "templates" / "projectionist.xml"),
)
SECURITY_MARKERS = (
    "no-new-privileges:true",
    "cap_drop:",
    "- ALL",
    "read_only: true",
    "/api/ready",
)


def fail(message: str) -> None:
    print(f"container hardening: {message}", file=sys.stderr)
    raise SystemExit(1)


def check_compose(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "docker.sock" in text or "DOCKER_SOCK" in text:
        fail(f"{path.name} mentions a Docker socket")
    for marker in SECURITY_MARKERS:
        if marker not in text:
            fail(f"{path.name} is missing {marker}")
    for raw in text.splitlines():
        body = raw.split("#", 1)[0].strip()
        if not body.startswith("-"):
            continue
        library = any(token in body for token in LIBRARY_TARGETS)
        if library and not body.endswith(":ro"):
            fail(f"{path.name} library mount is not read-only: {body}")
        if ":/config" in body and body.endswith(":ro"):
            fail(f"{path.name} mounts /config read-only")


def check_template(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "docker.sock" in text or "group-add 281" in text:
        fail(f"{path.name} still offers a Docker socket")
    required = (
        "no-new-privileges:true",
        "--cap-drop ALL",
        "--read-only",
        "--tmpfs /tmp",
        "LAN only",
    )
    for marker in required:
        if marker not in text:
            fail(f"{path.name} is missing {marker}")
    for target in LIBRARY_TARGETS:
        needle = f'Target="{target}"'
        if needle not in text:
            fail(f"{path.name} has no {target} mount")
        # The Config element for this target must say Mode="ro".
        start = text.index(needle)
        element = text[text.rindex("<Config", 0, start) : text.index(">", start) + 1]
        if 'Mode="ro"' not in element:
            fail(f"{path.name} {target} is not Mode ro")
    config_at = text.index('Target="/config"')
    config_element = text[text.rindex("<Config", 0, config_at) : text.index(">", config_at) + 1]
    if 'Mode="rw"' not in config_element:
        fail(f"{path.name} /config is not read-write")


def check_rollout(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "docker.sock" in text:
        fail("unraid-rollout.sh still names a Docker socket path")
    if "-v \"${DOCKER_SOCK}" in text or "MOUNT_DOCKER_SOCK:-/var/run" in text:
        fail("unraid-rollout.sh still mounts a Docker socket")
    if ":ro" not in text:
        fail("unraid-rollout.sh does not mount the library read-only")
    for marker in ("no-new-privileges:true", "--cap-drop", "ALL", "--read-only", "--tmpfs"):
        if marker not in text:
            fail(f"unraid-rollout.sh is missing {marker}")


def check_smoke(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "docker.sock" not in text:
        fail("docker-smoke does not assert the absence of a Docker socket")
    for marker in ("no-new-privileges:true", "--cap-drop", "ALL", "--read-only"):
        if marker not in text:
            fail(f"docker-smoke does not run with {marker}")


def main() -> None:
    for path in COMPOSE_FILES:
        check_compose(path)
    for left, right in TEMPLATE_PAIRS:
        check_template(left)
        check_template(right)
        if left.read_text(encoding="utf-8") != right.read_text(encoding="utf-8"):
            fail(f"{left.relative_to(ROOT)} and {right.relative_to(ROOT)} differ")
    check_rollout(ROOT / "scripts" / "unraid-rollout.sh")
    check_smoke(ROOT / ".github" / "workflows" / "ci.yml")
    entry = (ROOT / "scripts" / "docker-entrypoint.sh").read_text(encoding="utf-8")
    if "docker.sock" not in entry or "warning" not in entry:
        fail("the entrypoint does not warn when a Docker socket is mounted")
    print("container hardening: templates, compose, and rollout match")


if __name__ == "__main__":
    main()
