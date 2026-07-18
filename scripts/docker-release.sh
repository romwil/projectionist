#!/usr/bin/env bash
# Multi-arch Docker Hub release for CuratorX.
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

IMAGE="romwil/curatorx"
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

docker buildx build \
  --platform "${PLATFORMS}" \
  --provenance=false \
  --sbom=false \
  --build-arg "CURATORX_VERSION=${VERSION}" \
  --build-arg "BUILD_DATE=${BUILD_DATE}" \
  --build-arg "VCS_REF=${VCS_REF}" \
  "${TAGS[@]}" \
  --push \
  .

echo ""
echo "=== Hub inspect (expect MediaType: docker.distribution.manifest.list.v2+json) ==="
docker buildx imagetools inspect "${IMAGE}:${VERSION}" | head -30

echo ""
echo "=== Digests (paste into release notes / Unraid verify) ==="
echo "Tag ${IMAGE}:${VERSION}:"
docker buildx imagetools inspect "${IMAGE}:${VERSION}" --format '{{.Manifest.Digest}}' 2>/dev/null \
  || docker buildx imagetools inspect "${IMAGE}:${VERSION}" | awk '/^Digest:/{print $2; exit}'
echo "Tag ${IMAGE}:latest:"
docker buildx imagetools inspect "${IMAGE}:latest" --format '{{.Manifest.Digest}}' 2>/dev/null \
  || docker buildx imagetools inspect "${IMAGE}:latest" | awk '/^Digest:/{print $2; exit}'
if [[ "$DATE_TAG" -eq 1 ]]; then
  echo "Tag ${IMAGE}:latest-${DATE_STAMP}:"
  docker buildx imagetools inspect "${IMAGE}:latest-${DATE_STAMP}" --format '{{.Manifest.Digest}}' 2>/dev/null \
    || docker buildx imagetools inspect "${IMAGE}:latest-${DATE_STAMP}" | awk '/^Digest:/{print $2; exit}'
fi

echo ""
echo "Unraid owners: Force Update can report TOTAL DATA PULLED: 0 B when the local"
echo "  ${IMAGE}:latest tag is stale. Supported path:"
echo "  docker pull ${IMAGE}:latest"
echo "  # or: cd /mnt/user/appdata/curatorx && ./rollout.sh latest"
echo "  # or: ./scripts/unraid-force-pull.sh   (from a checkout / copied into appdata)"
echo "See docs/DOCKER.md and docs/wiki/Unraid.md."
