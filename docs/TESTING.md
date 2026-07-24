# End-to-end UI testing

CuratorX uses [Playwright](https://playwright.dev/) for browser tests against the full stack (FastAPI + built React SPA).

For **value-based backend unit tests** (assert exact tool/SQL results, not just response shape), see the root [TESTING.md](../TESTING.md).

## CA release checklist

> **Docs gate:** every user-facing change updates the relevant guide **and** adds a benefit-led `### Highlights` entry to `CHANGELOG.md`, meeting [DOCS_STYLE.md](DOCS_STYLE.md). Docs are a first-class deliverable, checked in every PR.

For the full maintainer/agent ship path (version bump, GitHub release, Docker Hub), see **[RELEASE.md](RELEASE.md)**. The table below is the CA test gate that feeds that runbook.

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

## QA sidecar — multi-role (auth ON)

Use a **second container** for browser / Playwright / Cursor browser MCP QA that exercises **real logins**. Do **not** turn production auth off and do **not** mount production `/config`.

| Persona | How you enter | Notes |
|---------|---------------|--------|
| **Owner** | First `POST /api/auth/local/register` (or login) | Bootstrap owner when no local users exist yet |
| **Member** | Owner creates via `POST /api/auth/local/register` (owner session) | Regular household user (`role=member`) |
| **Youth** | Same as member, then `PATCH /api/users/{id}` `{"is_youth": true}` | Content gate uses `youth.max_content_rating` (default PG-13) |
| **Guest (tour)** | Open `/tour` — **no password** | Requires `features.guest_tour_enabled` and/or `CURATORX_GUEST_TOUR_ENABLED=1`. Public allowlist includes `/api/guest/tour`. |
| **Guest (role)** | Optional local account with `PATCH` `{"role":"guest"}` | Logged-in **guest shell** (limited chrome). Distinct from the public tour. |

**Guest can / can’t (tour path):** with multi-user on and no session, visitors can hit `/tour`, `GET /api/guest/tour` (published collections), login/auth routes, and `POST /api/access-requests`. They **cannot** call gated APIs (settings, chat, admin, library mutations) — those return **401** until signed in. A signed-in `role=guest` user gets a session and guest shell UI (browse / ask with destructive actions withheld), still not owner Admin.

Access requests (`POST /api/access-requests`) are a separate public path: visitors ask for membership; the owner approves from Admin (can mint a local member + one-time password when local login is on). Seed script skips that queue and creates accounts directly.

### Automat / Unraid stand-up (LAN port 8790, never VIP)

```bash
# On automat (example host 10.10.1.202)
mkdir -p /mnt/user/appdata/curatorx-qa
cd /path/to/mediacurator   # or copy compose + scripts there

cp .env.qa.example .env.qa
# Edit .env.qa: CURATORX_SESSION_SECRET, QA_* passwords, QA_CONFIG_PATH
# QA_CONFIG_PATH=/mnt/user/appdata/curatorx-qa
# QA_BASE_URL=http://10.10.1.202:8790

# 1) Write multi-user + local-login settings BEFORE first start
bash scripts/seed-qa-roles.sh --settings-only --config-dir /mnt/user/appdata/curatorx-qa

# 2) Start isolated sidecar (host :8790 → container :8788)
docker compose -f docker-compose.qa.yml --env-file .env.qa up -d

# 3) Seed owner / member / youth (+ optional guest-role account)
bash scripts/seed-qa-roles.sh --base-url http://10.10.1.202:8790 --env-file .env.qa
```

Compose file: [`docker-compose.qa.yml`](../docker-compose.qa.yml). Env template: [`.env.qa.example`](../.env.qa.example). Seed: [`scripts/seed-qa-roles.sh`](../scripts/seed-qa-roles.sh).

Settings written by the seed script:

- `features.multi_user_enabled: true`
- `auth.mode: local`, `local_login_enabled: true`, **Plex login off**, **OIDC off**
- `features.guest_tour_enabled: true` (+ compose sets `CURATORX_GUEST_TOUR_ENABLED=1`)

Cursor browser MCP / agents: use **`http://10.10.1.202:8790`** (or your LAN IP). Never share prod config or VIP.

### Playwright: four `storageState` files

| File | Persona |
|------|---------|
| `e2e/.auth/owner.json` | Owner session |
| `e2e/.auth/member.json` | Member session |
| `e2e/.auth/youth.json` | Youth session (`is_youth`) |
| `e2e/.auth/guest.json` | Logged-in guest **role** |
| `e2e/.auth/guest-tour.json` | Public `/tour` (no login) |

```bash
set -a && source .env.qa && set +a
CURATORX_E2E_QA_ROLES=1 QA_BASE_URL=http://10.10.1.202:8790 npm run test:e2e:qa-roles
# → runs e2e/auth.setup.ts then e2e/live-roles.spec.ts via playwright.qa.config.ts
#
# Skip re-login when auth files already exist:
#   QA_SKIP_SETUP=1 CURATORX_E2E_QA_ROLES=1 QA_BASE_URL=http://10.10.1.202:8790 \
#     npm run test:e2e:qa-roles
```

Helpers: `e2e/fixtures/auth-roles.ts`. To exercise past-login UI as one persona without rebuilding the whole suite:

```ts
test.use({ storageState: "e2e/.auth/member.json" });
// or browser.newContext({ storageState: "e2e/.auth/youth.json", baseURL })
```

Default `npm run test:e2e` stays mocked/offline; QA role tests are opt-in only (`playwright.config.ts` ignores `auth.setup.ts` / `live-roles.spec.ts`).

### Role UI matrix (`e2e/live-roles.spec.ts`)

| Surface | Owner | Member | Youth | Guest tour | Guest role |
|---------|-------|--------|-------|------------|------------|
| Login / land | workspace | workspace | youth shell | `/tour` public | guest shell |
| Chat | ✓ composer | ✓ | ✓ Ask label | → `/login` | ✓ Ask label |
| Explore / Search | ✓ | ✓ | ✓ Browse | → `/login` | ✓ Browse |
| Inbox | ✓ | ✓ | ✓ | no | nav hidden |
| My Journey | ✓ | ✓ | ✓ | no | nav hidden |
| Settings | ✓ + Admin link | ✓ subset | ✓ + youth badge | no | nav hidden |
| Admin | ✓ rail | redirected | redirected | → login | redirected |
| Help / Privacy | ✓ owners jump | ✓ member | ✓ member | ✓ public | ✓ member |
| Theme toggle | once on chat | once on chat | once on chat | — | once on chat |

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
