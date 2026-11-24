#!/usr/bin/env bash
# Hub-first release: this push IS the release artifact.
# A version is not released until romwil/projectionist:X.Y.Z exists on Hub.
# GitHub merge / local Unraid docker build are NOT substitutes. See docs/RELEASE.md.
# Multi-arch Docker Hub release for Projectionist.
#
# Canonical image: romwil/projectionist
#
# The image is built from the commit tag v<version> points at. The OCI label
# org.opencontainers.image.revision is that full commit. The script exits if
# the published label and the tag's commit differ.
#
# Before any tag is created or pushed, the commit that would be tagged must
# contain a CHANGELOG heading ## [X.Y.Z] — YYYY-MM-DD. A missing heading exits
# non-zero and does not create or push the tag. When the tag is absent and the
# heading is present, this script creates the annotated tag on HEAD and pushes
# it. An existing tag is not moved.
#
# ALWAYS push Docker v2 schema 2 manifest lists (not OCI indexes with
# attestations). Unraid Dockerman's update checker fails on OCI indexes
# (shows "not available"); Force Update then recreates from the local tag.
#
# Flags: --provenance=false --sbom=false
#
# Usage:
#   ./scripts/docker-release.sh 1.8.11
#   ./scripts/docker-release.sh 1.8.11 --also-line 1.8
#   ./scripts/docker-release.sh 1.8.11 --date-tag          # also :latest-YYYYMMDD
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-}"
if [[ -z "$VERSION" || "$VERSION" == --* ]]; then
  echo "Usage: $0 <version> [--also-line X.Y] [--date-tag]" >&2
  exit 1
fi
shift || true

ALSO_LINE=""
DATE_TAG=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --also-line)
      ALSO_LINE="${2:-}"
      shift 2
      ;;
    --date-tag)
      DATE_TAG=1
      shift
      ;;
    *)
      echo "Unknown arg: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$ALSO_LINE" ]]; then
  # Derive line tag from semver X.Y.Z → X.Y
  ALSO_LINE="$(echo "$VERSION" | awk -F. '{print $1"."$2}')"
fi

IMAGE="romwil/projectionist"
PLATFORMS="linux/amd64,linux/arm64"
BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DATE_STAMP="$(date -u +%Y%m%d)"
TAG_NAME="v${VERSION}"
TMP_ROOT="${TMPDIR:-/tmp}"
TMP_ROOT="${TMP_ROOT%/}"
BUILD_PARENT=""
BUILD_DIR=""

cleanup_release_worktree() {
  status=$?
  case "${BUILD_PARENT}" in
    "${TMP_ROOT}"/projectionist-release.*)
      if [[ -n "${BUILD_DIR}" ]]; then
        git worktree remove --force "${BUILD_DIR}" >/dev/null 2>&1 || true
      fi
      rm -rf "${BUILD_PARENT}"
      git worktree prune >/dev/null 2>&1 || true
      ;;
  esac
  exit "${status}"
}
trap cleanup_release_worktree EXIT

# The commit we would tag. An existing tag is peeled and is not moved.
EXISTING_TAG_COMMIT="$(git rev-parse --verify --quiet "${TAG_NAME}^{commit}" 2>/dev/null || true)"
if [[ -n "${EXISTING_TAG_COMMIT}" ]]; then
  RELEASE_COMMIT="${EXISTING_TAG_COMMIT}"
else
  RELEASE_COMMIT="$(git rev-parse --verify HEAD)"
fi
if [[ ! "${RELEASE_COMMIT}" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Could not resolve a commit to publish (${RELEASE_COMMIT})." >&2
  exit 1
fi

# Heading check before any tag is created or pushed. git show reads the
# committed tree, so an uncommitted changelog line does not count.
if ! python3 - "${VERSION}" "${RELEASE_COMMIT}" "${TAG_NAME}" <<'PY'
import re
import subprocess
import sys

version, commit, tag_name = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    text = subprocess.check_output(
        ["git", "show", f"{commit}:CHANGELOG.md"],
        text=True,
        stderr=subprocess.DEVNULL,
    )
except subprocess.CalledProcessError:
    text = ""
pattern = re.compile(
    rf"^## \[{re.escape(version)}\]\s*[—–-]\s*\d{{4}}-\d{{2}}-\d{{2}}\s*$",
    re.MULTILINE,
)
if pattern.search(text):
    raise SystemExit(0)
print(
    f"CHANGELOG.md at {commit} is missing heading ## [{version}] — YYYY-MM-DD.",
    file=sys.stderr,
)
print(f"Refusing to create or push {tag_name}.", file=sys.stderr)
raise SystemExit(1)
PY
then
  exit 1
fi

if [[ -z "${EXISTING_TAG_COMMIT}" ]]; then
  git tag -a "${TAG_NAME}" "${RELEASE_COMMIT}" -m "${TAG_NAME}"
  if git remote get-url origin >/dev/null 2>&1; then
    if ! git push origin "refs/tags/${TAG_NAME}"; then
      git tag -d "${TAG_NAME}" >/dev/null 2>&1 || true
      echo "Push of ${TAG_NAME} failed. Removed the local tag so a later run can create it." >&2
      exit 1
    fi
  fi
fi

verify_published_revision() {
  local ref="$1"
  local expected="$2"
  local tag_name="$3"
  local media checked digests digest label
  media="$(docker buildx imagetools inspect "${ref}" --format '{{.Manifest.MediaType}}')"
  checked=0
  case "${media}" in
    *manifest.list*|*image.index*)
      digests="$(docker buildx imagetools inspect "${ref}" --format '{{range .Manifest.Manifests}}{{.Digest}}{{"\n"}}{{end}}')"
      while IFS= read -r digest; do
        [[ -z "${digest}" ]] && continue
        checked=$((checked + 1))
        label="$(docker buildx imagetools inspect "${IMAGE}@${digest}" --format '{{index .Image.Config.Labels "org.opencontainers.image.revision"}}')"
        if [[ "${label}" != "${expected}" ]]; then
          echo "org.opencontainers.image.revision for ${IMAGE}@${digest} is '${label}', and ${tag_name} is ${expected}." >&2
          echo "The image revision must match the tag." >&2
          exit 1
        fi
      done <<< "${digests}"
      ;;
    *)
      checked=1
      label="$(docker buildx imagetools inspect "${ref}" --format '{{index .Image.Config.Labels "org.opencontainers.image.revision"}}')"
      if [[ "${label}" != "${expected}" ]]; then
        echo "org.opencontainers.image.revision for ${ref} is '${label}', and ${tag_name} is ${expected}." >&2
        echo "The image revision must match the tag." >&2
        exit 1
      fi
      ;;
  esac
  if [[ "${checked}" -eq 0 ]]; then
    echo "No image manifest for ${ref}; cannot confirm org.opencontainers.image.revision." >&2
    exit 1
  fi
}

TAGS=(
  -t "${IMAGE}:${VERSION}"
  -t "${IMAGE}:${ALSO_LINE}"
  -t "${IMAGE}:latest"
)

if [[ "$DATE_TAG" -eq 1 ]]; then
  TAGS+=(-t "${IMAGE}:latest-${DATE_STAMP}")
fi

echo "Page-speed gate before Hub publish (GitHub Actions does not block this script):"
echo "  npm run test:release-perf"
echo "Budgets: frontend/perf/baseline.json — docs/RELEASE.md"

# Build a clean worktree of the tagged commit so an earlier checkout, or
# uncommitted files in this one, cannot become the image.
BUILD_PARENT="$(mktemp -d "${TMP_ROOT}/projectionist-release.XXXXXX")"
BUILD_DIR="${BUILD_PARENT}/tree"
git worktree add --detach "${BUILD_DIR}" "${RELEASE_COMMIT}"

echo "Generating release notes from ${TAG_NAME} (${RELEASE_COMMIT})"
( cd "${BUILD_DIR}" && ./scripts/generate-release-notes.sh --require-version "${VERSION}" )

echo "Writing version-stable dependency manifests (.docker-deps/)"
( cd "${BUILD_DIR}" && ./scripts/docker-dep-manifests.sh )

echo "Building ${IMAGE}:${VERSION} (+ :${ALSO_LINE} :latest) for ${PLATFORMS}"
echo "Source commit: ${TAG_NAME} ${RELEASE_COMMIT}"
echo "Build identity: version=${VERSION} created=${BUILD_DATE} revision=${RELEASE_COMMIT}"
echo "Flags: --provenance=false --sbom=false (Unraid-compatible Docker v2 manifests)"

# buildx is always BuildKit; export for any nested classic docker and document intent.
# Cache mounts in the Dockerfile need BuildKit (npm/pip --mount=type=cache).
export DOCKER_BUILDKIT=1

docker buildx build \
  --platform "${PLATFORMS}" \
  --provenance=false \
  --sbom=false \
  --build-arg "PROJECTIONIST_VERSION=${VERSION}" \
  --build-arg "BUILD_DATE=${BUILD_DATE}" \
  --build-arg "VCS_REF=${RELEASE_COMMIT}" \
  "${TAGS[@]}" \
  --push \
  "${BUILD_DIR}"

echo ""
echo "=== Hub inspect (expect MediaType: docker.distribution.manifest.list.v2+json) ==="
docker buildx imagetools inspect "${IMAGE}:${VERSION}" | head -30

echo ""
echo "=== Digests (paste into release notes / Unraid verify) ==="
for ref in \
  "${IMAGE}:${VERSION}" \
  "${IMAGE}:latest"
do
  echo "Tag ${ref}:"
  docker buildx imagetools inspect "${ref}" --format '{{.Manifest.Digest}}' 2>/dev/null \
    || docker buildx imagetools inspect "${ref}" | awk '/^Digest:/{print $2; exit}'
done
if [[ "$DATE_TAG" -eq 1 ]]; then
  for ref in "${IMAGE}:latest-${DATE_STAMP}"; do
    echo "Tag ${ref}:"
    docker buildx imagetools inspect "${ref}" --format '{{.Manifest.Digest}}' 2>/dev/null \
      || docker buildx imagetools inspect "${ref}" | awk '/^Digest:/{print $2; exit}'
  done
fi

echo ""
echo "=== Revision label (must match ${TAG_NAME}) ==="
verify_published_revision "${IMAGE}:${VERSION}" "${RELEASE_COMMIT}" "${TAG_NAME}"
echo "org.opencontainers.image.revision=${RELEASE_COMMIT}"

echo ""
echo "Unraid owners: Force Update can report TOTAL DATA PULLED: 0 B when the local"
echo "  ${IMAGE}:latest tag is stale. Supported path:"
echo "  docker pull ${IMAGE}:latest"
echo "  # or: cd /mnt/user/appdata/projectionist && ./rollout.sh latest"
echo "  # or: ./scripts/unraid-force-pull.sh   (from a checkout / copied into appdata)"
echo "See docs/DOCKER.md and docs/wiki/Unraid.md."
