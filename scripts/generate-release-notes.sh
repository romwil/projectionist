#!/usr/bin/env bash
# Parse CHANGELOG.md into frontend/public/release-notes.json.
#
# Usage:
#   ./scripts/generate-release-notes.sh
#   ./scripts/generate-release-notes.sh --require-version 1.8.4
#
# Fails when --require-version is set and CHANGELOG lacks ## [X.Y.Z].
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CHANGELOG="${ROOT}/CHANGELOG.md"
OUT="${ROOT}/frontend/public/release-notes.json"
REQUIRE_VERSION=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --require-version)
      REQUIRE_VERSION="${2:-}"
      if [[ -z "$REQUIRE_VERSION" ]]; then
        echo "Usage: $0 [--require-version X.Y.Z]" >&2
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      echo "Usage: $0 [--require-version X.Y.Z]"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -f "$CHANGELOG" ]]; then
  echo "CHANGELOG not found: $CHANGELOG" >&2
  exit 1
fi

mkdir -p "$(dirname "$OUT")"

python3 - "$CHANGELOG" "$OUT" "$REQUIRE_VERSION" <<'PY'
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

changelog_path = Path(sys.argv[1])
out_path = Path(sys.argv[2])
require_version = (sys.argv[3] or "").strip()

text = changelog_path.read_text(encoding="utf-8")
# ## [1.8.3] — 2026-07-16  (em dash, en dash, or hyphen)
heading_re = re.compile(
    r"^## \[(\d+\.\d+\.\d+)\]\s*[—–-]\s*(\d{4}-\d{2}-\d{2})\s*$",
    re.MULTILINE,
)
section_re = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
bullet_re = re.compile(r"^[-*]\s+(.+)$")

matches = list(heading_re.finditer(text))
if not matches:
    print("No version headings found in CHANGELOG.md (expected ## [X.Y.Z] — YYYY-MM-DD)", file=sys.stderr)
    sys.exit(1)

releases = []
for index, match in enumerate(matches):
    version = match.group(1)
    date = match.group(2)
    start = match.end()
    end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
    body = text[start:end].strip("\n")

    summary_lines: list[str] = []
    sections: list[dict] = []
    current_section: dict | None = None
    in_summary = True

    for raw_line in body.splitlines():
        line = raw_line.rstrip()
        section_match = section_re.match(line)
        if section_match:
            in_summary = False
            current_section = {"title": section_match.group(1).strip(), "bullets": []}
            sections.append(current_section)
            continue

        bullet_match = bullet_re.match(line.strip())
        if bullet_match and current_section is not None:
            current_section["bullets"].append(bullet_match.group(1).strip())
            continue

        if in_summary:
            if line.strip():
                summary_lines.append(line.strip())
            elif summary_lines:
                # blank line ends the summary paragraph block
                in_summary = False

    releases.append(
        {
            "version": version,
            "date": date,
            "summary": " ".join(summary_lines).strip(),
            "sections": sections,
        }
    )

if require_version:
    versions = {item["version"] for item in releases}
    if require_version not in versions:
        print(
            f"CHANGELOG.md missing heading for release version {require_version} "
            f"(expected ## [{require_version}] — YYYY-MM-DD)",
            file=sys.stderr,
        )
        sys.exit(1)

payload = {
    "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "releases": releases,
}

out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Wrote {out_path} ({len(releases)} releases)")
PY
