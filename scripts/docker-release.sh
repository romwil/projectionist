#!/usr/bin/env bash
# Multi-arch Docker Hub release for CuratorX.
# Builds linux/amd64 + linux/arm64 manifest lists with:
#   --provenance=false --sbom=false
#
# Usage:
#   ./scripts/docker-release.sh 1.3.0
#   ./scripts/docker-release.sh 1.3.0 --also-line 1.3
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

VERSION="${1:-}"
if [[ -z "$VERSION" || "$VERSION" == --* ]]; then
  echo "Usage: $0 <version> [--also-line X.Y]" >&2
  exit 1
fi
shift || true

ALSO_LINE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --also-line)
      ALSO_LINE="${2:-}"
      shift 2
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

TAGS=(
  -t "${IMAGE}:${VERSION}"
  -t "${IMAGE}:${ALSO_LINE}"
  -t "${IMAGE}:latest"
)

echo "Building ${IMAGE}:${VERSION} (+ :${ALSO_LINE} :latest) for ${PLATFORMS}"
echo "Flags: --provenance=false --sbom=false"

docker buildx build \
  --platform "${PLATFORMS}" \
  --provenance=false \
  --sbom=false \
  --build-arg "CURATORX_VERSION=${VERSION}" \
  "${TAGS[@]}" \
  --push \
  .

echo "Inspect (expect docker.distribution.manifest.list.v2+json):"
docker buildx imagetools inspect "${IMAGE}:${VERSION}" | head -20
