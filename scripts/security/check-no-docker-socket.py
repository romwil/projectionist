#!/usr/bin/env python3
"""Fail when shipped packaging mounts a Docker socket.

A socket mount is root on the host. Comments may mention the socket.
An active mount, or an Unraid config whose target is the socket, fails.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

_XML_TARGET = re.compile(r"""Target\s*=\s*["']/var/run/docker\.sock["']""")
_VOLUME = re.compile(r"-v\s+\S*docker\.sock|docker\.sock\s*:")


def _active_lines(text: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        if "docker.sock" in line and _VOLUME.search(line):
            found.append((number, line.strip()))
    return found


def findings(root: Path) -> list[str]:
    """Return human-readable hits. Empty means the tree does not mount a socket."""
    hits: list[str] = []
    xml_files = [
        root / "unraid" / "projectionist.xml",
        root / "templates" / "projectionist.xml",
    ]
    for path in xml_files:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if _XML_TARGET.search(text):
            hits.append(f"{path.relative_to(root)}: Config target is /var/run/docker.sock")

    compose = list(root.glob("docker-compose*.yml")) + list(root.glob("Dockerfile*"))
    compose.append(root / "scripts" / "unraid-rollout.sh")
    for path in compose:
        if not path.is_file():
            continue
        for number, line in _active_lines(path.read_text(encoding="utf-8")):
            hits.append(f"{path.relative_to(root)}:{number}: {line}")
    return hits


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else REPO
    hits = findings(root)
    if hits:
        print("Docker socket mount is present:", file=sys.stderr)
        for hit in hits:
            print(f"  {hit}", file=sys.stderr)
        return 1
    print("No Docker socket mount in shipped packaging.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
