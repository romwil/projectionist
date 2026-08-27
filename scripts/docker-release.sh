#!/usr/bin/env bash
# Hub-first release: this push IS the release artifact.
# A version is not released until romwil/projectionist:X.Y.Z exists on Hub.
# GitHub merge / local Unraid docker build are NOT substitutes. See docs/RELEASE.md.
# Multi-arch Docker Hub release for Projectionist.
#
# Canonical image: romwil/projectionist
# Compat dual-tag (same digests): romwil/curatorx  — during ~2-release window
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
COMPAT_IMAGE="romwil/curatorx"
PLATFORMS="linux/amd64,linux/arm64"
BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
VCS_REF="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
DATE_STAMP="$(date -u +%Y%m%d)"

TAGS=(
  -t "${IMAGE}:${VERSION}"
  -t "${IMAGE}:${ALSO_LINE}"
  -t "${IMAGE}:latest"
)

if [[ "$DATE_TAG" -eq 1 ]]; then
  TAGS+=(-t "${IMAGE}:latest-${DATE_STAMP}")
fi

echo "Generating release notes from CHANGELOG.md (require ## [${VERSION}])"
./scripts/generate-release-notes.sh --require-version "${VERSION}"

echo "Building ${IMAGE}:${VERSION} (+ :${ALSO_LINE} :latest) for ${PLATFORMS}"
echo "Build identity: version=${VERSION} created=${BUILD_DATE} revision=${VCS_REF}"
echo "Flags: --provenance=false --sbom=false (Unraid-compatible Docker v2 manifests)"
echo "Compat dual-tag after push: ${COMPAT_IMAGE}:{${VERSION},${ALSO_LINE},latest}"

# buildx is always BuildKit; export for any nested classic docker and document intent.
# Cache mounts in the Dockerfile need BuildKit (npm/pip --mount=type=cache).
export DOCKER_BUILDKIT=1

docker buildx build \
  --platform "${PLATFORMS}" \
  --provenance=false \
  --sbom=false \
  --build-arg "PROJECTIONIST_VERSION=${VERSION}" \
  --build-arg "CURATORX_VERSION=${VERSION}" \
  --build-arg "BUILD_DATE=${BUILD_DATE}" \
  --build-arg "VCS_REF=${VCS_REF}" \
  "${TAGS[@]}" \
  --push \
  .

# Retag identical digests onto the legacy Hub name (compat window).
COMPAT_TAGS=(
  -t "${COMPAT_IMAGE}:${VERSION}"
  -t "${COMPAT_IMAGE}:${ALSO_LINE}"
  -t "${COMPAT_IMAGE}:latest"
)
if [[ "$DATE_TAG" -eq 1 ]]; then
  COMPAT_TAGS+=(-t "${COMPAT_IMAGE}:latest-${DATE_STAMP}")
fi

echo ""
echo "Dual-tagging identical manifests → ${COMPAT_IMAGE}:* (compat)"
docker buildx imagetools create \
  "${COMPAT_TAGS[@]}" \
  "${IMAGE}:${VERSION}"

echo ""
echo "=== Hub inspect (expect MediaType: docker.distribution.manifest.list.v2+json) ==="
docker buildx imagetools inspect "${IMAGE}:${VERSION}" | head -30

echo ""
echo "=== Digests (paste into release notes / Unraid verify) ==="
for ref in \
  "${IMAGE}:${VERSION}" \
  "${IMAGE}:latest" \
  "${COMPAT_IMAGE}:${VERSION}" \
  "${COMPAT_IMAGE}:latest"
do
  echo "Tag ${ref}:"
  docker buildx imagetools inspect "${ref}" --format '{{.Manifest.Digest}}' 2>/dev/null \
    || docker buildx imagetools inspect "${ref}" | awk '/^Digest:/{print $2; exit}'
done
if [[ "$DATE_TAG" -eq 1 ]]; then
  for ref in "${IMAGE}:latest-${DATE_STAMP}" "${COMPAT_IMAGE}:latest-${DATE_STAMP}"; do
    echo "Tag ${ref}:"
    docker buildx imagetools inspect "${ref}" --format '{{.Manifest.Digest}}' 2>/dev/null \
      || docker buildx imagetools inspect "${ref}" | awk '/^Digest:/{print $2; exit}'
  done
fi

echo ""
echo "Unraid owners: Force Update can report TOTAL DATA PULLED: 0 B when the local"
echo "  ${IMAGE}:latest (or ${COMPAT_IMAGE}:latest) tag is stale. Supported path:"
echo "  docker pull ${IMAGE}:latest"
echo "  # or: cd /mnt/user/appdata/curatorx && ./rollout.sh latest"
echo "  # or: ./scripts/unraid-force-pull.sh   (from a checkout / copied into appdata)"
echo "See docs/DOCKER.md and docs/wiki/Unraid.md."
