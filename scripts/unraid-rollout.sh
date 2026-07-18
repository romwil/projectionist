#!/usr/bin/env bash
# CuratorX Unraid rollout: pull + recreate via plain Docker CLI
# (stock Unraid has neither Compose v2 nor docker-compose).
# Prefer `docker compose` / `docker-compose` when available; otherwise
# fall back to `docker pull` + `docker run`.
# Does NOT wipe ./config (settings.json, SQLite, secrets).
#
# Canonical copy lives in the repo as scripts/unraid-rollout.sh — keep
# /mnt/user/appdata/curatorx/rollout.sh in sync after upgrades:
#   cp scripts/unraid-rollout.sh /mnt/user/appdata/curatorx/rollout.sh
#
# For image-only refresh (keep Dockerman template, then Force Update):
#   ./scripts/unraid-force-pull.sh
#
# Usage (on Unraid host):
#   cd /mnt/user/appdata/curatorx
#   ./rollout.sh           # romwil/curatorx:latest
#   ./rollout.sh 1.8.11    # pin a release tag
#
# First migration from an Unraid dockerman-managed container: this script
# removes a same-named container (stop/rm only; never docker volume rm /
# never touches the ./config bind mount).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Optional seed env (Compose-style). Do not invent secrets here.
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
  set +a
fi

IMAGE_TAG="${1:-${IMAGE_TAG:-latest}}"
HOST_PORT="${HOST_PORT:-8788}"
CONTAINER_NAME="curatorx"
IMAGE="romwil/curatorx:${IMAGE_TAG}"
CONFIG_DIR="$SCRIPT_DIR/config"
HEALTH_URL="http://127.0.0.1:${HOST_PORT}/api/health"
STARTUP_PATTERN='CuratorX startup'
WAIT_SECS="${ROLLOUT_WAIT_SECS:-90}"

log() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "docker not found in PATH"
[[ -d "$CONFIG_DIR" ]] || die "config directory missing at $CONFIG_DIR (refusing to create empty tree)"

# Detect optional compose (not required on Unraid).
COMPOSE=()
if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
fi

stop_rm_container() {
  if ! docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    return 0
  fi
  log "Stopping and removing container '$CONTAINER_NAME' (config bind mount preserved)…"
  docker stop "$CONTAINER_NAME" >/dev/null || true
  docker rm "$CONTAINER_NAME" >/dev/null
  log "Removed container '$CONTAINER_NAME'."
}

# Env keys mirrored from docker-compose.yml (passed only when set / non-empty
# so unset secrets still auto-generate under ./config).
ENV_KEYS=(
  TZ
  PLEX_URL PLEX_TOKEN
  RADARR_URL RADARR_API_KEY
  SONARR_URL SONARR_API_KEY
  TMDB_API_KEY FANART_API_KEY
  TAUTULLI_URL TAUTULLI_API_KEY
  LLM_PROVIDER LLM_BASE_URL LLM_API_KEY LLM_MODEL
  CURATORX_SESSION_SECRET CURATORX_WEBHOOK_SECRET
  CURATORX_MCP_API_KEY CURATORX_MCP_FULL_API_KEY
  CURATORX_LOG_LEVEL
)

run_plain_docker() {
  export IMAGE_TAG
  log "Using plain Docker CLI (compose not available)."
  log "Pulling $IMAGE…"
  docker pull "$IMAGE"

  stop_rm_container

  local -a run_args=(
    -d
    --name "$CONTAINER_NAME"
    --restart unless-stopped
    -p "${HOST_PORT}:8788"
    -v "${CONFIG_DIR}:/config"
    --add-host=host.docker.internal:host-gateway
    -e DATA_DIR=/config
    -e PORT=8788
  )

  local key val
  for key in "${ENV_KEYS[@]}"; do
    # Portable under bash 3.2+ / set -u: read only if set & non-empty.
    eval "val=\"\${$key-}\""
    if [[ -n "$val" ]]; then
      run_args+=(-e "${key}=${val}")
    fi
  done
  # TZ defaults to UTC when unset (matches compose ${TZ:-UTC})
  eval "val=\"\${TZ-}\""
  if [[ -z "$val" ]]; then
    run_args+=(-e TZ=UTC)
  fi

  log "Starting container…"
  docker run "${run_args[@]}" "$IMAGE"
}

run_compose() {
  export IMAGE_TAG
  [[ -f "$SCRIPT_DIR/docker-compose.yml" ]] || die "docker-compose.yml missing in $SCRIPT_DIR"

  # If a container named curatorx exists but was not created by this compose
  # project, remove it first (container only — bind-mounted ./config untouched).
  if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
    local project working_dir expected
    project="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$CONTAINER_NAME" 2>/dev/null || true)"
    working_dir="$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "$CONTAINER_NAME" 2>/dev/null || true)"
    expected="${SCRIPT_DIR%/}"
    working_dir="${working_dir%/}"
    if [[ -z "$project" || -z "$working_dir" || "$working_dir" != "$expected" ]]; then
      log "Container '$CONTAINER_NAME' exists but is not managed by this compose project."
      stop_rm_container
    else
      log "Existing compose-managed container found (project=$project)."
    fi
  fi

  log "Using ${COMPOSE[*]}."
  log "Pulling image…"
  "${COMPOSE[@]}" pull curatorx
  log "Recreating container (force-recreate; config untouched)…"
  "${COMPOSE[@]}" up -d --force-recreate --remove-orphans curatorx
}

wait_for_startup_log() {
  local deadline=$((SECONDS + WAIT_SECS))
  local logs=""
  while (( SECONDS < deadline )); do
    if docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null | grep -qx true; then
      logs="$(docker logs --tail 80 "$CONTAINER_NAME" 2>&1 || true)"
      if printf '%s\n' "$logs" | grep -q "$STARTUP_PATTERN"; then
        printf '%s\n' "$logs" | grep -E "$STARTUP_PATTERN|build" | tail -5
        return 0
      fi
    else
      if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
        local status
        status="$(docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || true)"
        if [[ "$status" == "exited" || "$status" == "dead" ]]; then
          docker logs --tail 80 "$CONTAINER_NAME" 2>&1 || true
          die "container exited during startup (status=$status)"
        fi
      fi
    fi
    sleep 2
  done
  docker logs --tail 80 "$CONTAINER_NAME" 2>&1 || true
  die "timed out after ${WAIT_SECS}s waiting for startup log matching /$STARTUP_PATTERN/"
}

smoke_health() {
  local deadline=$((SECONDS + 30))
  local body=""
  while (( SECONDS < deadline )); do
    if command -v curl >/dev/null 2>&1; then
      body="$(curl -fsS --max-time 5 "$HEALTH_URL" 2>/dev/null || true)"
      if [[ -n "$body" ]]; then
        log "Health: $body"
        printf '%s' "$body" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' || die "health JSON missing status=ok"
        return 0
      fi
    elif command -v wget >/dev/null 2>&1; then
      body="$(wget -qO- --timeout=5 "$HEALTH_URL" 2>/dev/null || true)"
      if [[ -n "$body" ]]; then
        log "Health: $body"
        printf '%s' "$body" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' || die "health JSON missing status=ok"
        return 0
      fi
    else
      if docker exec "$CONTAINER_NAME" wget -qO- --timeout=5 "http://127.0.0.1:8788/api/health" 2>/dev/null \
        || docker exec "$CONTAINER_NAME" python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8788/api/health', timeout=5).read().decode())" 2>/dev/null; then
        return 0
      fi
    fi
    sleep 2
  done
  die "health check failed: $HEALTH_URL"
}

log "=== CuratorX rollout ==="
log "Dir:   $SCRIPT_DIR"
log "Image: $IMAGE"
log "Port:  ${HOST_PORT} → 8788"
log "Config bind: $CONFIG_DIR → /config (preserved)"

if ((${#COMPOSE[@]})); then
  run_compose
else
  run_plain_docker
fi

log "Waiting for startup confirmation…"
wait_for_startup_log

log "Smoke check…"
smoke_health

if docker exec "$CONTAINER_NAME" cat /app/.build-info >/dev/null 2>&1; then
  log "Build info:"
  docker exec "$CONTAINER_NAME" cat /app/.build-info || true
fi

log "=== Rollout OK (tag=${IMAGE_TAG}) ==="
