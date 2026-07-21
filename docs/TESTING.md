# End-to-end UI testing

CuratorX uses [Playwright](https://playwright.dev/) for browser tests against the full stack (FastAPI + built React SPA).

For **value-based backend unit tests** (assert exact tool/SQL results, not just response shape), see the root [TESTING.md](../TESTING.md).

## CA release checklist

> **Docs gate:** every user-facing change updates the relevant guide **and** adds a benefit-led `### Highlights` entry to `CHANGELOG.md`, meeting [DOCS_STYLE.md](DOCS_STYLE.md). Docs are a first-class deliverable, checked in every PR.

Run these layers before tagging a Community Applications release. Default CI and local discover paths need **no** live Plex / Radarr / Sonarr / Seerr / LLM secrets.

| Layer | Command | Secrets? |
|-------|---------|----------|
| Backend unit + CA edge | `.venv/bin/python -m unittest discover -s tests -v` (or `pytest tests/ -v`) | No |
| Explore / neighbors value suite | `pytest tests/test_explore_wave3.py tests/test_title_neighbors_api.py -v` | No |
| Focused CA suite | `.venv/bin/python -m unittest tests.test_ca_release -v` | No |
| Frontend unit | `cd frontend && npm run test:unit` (includes theme prefs + matchScore) | No |
| Mocked Playwright | `npm run test:e2e` | No |
| Security pentest checklist (optional) | `python3 scripts/security/pentest/run-checklist.py` | No |
| Live service ping (optional) | `CURATORX_LIVE_INTEGRATION=1 …` (below) | Yes |
| Live stack Playwright (optional) | `npm run test:e2e:live-stack` | Running server |

### Still impossible without a real Plex account / OAuth

Even with live flags and API keys, these flows stay out of automated CA gates:

- Full **Plex OAuth PIN** browser sign-in (tv.plex.tv pin dance) — e2e uses mocked `POST /api/auth/plex` + pasted token UI instead
- Writing real library ratings / collections against a production Plex (unit tests mock the client)
- End-to-end LLM chat quality (chat e2e echoes mocked `/api/chat`)
- Seerr member request path with a linked Plex user identity from a live OAuth session

## CA / release unit tests

Before Community Applications release, run the non-e2e suites (no live Plex/LLM required):

```bash
# Backend (from repo root, with venv activated or via .venv)
.venv/bin/python -m unittest discover -s tests -v

# Frontend unit tests (slash commands, id fallback, arr confirm copy, dock targets)
cd frontend && npm run test:unit
```

Optional focused CA edge suite:

```bash
.venv/bin/python -m unittest tests.test_ca_release -v
```

These cover auth-disabled bootstrap, empty library stats/sync start, optional_int float ratings,
message feedback/reviews/webhooks error paths, Seerr/multi-user-off API safety, and arr confirm
friendly errors.

### API authz regression (multi-user) — `tests/test_api_authz.py`

Regression suite for multi-user API enforcement (`tests/test_api_authz.py`). When
`features.multi_user_enabled` is **on**, unauthenticated clients must not hit the control plane.

| Expectation | Request (no session cookie) | Expected |
|-------------|----------------------------|----------|
| Settings read gated | `GET /api/settings` | **401** |
| Settings write gated | `PUT /api/settings` | **401** |
| Chat gated | `POST /api/chat` | **401** |
| Action confirm gated | `POST /api/actions/confirm` | **401** |
| Allowlist still public | `GET /api/health`, `GET /api/features`, `/api/auth/*` | **200** / auth flow as designed |
| Webhook allowlist | `POST /api/webhooks/plex` (with valid secret when required) | Not forced through session auth |

When multi-user is **off**, preserve trusted-LAN single-owner behavior (bootstrap owner; existing
`tests/test_ca_release.py` must stay green). Full finding list: [SECURITY.md](SECURITY.md).

Live integration tests (`tests/test_live_integrations.py`) are **skipped** during discover unless
`CURATORX_LIVE_INTEGRATION=1` is set — see [Live service integrations](#live-service-integrations-optional).

## Quick start

From the repo root with Python dependencies installed (`pip install -e ".[web]"`):

```bash
bash scripts/run-e2e.sh
```

On **Windows (PowerShell)** without WSL:

```powershell
.\scripts\run-e2e.ps1
```

Playwright starts the temp server with `node scripts/start-e2e-server.mjs` (see `playwright.config.ts`).


Or step by step:

```bash
cd frontend && npm install && npm run build && cd ..
npm install
npx playwright install chromium
npm run test:e2e
```

Tests start a temporary CuratorX server on **http://127.0.0.1:8799** (override with `E2E_PORT` / `E2E_BASE_URL`).

### Port 8788 trap (do not use for mocked e2e)

**Never point default Playwright / mocked e2e at `localhost:8788`.** On many developer machines that port is an **SSH tunnel to production** (or Docker). With `reuseExistingServer`, Playwright will happily talk to that live/old UI instead of your local build — confusing failures and wasted debugging.

| Port | Use |
|------|-----|
| **8799** (default) | Mocked / temp e2e server Playwright starts |
| **8788** | App / Docker / Unraid host mapping; only for intentional live-stack tests via `E2E_BASE_URL` |

```bash
# Explicit free port (same as default):
E2E_PORT=8799 npm run test:e2e
```

## What is covered (mocked e2e)

| Suite | Coverage |
|-------|----------|
| `e2e/chat.spec.ts` | Single chat workspace (composer, cards, threads) |
| `e2e/setup-banner.spec.ts` | Incomplete setup banner on `/` |
| `e2e/config-wizard.spec.ts` | 3-step onboarding wizard |
| `e2e/config-maintenance.spec.ts` | Maintenance dashboard + library sync card |
| `e2e/login.spec.ts` | Multi-user gate → `/login`, Plex sign-in UI, mocked auth |
| `e2e/drag-to-dock.spec.ts` | Status dock drop hint only while dragging |
| `e2e/ca-release.spec.ts` | Health + app load, sync progress friendly label/%, no Phase labels |
| `e2e/live.spec.ts` | Opt-in real-stack smoke (`CURATORX_E2E_LIVE=1`) |

Mocked suites intercept `/api/chat`, `/api/setup/test/*`, `/api/plex/sections`, `/api/features`,
`/api/auth/*`, `/api/setup/status`, and (for sync UI) `/api/jobs` so CI passes without Anthropic or
Plex credentials. Wizard/setup-banner suites use `setForceWizardIncomplete` so a shared e2e server
that already finished onboarding still shows the wizard (the API preserves `onboarding_complete`).

## Live service integrations (optional)

Python suite that **pings real** Plex / Radarr / Sonarr / Seerr using the same connection helpers
as Configuration → Test. Skipped unless explicitly enabled:

```bash
# From repo root; load secrets from environment and/or .env / config/settings.json
export CURATORX_LIVE_INTEGRATION=1
# Optional: DATA_DIR=./config  (defaults to ./config)
# Required per service you want exercised:
#   PLEX_URL + PLEX_TOKEN
#   RADARR_URL + RADARR_API_KEY
#   SONARR_URL + SONARR_API_KEY
#   SEERR_URL + SEERR_API_KEY

.venv/bin/python -m unittest tests.test_live_integrations -v
```

CI with repository secrets:

```bash
CURATORX_LIVE_INTEGRATION=1 \
  PLEX_URL="$PLEX_URL" PLEX_TOKEN="$PLEX_TOKEN" \
  RADARR_URL="$RADARR_URL" RADARR_API_KEY="$RADARR_API_KEY" \
  SONARR_URL="$SONARR_URL" SONARR_API_KEY="$SONARR_API_KEY" \
  SEERR_URL="$SEERR_URL" SEERR_API_KEY="$SEERR_API_KEY" \
  .venv/bin/python -m unittest tests.test_live_integrations -v
```

Unset `CURATORX_LIVE_INTEGRATION` (or leave it unset) for normal discover — every live case skips cleanly.
Individual services also skip when that service’s URL/key pair is missing.

## Live Playwright against a real stack (optional)

Two related switches:

| Env | Effect |
|-----|--------|
| `E2E_MOCK_APIS=0` | Disable route mocks; browser hits the real API (`npm run test:e2e:live`) |
| `CURATORX_E2E_LIVE=1` | Run `e2e/live.spec.ts` smoke against a running server (`npm run test:e2e:live-stack`) |

```bash
# Stack already up (Docker or local web):
docker compose up -d
CURATORX_E2E_LIVE=1 E2E_MOCK_APIS=0 E2E_BASE_URL=http://127.0.0.1:8788 npm run test:e2e:live-stack
```

Without `CURATORX_E2E_LIVE=1`, `e2e/live.spec.ts` skips so default `npm run test:e2e` stays green offline.

## CI / full test suite

GitHub Actions runs Python unit tests, frontend build, and Playwright E2E on every push/PR to `main`.

Run the same locally:

```bash
npm test
```

This executes `python -m unittest discover`, `frontend` production build, and Playwright.

For CA release readiness without Playwright (or when no browser deps are installed), prefer the **CA / release unit tests** section above.

## Maintenance

- Prefer `data-testid` attributes for stable selectors (see components under `frontend/src/`).
- Shared mocks live in `e2e/fixtures/api-mocks.ts`.
- Page helpers: `e2e/fixtures/helpers.ts`, `e2e/fixtures/selectors.ts`.
