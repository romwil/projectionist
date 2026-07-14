#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Prefer 8799 over 8788: :8788 is often an SSH tunnel to production (or Docker).
# Binding/reusing 8788 makes Playwright hit the live old UI, not this local build.
PORT="${E2E_PORT:-8799}"
DATA_DIR="${E2E_DATA_DIR:-$(mktemp -d -t curatorx-e2e-XXXXXX)}"

export DATA_DIR
export PORT
export CURATORX_SKIP_DOTENV=1

if [[ ! -d "$ROOT/frontend/dist" ]]; then
  echo "Building frontend for E2E..."
  (cd "$ROOT/frontend" && npm install && npm run build)
fi

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
else
  echo "Python 3 is required to run CuratorX E2E tests." >&2
  exit 1
fi

echo "Starting CuratorX E2E server on :$PORT (DATA_DIR=$DATA_DIR)"
exec "$PYTHON" -m curatorx.web
