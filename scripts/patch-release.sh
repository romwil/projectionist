#!/usr/bin/env bash
# Dot / patch release prep (Hub-first). Bumps Z in X.Y.Z across lockstep files,
# refreshes Unraid XML + README badge, generates release-notes.json, and prints
# the maintainer ship checklist (Hub → PR → tag → CA proof → rollout).
#
# Does NOT commit, push, tag, publish Hub, or roll out prod — see docs/RELEASE.md.
#
# Historical note: git has no record of a prior patch-release helper; dot ships
# were manual (e.g. v1.33.2 feature commits, chore(release): 1.33.3 @ 4fba871).
# This script codifies that workflow for agents and maintainers.
#
# Usage:
#   ./scripts/patch-release.sh --dry-run
#   ./scripts/patch-release.sh 1.33.4 --xml-summary "One-line CA Changes blurb"
#   ./scripts/patch-release.sh --run-tests
#   ./scripts/patch-release.sh --check   # verify CHANGELOG + lockstep only
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DRY_RUN=0
RUN_TESTS=0
CHECK_ONLY=0
TARGET_VERSION=""
XML_SUMMARY=""

usage() {
  cat <<'EOF'
Usage: patch-release.sh [OPTIONS] [X.Y.Z]

Prepare a dot (patch) release on the current branch.

  X.Y.Z              Target version (default: bump patch on projectionist.__version__)

Options:
  --dry-run          Show planned edits; do not write files
  --xml-summary STR  One-line blurb inserted under <Changes> ### X.Y.Z (required to apply)
  --run-tests        After bump: pytest test_version, frontend unit, lint, build
  --check            Require CHANGELOG ## [X.Y.Z] and lockstep parity; no file writes
  -h, --help         This help

Before running without --dry-run:
  1. Finish code fixes on a PR branch (not main).
  2. Add ## [X.Y.Z] — YYYY-MM-DD to CHANGELOG.md (Highlights + technical + Verification).
  3. Pass --xml-summary for the Unraid template <Changes> head line.

After this script (when user asks to ship):
  ./scripts/docker-release.sh X.Y.Z
  PR → merge main → tag vX.Y.Z → gh release create
  CA proof: pull Hub tag (Path B) — not host docker build
  Prod (if asked): cd …/appdata/projectionist && ./rollout.sh X.Y.Z

See docs/RELEASE.md § Dot (patch) release.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --run-tests)
      RUN_TESTS=1
      shift
      ;;
    --check)
      CHECK_ONLY=1
      shift
      ;;
    --xml-summary)
      XML_SUMMARY="${2:-}"
      if [[ -z "$XML_SUMMARY" ]]; then
        echo "error: --xml-summary requires a value" >&2
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --*)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
    *)
      if [[ -n "$TARGET_VERSION" ]]; then
        echo "error: unexpected extra argument: $1" >&2
        exit 1
      fi
      TARGET_VERSION="$1"
      shift
      ;;
  esac
done

CURRENT="$(python3 - <<'PY'
from projectionist import __version__
print(__version__)
PY
)"

if [[ -z "$TARGET_VERSION" ]]; then
  if [[ "$CHECK_ONLY" -eq 1 ]]; then
    TARGET_VERSION="$CURRENT"
  else
    TARGET_VERSION="$(python3 - <<PY
cur = "$CURRENT".split(".")
if len(cur) != 3 or not all(p.isdigit() for p in cur):
    raise SystemExit("current version is not semver X.Y.Z: $CURRENT")
print(f"{cur[0]}.{cur[1]}.{int(cur[2]) + 1}")
PY
)"
  fi
fi

if ! [[ "$TARGET_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "error: target must be semver X.Y.Z (got: $TARGET_VERSION)" >&2
  exit 1
fi

MAJOR_MINOR="$(echo "$TARGET_VERSION" | awk -F. '{print $1"."$2}')"

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  echo "Patch release check: ${TARGET_VERSION}"
else
  echo "Patch release prep: ${CURRENT} → ${TARGET_VERSION}"
fi
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "(dry-run — no files will be modified)"
fi

# --- CHANGELOG gate ---
CHANGELOG_HEADING="## [${TARGET_VERSION}]"
if ! grep -qE "^## \\[${TARGET_VERSION//./\\.}\\]" CHANGELOG.md; then
  echo "" >&2
  echo "error: CHANGELOG.md missing heading: ${CHANGELOG_HEADING} — YYYY-MM-DD" >&2
  echo "Add the release section (Highlights + technical + Verification) first." >&2
  echo "See docs/RELEASE.md § CHANGELOG." >&2
  exit 1
fi

if [[ "$CHECK_ONLY" -eq 1 ]]; then
  echo "CHANGELOG heading OK for ${TARGET_VERSION}"
  .venv/bin/python -m pytest tests/test_version.py -v --no-cov
  echo "check: CHANGELOG heading + lockstep OK (run without --check to regenerate release-notes)"
  exit 0
fi

if [[ "$DRY_RUN" -eq 0 && -z "$XML_SUMMARY" ]]; then
  echo "error: --xml-summary is required to apply Unraid <Changes> (or use --dry-run)" >&2
  exit 1
fi

export ROOT TARGET_VERSION CURRENT MAJOR_MINOR XML_SUMMARY DRY_RUN

python3 - <<'PY'
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

root = Path(os.environ["ROOT"])
target = os.environ["TARGET_VERSION"]
current = os.environ["CURRENT"]
major_minor = os.environ["MAJOR_MINOR"]
xml_summary = os.environ.get("XML_SUMMARY", "")
dry_run = os.environ.get("DRY_RUN") == "1"

if target == current and not dry_run:
    print(f"note: already at {target}; refreshing release-notes only")

planned: list[str] = []


def set_version_py(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    new = re.sub(
        r'^__version__\s*=\s*"[^"]+"',
        f'__version__ = "{target}"',
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if new != text:
        planned.append(str(path.relative_to(root)))
        if not dry_run:
            path.write_text(new, encoding="utf-8")


def set_pyproject(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    new = re.sub(
        r'(^version\s*=\s*")[^"]+(")',
        rf"\g<1>{target}\g<2>",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if new != text:
        planned.append(str(path.relative_to(root)))
        if not dry_run:
            path.write_text(new, encoding="utf-8")


def set_package_json(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != target:
        planned.append(str(path.relative_to(root)))
        if not dry_run:
            data["version"] = target
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def set_lockfile(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    if data.get("version") != target:
        data["version"] = target
        changed = True
    root_pkg = data.get("packages", {}).get("")
    if isinstance(root_pkg, dict) and root_pkg.get("version") != target:
        root_pkg["version"] = target
        changed = True
    if changed:
        planned.append(str(path.relative_to(root)))
        if not dry_run:
            path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def set_readme(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    new = re.sub(
        r"(badge/version-)[0-9]+\.[0-9]+\.[0-9]+(-green\.svg)",
        rf"\g<1>{target}\g<2>",
        text,
        count=1,
    )
    if new != text:
        planned.append(str(path.relative_to(root)))
        if not dry_run:
            path.write_text(new, encoding="utf-8")


def set_unraid_xml(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    target_heading = rf"^### {re.escape(target)}\s*$"
    new = re.sub(
        r"(<!-- Unraid Community Applications template — Projectionist )[0-9]+\.[0-9]+\.[0-9]+( -->)",
        rf"\g<1>{target}\g<2>",
        text,
        count=1,
    )
    # Pin examples: keep line tag X.Y, update exact patch in `:X.Y.Z` tokens
    new = re.sub(
        r"(pin `:)[0-9]+\.[0-9]+\.[0-9]+",
        rf"\g<1>{target}",
        new,
    )
    new = re.sub(
        r"(pin `:)[0-9]+\.[0-9]+` / `:[0-9]+\.[0-9]+\.[0-9]+",
        rf"\g<1>{major_minor}` / `:{target}",
        new,
    )
    if not re.search(target_heading, new, flags=re.MULTILINE):
        if not xml_summary and not dry_run:
            print("error: --xml-summary required for new ### under <Changes>", file=sys.stderr)
            sys.exit(1)
        insert = f"### {target}\n{xml_summary or '(dry-run summary placeholder)'}\n\n"
        new = re.sub(
            r"(<Changes>\s*\n)",
            rf"\1{insert}",
            new,
            count=1,
        )
        if not re.search(target_heading, new, flags=re.MULTILINE):
            rel = path.relative_to(root)
            print(
                f"error: failed to insert ### {target} under <Changes> in {rel}",
                file=sys.stderr,
            )
            print(
                "  ensure <Changes> exists with a newline immediately after the opening tag",
                file=sys.stderr,
            )
            sys.exit(1)
    if new != text:
        planned.append(str(path.relative_to(root)))
        if not dry_run:
            path.write_text(new, encoding="utf-8")


set_version_py(root / "projectionist" / "_version.py")
set_pyproject(root / "pyproject.toml")
set_package_json(root / "package.json")
set_package_json(root / "frontend" / "package.json")
set_lockfile(root / "package-lock.json")
set_lockfile(root / "frontend" / "package-lock.json")
set_readme(root / "README.md")
for rel in ("templates/projectionist.xml", "unraid/projectionist.xml"):
    set_unraid_xml(root / rel)

if dry_run:
    print("Would update:" if planned else "No version file changes needed (already at target?):")
    for p in planned:
        print(f"  - {p}")
    if not xml_summary:
        print("  (pass --xml-summary to preview <Changes> blurb on apply)")
else:
    if planned:
        print("Updated:")
        for p in planned:
            print(f"  - {p}")
    else:
        print("Version files already at target; continuing to release-notes + checks.")
PY

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo ""
  echo "Next (after CHANGELOG + --xml-summary on real run):"
  echo "  ./scripts/patch-release.sh ${TARGET_VERSION} --xml-summary '…' [--run-tests]"
  echo "  ./scripts/docker-release.sh ${TARGET_VERSION}   # when user asks to ship"
  exit 0
fi

echo ""
echo "Generating release-notes.json (require CHANGELOG ## [${TARGET_VERSION}])"
./scripts/generate-release-notes.sh --require-version "${TARGET_VERSION}"

echo ""
echo "Verifying lockstep (tests/test_version.py)"
.venv/bin/python -m pytest tests/test_version.py -v --no-cov

if [[ "$RUN_TESTS" -eq 1 ]]; then
  echo ""
  echo "Running full release test gates (docs/RELEASE.md)"
  .venv/bin/python -m pytest tests/ -q
  (cd frontend && npm run test:unit && npm run lint && npm run build)
fi

cat <<EOF

────────────────────────────────────────────────────────────
Dot release ${TARGET_VERSION} — tree prep done. Ship checklist:

  □ Review git diff (version files + CHANGELOG + release-notes.json)
  □ Commit on PR branch:  v${TARGET_VERSION}: <Highlights-style title>
  □ Open/update PR into main (never push directly to main)
  □ When user asks to ship:
      1. ./scripts/docker-release.sh ${TARGET_VERSION}
      2. Merge PR → main → tag v${TARGET_VERSION} → gh release create
      3. CA proof: pull Hub tag (Path B) — not Automat host build (Path A)
      4. Prod if asked: cd …/appdata/projectionist && ./rollout.sh ${TARGET_VERSION}
      5. Spin down projectionist-qa (:8790) unless QA campaign active

Full runbook: docs/RELEASE.md
────────────────────────────────────────────────────────────
EOF
