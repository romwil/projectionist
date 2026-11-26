#!/usr/bin/env bash
# PULL-ONLY from Docker Hub. Does not build images.
# Not a substitute for docker-release.sh. CA/Unraid proof = pull a Hub tag (docs/RELEASE.md).
# Do not use a host-built image as release proof.
# Projectionist Unraid rollout: pull + recreate via plain Docker CLI
# (stock Unraid has neither Compose v2 nor docker-compose).
# Prefer `docker compose` / `docker-compose` when available; otherwise
# fall back to `docker pull` + `docker run`.
# Does NOT wipe ./config (settings.json, SQLite, secrets).
#
# Canonical copy lives in the repo as scripts/unraid-rollout.sh — keep the
# host copy in sync after upgrades. Host appdata is rollout kit + ./config only
# (see docs/ops/AUTOMAT.md — do not git clone the full repo into appdata):
#   cp scripts/unraid-rollout.sh /mnt/user/appdata/projectionist/rollout.sh
#   cp docker-compose.unraid.yml /mnt/user/appdata/projectionist/docker-compose.yml
#   cp scripts/unraid.env.example /mnt/user/appdata/projectionist/.env.example
#   cp scripts/unraid-force-pull.sh /mnt/user/appdata/projectionist/unraid-force-pull.sh
# Legacy installs that never moved off /mnt/user/appdata/curatorx can keep that
# path (same scripts; override CONTAINER_NAME=curatorx if needed).
#
# For image-only refresh (keep Dockerman template, then Force Update):
#   ./unraid-force-pull.sh
#
# Usage (on Unraid host):
#   cd /mnt/user/appdata/projectionist
#   ./rollout.sh                     # romwil/projectionist:latest
#   ./rollout.sh 1.27.3              # pin a release tag
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
THEATER_HOST_PORT="${THEATER_HOST_PORT:-8791}"
# New installs / recreate prefer container name projectionist. Override if your
# Dockerman container is still named curatorx: CONTAINER_NAME=curatorx ./rollout.sh
CONTAINER_NAME="${CONTAINER_NAME:-projectionist}"
IMAGE="romwil/projectionist:${IMAGE_TAG}"
CONFIG_DIR="$SCRIPT_DIR/config"
# Host media libraries — rw so Investigate Apply can rename files. Automat defaults.
TV_MEDIA="${PROJECTIONIST_TV_MEDIA:-/mnt/user/data/media/tv}"
MOVIE_MEDIA="${PROJECTIONIST_MOVIE_MEDIA:-/mnt/user/data/media/movies}"
PREROLL_MEDIA="${PROJECTIONIST_PREROLL_MEDIA:-/mnt/user/data/media/preroll}"
_REQUESTED_DOCKER_SOCK="${DOCKER_SOCK:-}"
DOCKER_SOCK=""
HEALTH_URL="http://127.0.0.1:${HOST_PORT}/api/health"
READY_URL="http://127.0.0.1:${HOST_PORT}/api/ready"
APP_ORIGIN="http://127.0.0.1:${HOST_PORT}"
# App uid. docker exec without -u is root and can rewrite settings.json as root.
# At 05:22:53 UTC a rollout session ran `docker exec -i projectionist python -`
# as root. That process rewrote settings.json. Every docker exec here passes
# -u "$APP_UID". Do not drop it.
APP_UID=1000
STARTUP_PATTERN='Projectionist startup'
# Accept legacy log line during image transition
STARTUP_PATTERN_LEGACY='CuratorX startup'
WAIT_SECS="${ROLLOUT_WAIT_SECS:-90}"

log() { printf '%s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

# The Docker socket is root on the host. Refuse before any container is created.
if [[ -n "${MOUNT_DOCKER_SOCK:-}" || -n "${_REQUESTED_DOCKER_SOCK}" ]]; then
  die "Refusing to mount a Docker socket. Unset MOUNT_DOCKER_SOCK and DOCKER_SOCK. Use a Tunarr URL instead."
fi

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
  log "Stopping and removing container '$CONTAINER_NAME' (config bind mount preserved)..."
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
  ACRCLOUD_HOST ACRCLOUD_ACCESS_KEY ACRCLOUD_ACCESS_SECRET
  PROJECTIONIST_ACRCLOUD_HOST PROJECTIONIST_ACRCLOUD_ACCESS_KEY PROJECTIONIST_ACRCLOUD_ACCESS_SECRET
  PROJECTIONIST_OPENSUBTITLES_API_KEY OPENSUBTITLES_API_KEY
  LLM_PROVIDER LLM_BASE_URL LLM_API_KEY LLM_MODEL
  PROJECTIONIST_OWNER_USERNAME PROJECTIONIST_OWNER_PASSWORD
  PROJECTIONIST_SESSION_SECRET PROJECTIONIST_WEBHOOK_SECRET
  PROJECTIONIST_MCP_API_KEY PROJECTIONIST_MCP_FULL_API_KEY
  PROJECTIONIST_MCP_FULL_CONFIRM
  PROJECTIONIST_SECRETS_KEY
  PROJECTIONIST_LOG_LEVEL
  PROJECTIONIST_HOST_IP HOST_IP
  PROJECTIONIST_TUNARR_PUBLIC_URL PROJECTIONIST_TUNARR_HOST_PORT PROJECTIONIST_TUNARR_HDHR_PORT
  PROJECTIONIST_TUNARR_MEDIA_BINDS
  PROJECTIONIST_TV_MEDIA PROJECTIONIST_MOVIE_MEDIA PROJECTIONIST_PREROLL_MEDIA
  TV_ROOT MOVIES_ROOT PREROLL_ROOT
  CURATORX_OWNER_USERNAME CURATORX_OWNER_PASSWORD
  CURATORX_SESSION_SECRET CURATORX_WEBHOOK_SECRET
  CURATORX_MCP_API_KEY CURATORX_MCP_FULL_API_KEY
  CURATORX_MCP_FULL_CONFIRM
  CURATORX_LOG_LEVEL
  CURATORX_HOST_IP CURATORX_TUNARR_PUBLIC_URL
)

run_plain_docker() {
  export IMAGE_TAG
  log "Using plain Docker CLI (compose not available)."
  log "Pulling $IMAGE..."
  docker pull "$IMAGE"

  stop_rm_container

  local -a run_args=(
    -d
    --name "$CONTAINER_NAME"
    --restart unless-stopped
    -p "${HOST_PORT}:8788"
    -p "${THEATER_HOST_PORT}:8791"
    -v "${CONFIG_DIR}:/config"
    --add-host=host.docker.internal:host-gateway
  )
  _mount_media_rw() {
    local host_path="$1" container_path="$2" label="$3"
    if [[ ! -d "$host_path" ]]; then
      log "WARN: $label host path missing ($host_path) — skipping bind (Investigate cannot rename under $container_path)."
      return 0
    fi
    log "Mounting $label $host_path → $container_path (rw)"
    run_args+=(-v "${host_path}:${container_path}")
    if [[ "$host_path" != "$container_path" ]]; then
      log "Mounting $label same-path $host_path → $host_path (rw)"
      run_args+=(-v "${host_path}:${host_path}")
    fi
  }
  _mount_media_rw "$TV_MEDIA" /tv "TV library"
  _mount_media_rw "$MOVIE_MEDIA" /movies "Movie library"
  _mount_media_rw "$PREROLL_MEDIA" /preroll "Preroll bumpers"
  run_args+=(
    -e "PROJECTIONIST_TV_MEDIA=${TV_MEDIA}"
    -e "PROJECTIONIST_MOVIE_MEDIA=${MOVIE_MEDIA}"
    -e "PROJECTIONIST_PREROLL_MEDIA=${PREROLL_MEDIA}"
    -e DATA_DIR=/config
    -e PORT=8788
    -e PROJECTIONIST_THEATER_PORT=8791
    -e "PROJECTIONIST_HOST_DATA_DIR=${CONFIG_DIR}"
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

  log "Starting container..."
  docker run "${run_args[@]}" "$IMAGE"
}

run_compose() {
  export IMAGE_TAG
  [[ -f "$SCRIPT_DIR/docker-compose.yml" ]] || die "docker-compose.yml missing in $SCRIPT_DIR"

  # If a container exists but was not created by this compose project, remove
  # it first (container only — bind-mounted ./config untouched).
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
  log "Pulling image..."
  "${COMPOSE[@]}" pull projectionist
  log "Recreating container (force-recreate; config untouched)..."
  "${COMPOSE[@]}" up -d --force-recreate --remove-orphans projectionist
}

wait_for_startup_log() {
  local deadline=$((SECONDS + WAIT_SECS))
  local logs=""
  while (( SECONDS < deadline )); do
    if docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME" 2>/dev/null | grep -qx true; then
      logs="$(docker logs --tail 80 "$CONTAINER_NAME" 2>&1 || true)"
      if printf '%s\n' "$logs" | grep -qE "${STARTUP_PATTERN}|${STARTUP_PATTERN_LEGACY}"; then
        printf '%s\n' "$logs" | grep -E "${STARTUP_PATTERN}|${STARTUP_PATTERN_LEGACY}|build" | tail -5
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
  die "timed out after ${WAIT_SECS}s waiting for startup log matching /${STARTUP_PATTERN}/"
}

fetch_url() {
  local url="$1"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 5 "$url" 2>/dev/null || true
    return 0
  fi
  if command -v wget >/dev/null 2>&1; then
    wget -qO- --timeout=5 "$url" 2>/dev/null || true
    return 0
  fi
  docker exec -u "$APP_UID" "$CONTAINER_NAME" python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8788${url#${APP_ORIGIN}}', timeout=5).read().decode())" 2>/dev/null || true
}

smoke_ready() {
  local deadline=$((SECONDS + 30))
  local body=""
  while (( SECONDS < deadline )); do
    body="$(fetch_url "$READY_URL")"
    if [[ -n "$body" ]] && printf '%s' "$body" | grep -q '"status"[[:space:]]*:[[:space:]]*"ready"'; then
      log "Ready: $body"
      return 0
    fi
    sleep 2
  done
  log "Last ready body: ${body:-<empty>}"
  die "ready check failed: $READY_URL (health is not enough; the app must be able to read and write settings and the database)"
}

smoke_signed_in() {
  local user="${PROJECTIONIST_SMOKE_USERNAME:-}"
  local pass="${PROJECTIONIST_SMOKE_PASSWORD:-}"
  if [[ -z "$user" || -z "$pass" ]]; then
    die "Refusing to report success without a signed-in smoke. Set PROJECTIONIST_SMOKE_USERNAME and PROJECTIONIST_SMOKE_PASSWORD in the host environment. No account was created."
  fi
  command -v curl >/dev/null 2>&1 || die "Signed-in smoke needs curl on the host."
  command -v python >/dev/null 2>&1 || command -v python3 >/dev/null 2>&1 || die "Signed-in smoke needs python on the host."
  local py="python3"
  command -v python3 >/dev/null 2>&1 || py="python"
  local work
  work="$(mktemp -d)"
  # shellcheck disable=SC2064
  trap "rm -rf '$work'" RETURN
  local login_code
  login_code="$(
    PROJECTIONIST_SMOKE_USERNAME="$user" PROJECTIONIST_SMOKE_PASSWORD="$pass" "$py" -c 'import json,os; print(json.dumps({"username":os.environ["PROJECTIONIST_SMOKE_USERNAME"],"password":os.environ["PROJECTIONIST_SMOKE_PASSWORD"]}))' \
      | curl -sS -o "$work/login" -w '%{http_code}' -c "$work/cookies" -H 'Content-Type: application/json' --data-binary @- \
        "$APP_ORIGIN/api/auth/local/login" || true
  )"
  if [[ "$login_code" != "200" ]]; then
    if grep -q "sign-in code" "$work/login" 2>/dev/null; then
      rm -rf "$work"
      die "Signed-in smoke stopped: this account requires a sign-in code. PROJECTIONIST_SMOKE_USERNAME can sign in only as far as that code, so the rollout will not report success."
    fi
    rm -rf "$work"
    die "Signed-in smoke failed: local login returned HTTP ${login_code:-none}."
  fi
  local features_code
  features_code="$(curl -sS -o "$work/features" -w '%{http_code}' -b "$work/cookies" --max-time 20 "$APP_ORIGIN/api/features" || true)"
  if [[ "$features_code" != "200" ]]; then
    rm -rf "$work"
    die "Signed-in smoke failed: features returned HTTP ${features_code:-none}."
  fi
  if ! "$py" -c '
import json, sys
data = json.load(open(sys.argv[1]))
features = data.get("features") or {}
provider = features.get("llm_provider")
if data.get("authenticated") is not True:
    sys.exit("features is not signed in")
if not isinstance(provider, str) or not provider.strip():
    sys.exit("features did not show a chat provider")
if "live_channels_enabled" not in features:
    sys.exit("features did not show live channels")
' "$work/features"; then
    rm -rf "$work"
    die "Signed-in smoke failed: features did not show the chat provider and live channels."
  fi
  local rail_code
  rail_code="$(curl -sS -o "$work/rail" -w '%{http_code}' -b "$work/cookies" --max-time 60 "$APP_ORIGIN/api/library/feeds/hub" || true)"
  if [[ "$rail_code" != "200" ]]; then
    rm -rf "$work"
    die "Signed-in smoke failed: the hub rail returned HTTP ${rail_code:-none}."
  fi
  log "Signed-in smoke: features show the chat provider and live channels, and the hub rail returned 200."
}

# Root-only credentials for the signed-in smoke. Not the app .env, and not
# /boot: the flash is FAT32, so mode 600 is not real there, and Unraid Connect
# may back the flash up. This directory is outside the container /config bind
# and outside git. Fail before the container is replaced.
require_smoke_env() {
  local smoke_env="${PROJECTIONIST_SMOKE_ENV:-/mnt/user/appdata/projectionist-secrets/smoke.env}"
  local smoke_dir
  smoke_dir="$(dirname "$smoke_env")"
  if [[ ! -f "$smoke_env" ]]; then
    die "Smoke env file is missing at ${smoke_env}. Refusing to replace the container."
  fi
  local smoke_mode smoke_owner dir_mode dir_owner
  smoke_mode="$(stat -c '%a' "$smoke_env")"
  smoke_owner="$(stat -c '%u' "$smoke_env")"
  dir_mode="$(stat -c '%a' "$smoke_dir")"
  dir_owner="$(stat -c '%u' "$smoke_dir")"
  if [[ "$dir_mode" != "700" || "$dir_owner" != "0" ]]; then
    die "Smoke env directory ${smoke_dir} must be mode 700 and owned by root. Refusing to replace the container."
  fi
  if [[ "$smoke_mode" != "600" || "$smoke_owner" != "0" ]]; then
    die "Smoke env ${smoke_env} must be mode 600 and owned by root. Refusing to replace the container."
  fi
  set -a
  # shellcheck disable=SC1090
  source "$smoke_env"
  set +a
  if [[ -z "${PROJECTIONIST_SMOKE_USERNAME:-}" || -z "${PROJECTIONIST_SMOKE_PASSWORD:-}" ]]; then
    die "Smoke env ${smoke_env} is missing a username or password. Refusing to replace the container."
  fi
  log "Smoke env ${smoke_env} is mode 600, owned by root. Username: ${PROJECTIONIST_SMOKE_USERNAME}."
}

log "=== Projectionist rollout ==="
log "Dir:   $SCRIPT_DIR"
log "Image: $IMAGE"
log "Port:  ${HOST_PORT} → 8788"
log "Theater port: ${THEATER_HOST_PORT} → 8791 (LAN only)"
log "Docker socket: not mounted"
log "Config bind: $CONFIG_DIR → /config (preserved)"
log "TV library (rw): $TV_MEDIA → /tv (and same-path when host dir exists)"
log "Movie library (rw): $MOVIE_MEDIA → /movies (and same-path when host dir exists)"
log "Preroll bumpers (rw): $PREROLL_MEDIA → /preroll (and same-path when host dir exists)"
log "Host data dir (Tunarr binds): PROJECTIONIST_HOST_DATA_DIR=$CONFIG_DIR"
require_smoke_env

if ((${#COMPOSE[@]})); then
  run_compose
else
  run_plain_docker
fi

log "Waiting for startup confirmation..."
wait_for_startup_log

log "Ready check..."
smoke_ready
log "Signed-in smoke..."
smoke_signed_in

if docker exec -u "$APP_UID" "$CONTAINER_NAME" cat /app/.build-info >/dev/null 2>&1; then
  log "Build info:"
  docker exec -u "$APP_UID" "$CONTAINER_NAME" cat /app/.build-info || true
fi

log "=== Rollout OK (tag=${IMAGE_TAG}) ==="
