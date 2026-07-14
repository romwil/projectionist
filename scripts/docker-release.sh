#!/usr/bin/env bash
# Multi-arch Docker Hub release for CuratorX.
#
# IMPORTANT: Unraid's update checker fails on OCI image indexes / attestation
# manifests (shows "not available" and Force Update may use the local cache).
# Always push Docker v2 schema 2 manifests: disable provenance + SBOM.
#
# Usage:
#   ./scripts/docker-release.sh 1.2.0
#   ./scripts/docker-release.sh 1.2.0 --also-line 1.2
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
echo "Flags: --provenance=false --sbom=false (Unraid-compatible Docker manifests)"

docker buildx build \
  --platform "${PLATFORMS}" \
  --provenance=false \
  --sbom=false \
  "${TAGS[@]}" \
  --push \
  .

echo "Inspect (expect docker.distribution.manifest.list.v2+json, not oci.image.index):"
docker buildx imagetools inspect "${IMAGE}:${VERSION}" | head -20
