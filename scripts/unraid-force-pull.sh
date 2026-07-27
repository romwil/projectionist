#!/usr/bin/env bash
# Explicit Hub re-resolve for Projectionist on Unraid / Dockerman hosts.
#
# Why this exists: Docker → Force Update calls Engine pull, then recreates the
# container. When Engine reports the local tag as already current, the UI shows
# TOTAL DATA PULLED: 0 B and recreates from the stale local
# romwil/projectionist:latest (or dual-tagged romwil/curatorx:latest) mapping —
# even when Hub :latest has moved (buildx on another machine shows the new
# digest). This script forces a CLI pull and verifies RepoDigests moved;
# optional --rmi-retry deletes the local tag first.
#
# Does NOT wipe /config. Prefer ./rollout.sh in appdata for pull+recreate in one
# step; use this when you want to keep Dockerman's container definition and only
# refresh the image before Force Update / Apply in the UI.
#
# Host appdata path: /mnt/user/appdata/projectionist (legacy …/curatorx OK if
# you never migrated). Prefer ./rollout.sh for pull+recreate in one step.
#
# Usage (on Unraid host, from appdata or repo checkout):
#   ./unraid-force-pull.sh              # pull :latest, print digests
#   ./unraid-force-pull.sh 1.27.3       # pull a pinned tag
#   ./unraid-force-pull.sh latest --rmi-retry
#   ./unraid-force-pull.sh latest --recreate   # stop/rm + instruct template start
#
set -euo pipefail

IMAGE_TAG="${1:-latest}"
shift || true
RMI_RETRY=0
RECREATE=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --rmi-retry) RMI_RETRY=1; shift ;;
    --recreate)  RECREATE=1; shift ;;
    *)
      echo "Unknown arg: $1" >&2
      echo "Usage: $0 [tag] [--rmi-retry] [--recreate]" >&2
      exit 1
      ;;
  esac
done

# Canonical Hub name; dual-tagged romwil/curatorx:* shares digests during compat.
# Override repo if needed: IMAGE_REPO=romwil/curatorx ./scripts/unraid-force-pull.sh
IMAGE_REPO="${IMAGE_REPO:-romwil/projectionist}"
IMAGE="${IMAGE_REPO}:${IMAGE_TAG}"
# Default container name for new installs; override for legacy Dockerman names:
#   CONTAINER_NAME=curatorx ./scripts/unraid-force-pull.sh
CONTAINER_NAME="${CONTAINER_NAME:-projectionist}"

log() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker not found in PATH"

digest_of() {
  local ref="$1"
  docker image inspect "$ref" --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{end}}' 2>/dev/null || true
}

image_id_of() {
  local ref="$1"
  docker image inspect "$ref" --format '{{.Id}}' 2>/dev/null || true
}

BEFORE_DIGEST="$(digest_of "$IMAGE")"
BEFORE_ID="$(image_id_of "$IMAGE")"

log "=== Projectionist force-pull ==="
log "Image: $IMAGE"
log "Before RepoDigest: ${BEFORE_DIGEST:-<none>}"
log "Before Image ID:   ${BEFORE_ID:-<none>}"

pull_once() {
  log "Pulling $IMAGE…"
  docker pull "$IMAGE"
}

pull_once

AFTER_DIGEST="$(digest_of "$IMAGE")"
AFTER_ID="$(image_id_of "$IMAGE")"

log "After RepoDigest:  ${AFTER_DIGEST:-<none>}"
log "After Image ID:    ${AFTER_ID:-<none>}"

if [[ -n "$BEFORE_DIGEST" && -n "$AFTER_DIGEST" && "$BEFORE_DIGEST" == "$AFTER_DIGEST" ]]; then
  log ""
  log "Digest unchanged after pull (Engine still maps this tag to the same content)."
  if [[ "$RMI_RETRY" -eq 1 ]]; then
    log "--rmi-retry: removing local tag/image so the next pull must fetch from Hub…"
    if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
      log "Stopping/removing container '$CONTAINER_NAME' first (config bind mount preserved)…"
      docker stop "$CONTAINER_NAME" >/dev/null || true
      docker rm "$CONTAINER_NAME" >/dev/null || true
    fi
    docker rmi "$IMAGE" >/dev/null 2>&1 || docker rmi "$(image_id_of "$IMAGE")" >/dev/null 2>&1 || true
    pull_once
    AFTER_DIGEST="$(digest_of "$IMAGE")"
    AFTER_ID="$(image_id_of "$IMAGE")"
    log "After rmi+pull RepoDigest: ${AFTER_DIGEST:-<none>}"
    log "After rmi+pull Image ID:   ${AFTER_ID:-<none>}"
    if [[ -n "$BEFORE_DIGEST" && -n "$AFTER_DIGEST" && "$BEFORE_DIGEST" == "$AFTER_DIGEST" ]]; then
      die "still the same digest after rmi+pull — Hub tag may not have moved (check: docker buildx imagetools inspect $IMAGE)"
    fi
  else
    log "If Hub should be newer, re-run with --rmi-retry, or:"
    log "  docker stop $CONTAINER_NAME && docker rm $CONTAINER_NAME"
    log "  docker rmi $IMAGE && docker pull $IMAGE"
    log "Then start from Docker → User Templates → projectionist (or appdata ./rollout.sh)."
  fi
else
  log "Digest/ID moved (or first pull) — local tag now tracks Hub."
fi

if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1 && docker exec "$CONTAINER_NAME" cat /app/.build-info >/dev/null 2>&1; then
  log "Running container build-info (may still be old until recreate):"
  docker exec "$CONTAINER_NAME" cat /app/.build-info || true
fi

if [[ "$RECREATE" -eq 1 ]]; then
  if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    log "Stopping/removing container '$CONTAINER_NAME' (config preserved)…"
    docker stop "$CONTAINER_NAME" >/dev/null || true
    docker rm "$CONTAINER_NAME" >/dev/null || true
  fi
  log "Container removed. Start again from Docker → User Templates → projectionist"
  log "(or: cd /mnt/user/appdata/projectionist && ./rollout.sh ${IMAGE_TAG})"
else
  log ""
  log "Next: Docker UI → projectionist → Force Update / Apply"
  log "  (recreates from the refreshed local tag; keeps Dockerman template)"
  log "Or: cd /mnt/user/appdata/projectionist && ./rollout.sh ${IMAGE_TAG}"
fi

log "Verify after recreate: docker exec $CONTAINER_NAME cat /app/.build-info"
log "=== force-pull done ==="
