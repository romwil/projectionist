#!/usr/bin/env bash
# Seed a multi-user QA sidecar with owner / member / youth (+ optional guest role).
#
# Auth stays ON. Guest *tour* is passwordless at /tour when guest_tour is enabled.
# Guest *role* is an optional logged-in account with role=guest (guest shell).
#
# Usage:
#   cp .env.qa.example .env.qa   # fill secrets
#   bash scripts/seed-qa-roles.sh --write-settings --config-dir ./config-qa
#   docker compose -f docker-compose.qa.yml --env-file .env.qa up -d
#   bash scripts/seed-qa-roles.sh --base-url http://10.10.1.202:8790 --env-file .env.qa
#
# One-shot curls (after settings + health) are printed with --dry-run-curls.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE=""
BASE_URL=""
CONFIG_DIR=""
WRITE_SETTINGS=0
SEED_USERS=1
DRY_RUN_CURLS=0
SEED_GUEST_ROLE=""

usage() {
  sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="${2:-}"; shift 2 ;;
    --base-url) BASE_URL="${2:-}"; shift 2 ;;
    --config-dir) CONFIG_DIR="${2:-}"; shift 2 ;;
    --write-settings) WRITE_SETTINGS=1; shift ;;
    --settings-only) WRITE_SETTINGS=1; SEED_USERS=0; shift ;;
    --dry-run-curls) DRY_RUN_CURLS=1; shift ;;
    --no-guest-role) SEED_GUEST_ROLE=0; shift ;;
    -h|--help) usage 0 ;;
    *) echo "Unknown arg: $1" >&2; usage 1 ;;
  esac
done

load_env() {
  local file="$1"
  [[ -f "$file" ]] || { echo "Env file not found: $file" >&2; exit 1; }
  set -a
  # shellcheck disable=SC1090
  source "$file"
  set +a
}

if [[ -n "$ENV_FILE" ]]; then
  load_env "$ENV_FILE"
elif [[ -f "$ROOT/.env.qa" ]]; then
  load_env "$ROOT/.env.qa"
fi

BASE_URL="${BASE_URL:-${QA_BASE_URL:-http://127.0.0.1:8790}}"
BASE_URL="${BASE_URL%/}"
CONFIG_DIR="${CONFIG_DIR:-${QA_CONFIG_PATH:-$ROOT/config-qa}}"

OWNER_USER="${QA_OWNER_USER:-qa-owner}"
OWNER_PASS="${QA_OWNER_PASSWORD:-}"
MEMBER_USER="${QA_MEMBER_USER:-qa-member}"
MEMBER_PASS="${QA_MEMBER_PASSWORD:-}"
YOUTH_USER="${QA_YOUTH_USER:-qa-youth}"
YOUTH_PASS="${QA_YOUTH_PASSWORD:-}"
GUEST_USER="${QA_GUEST_USER:-qa-guest}"
GUEST_PASS="${QA_GUEST_PASSWORD:-}"
if [[ -z "$SEED_GUEST_ROLE" ]]; then
  SEED_GUEST_ROLE="${QA_SEED_GUEST_ROLE:-1}"
fi

write_settings() {
  mkdir -p "$CONFIG_DIR"
  local path="$CONFIG_DIR/settings.json"
  if [[ -f "$path" ]]; then
    echo "settings.json already exists at $path — leaving in place (edit manually or delete to regenerate)."
    return 0
  fi
  cat >"$path" <<'EOF'
{
  "features": {
    "multi_user_enabled": true,
    "seerr_enabled": false,
    "plex_collections_enabled": false,
    "guest_tour_enabled": true
  },
  "auth": {
    "mode": "local",
    "plex_login_enabled": false,
    "oidc_enabled": false,
    "local_login_enabled": true
  },
  "youth": {
    "max_content_rating": "PG-13"
  },
  "llm_provider": "openai_compatible",
  "onboarding_complete": true
}
EOF
  echo "Wrote QA settings → $path"
  echo "  multi_user_enabled=true  local_login_enabled=true  plex/SSO off  guest_tour_enabled=true"
}

print_curls() {
  cat <<EOF
# --- Manual bootstrap curls (auth ON; passwords from .env.qa) ---
# 1) First local user becomes owner (no session required):
curl -sS -c /tmp/cx-qa-owner.jar -X POST "$BASE_URL/api/auth/local/register" \\
  -H 'Content-Type: application/json' \\
  -d '{"username":"$OWNER_USER","password":"***"}'

# 2) Create member (owner session cookie required):
curl -sS -b /tmp/cx-qa-owner.jar -c /tmp/cx-qa-owner.jar -X POST "$BASE_URL/api/auth/local/register" \\
  -H 'Content-Type: application/json' \\
  -d '{"username":"$MEMBER_USER","password":"***"}'

# 3) Create youth local user, then flag is_youth:
curl -sS -b /tmp/cx-qa-owner.jar -c /tmp/cx-qa-owner.jar -X POST "$BASE_URL/api/auth/local/register" \\
  -H 'Content-Type: application/json' \\
  -d '{"username":"$YOUTH_USER","password":"***"}'
# Capture user id from response or GET /api/users, then:
curl -sS -b /tmp/cx-qa-owner.jar -X PATCH "$BASE_URL/api/users/<YOUTH_USER_ID>" \\
  -H 'Content-Type: application/json' \\
  -d '{"is_youth":true}'

# 4) Optional logged-in guest role (guest shell). Public tour needs no password:
#    open $BASE_URL/tour
curl -sS -b /tmp/cx-qa-owner.jar -X POST "$BASE_URL/api/auth/local/register" \\
  -H 'Content-Type: application/json' \\
  -d '{"username":"$GUEST_USER","password":"***"}'
curl -sS -b /tmp/cx-qa-owner.jar -X PATCH "$BASE_URL/api/users/<GUEST_USER_ID>" \\
  -H 'Content-Type: application/json' \\
  -d '{"role":"guest"}'

# Login later:
curl -sS -c /tmp/cx-qa.jar -X POST "$BASE_URL/api/auth/local/login" \\
  -H 'Content-Type: application/json' \\
  -d '{"username":"$OWNER_USER","password":"***"}'
EOF
}

json_get() {
  # Minimal JSON field extract without jq dependency (string or bool).
  local key="$1"
  python3 -c '
import json,sys
key=sys.argv[1]
data=json.load(sys.stdin)
cur=data
for part in key.split("."):
    if cur is None: break
    if isinstance(cur, dict):
        cur=cur.get(part)
    else:
        cur=None
        break
if isinstance(cur, (dict, list)):
    print(json.dumps(cur))
elif cur is None:
    print("")
else:
    print(cur)
' "$key"
}

require_passwords() {
  local missing=0
  for pair in "QA_OWNER_PASSWORD:$OWNER_PASS" "QA_MEMBER_PASSWORD:$MEMBER_PASS" "QA_YOUTH_PASSWORD:$YOUTH_PASS"; do
    local name="${pair%%:*}" val="${pair#*:}"
    if [[ -z "$val" || "$val" == change-me-* ]]; then
      echo "Set a real $name in .env.qa (placeholder rejected)." >&2
      missing=1
    fi
  done
  if [[ "$SEED_GUEST_ROLE" == "1" ]]; then
    if [[ -z "$GUEST_PASS" || "$GUEST_PASS" == change-me-* ]]; then
      echo "Set QA_GUEST_PASSWORD or pass --no-guest-role." >&2
      missing=1
    fi
  fi
  [[ "$missing" -eq 0 ]] || exit 1
}

wait_health() {
  local i
  for i in $(seq 1 60); do
    if curl -fsS "$BASE_URL/api/health" >/dev/null 2>&1; then
      echo "Healthy: $BASE_URL/api/health"
      return 0
    fi
    sleep 1
  done
  echo "Timed out waiting for $BASE_URL/api/health" >&2
  exit 1
}

cookie_jar="$(mktemp -t cx-qa-XXXXXX.jar)"
trap 'rm -f "$cookie_jar"' EXIT

api() {
  local method="$1" path="$2" data="${3:-}"
  if [[ -n "$data" ]]; then
    curl -sS -b "$cookie_jar" -c "$cookie_jar" -X "$method" "$BASE_URL$path" \
      -H 'Content-Type: application/json' -d "$data"
  else
    curl -sS -b "$cookie_jar" -c "$cookie_jar" -X "$method" "$BASE_URL$path"
  fi
}

register_or_login() {
  local user="$1" pass="$2"
  local body resp
  body=$(printf '{"username":%s,"password":%s}' "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$user")" "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$pass")")
  resp=$(api POST /api/auth/local/register "$body" || true)
  if echo "$resp" | grep -q '"authenticated"[[:space:]]*:[[:space:]]*true'; then
    echo "Registered $user (role=$(echo "$resp" | json_get user.role))"
    echo "$resp"
    return 0
  fi
  # Already exists → login
  resp=$(api POST /api/auth/local/login "$body")
  if echo "$resp" | grep -q '"authenticated"[[:space:]]*:[[:space:]]*true'; then
    echo "Logged in existing $user (role=$(echo "$resp" | json_get user.role))"
    echo "$resp"
    return 0
  fi
  echo "Failed to register/login $user: $resp" >&2
  exit 1
}

find_user_id() {
  local name="$1"
  api GET /api/users | python3 -c '
import json,sys
name=sys.argv[1]
payload=json.load(sys.stdin)
items=payload.get("users") or payload.get("items") or payload
if isinstance(items, dict):
    items=items.get("users") or items.get("items") or []
for u in items:
    if str(u.get("display_name") or "") == name:
        print(u.get("id") or "")
        break
' "$name"
}

if [[ "$WRITE_SETTINGS" -eq 1 ]]; then
  write_settings
fi

if [[ "$DRY_RUN_CURLS" -eq 1 ]]; then
  print_curls
  exit 0
fi

if [[ "$SEED_USERS" -eq 0 ]]; then
  exit 0
fi

require_passwords
wait_health

features=$(curl -fsS "$BASE_URL/api/features" || true)
multi=$(echo "$features" | json_get features.multi_user_enabled)
local_on=$(echo "$features" | json_get auth.local_login_enabled)
guest_on=$(echo "$features" | json_get features.guest_tour_enabled)
echo "features: multi_user=$multi local_login=$local_on guest_tour=$guest_on"
if [[ "$multi" != "True" && "$multi" != "true" ]]; then
  echo "multi_user_enabled is off. Write settings ( --write-settings ) and restart the QA container." >&2
  exit 1
fi
if [[ "$local_on" != "True" && "$local_on" != "true" ]]; then
  echo "local_login_enabled is off. Fix settings.json auth.local_login_enabled and restart." >&2
  exit 1
fi

# Owner first (bootstrap if no local users yet)
register_or_login "$OWNER_USER" "$OWNER_PASS" >/dev/null
# Ensure we hold an owner session for subsequent creates
login_body=$(printf '{"username":%s,"password":%s}' "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$OWNER_USER")" "$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1]))' "$OWNER_PASS")")
api POST /api/auth/local/login "$login_body" >/dev/null

register_or_login "$MEMBER_USER" "$MEMBER_PASS" >/dev/null
# Re-login as owner (register sets cookie to the new user)
api POST /api/auth/local/login "$login_body" >/dev/null

register_or_login "$YOUTH_USER" "$YOUTH_PASS" >/dev/null
api POST /api/auth/local/login "$login_body" >/dev/null
youth_id=$(find_user_id "$YOUTH_USER")
if [[ -z "$youth_id" ]]; then
  echo "Could not resolve youth user id for $YOUTH_USER" >&2
  exit 1
fi
api PATCH "/api/users/$youth_id" '{"is_youth":true}' >/dev/null
echo "Set is_youth=true on $YOUTH_USER ($youth_id)"

if [[ "$SEED_GUEST_ROLE" == "1" ]]; then
  register_or_login "$GUEST_USER" "$GUEST_PASS" >/dev/null
  api POST /api/auth/local/login "$login_body" >/dev/null
  guest_id=$(find_user_id "$GUEST_USER")
  if [[ -z "$guest_id" ]]; then
    echo "Could not resolve guest user id for $GUEST_USER" >&2
    exit 1
  fi
  api PATCH "/api/users/$guest_id" '{"role":"guest"}' >/dev/null
  echo "Set role=guest on $GUEST_USER ($guest_id) — guest shell when signed in"
fi

echo
echo "QA personas ready at $BASE_URL"
echo "  owner : $OWNER_USER  (local password)"
echo "  member: $MEMBER_USER  (local password)"
echo "  youth : $YOUTH_USER  (local password + is_youth)"
if [[ "$SEED_GUEST_ROLE" == "1" ]]; then
  echo "  guest : $GUEST_USER  (local password + role=guest) OR open $BASE_URL/tour (no login)"
else
  echo "  guest : open $BASE_URL/tour (no login; CURATORX_GUEST_TOUR_ENABLED / guest_tour_enabled)"
fi
echo "Auth remains ON. Do not share this volume with production."
