#!/usr/bin/env bash
# Mocked Playwright e2e. Default port is 8799 (see playwright.config.ts).
# Do NOT use :8788 — it is often an SSH tunnel to production / Docker.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ "${SKIP_FRONTEND_BUILD:-0}" != "1" ]]; then
  (cd frontend && npm install && npm run build)
fi

npm install
npx playwright install chromium
npm run test:e2e "$@"
