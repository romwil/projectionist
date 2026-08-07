# AGENTS.md

## Cursor Cloud specific instructions

Projectionist is a **single service**: a Python 3.12 FastAPI backend (`python -m projectionist.web`) that
also serves the pre-built React SPA from `frontend/dist`. Optional stdio/HTTP MCP server
(`python -m projectionist.mcp.server`). There is **no separate database/cache/queue** to run — state is
SQLite under `DATA_DIR` (WAL). Plex / Radarr / Sonarr / TMDB / LLM are all optional integrations and
are **not** required to boot, run, or test the app (it starts in single-owner mode with no login).

### Environment (already provisioned by the update script)
- Python venv at `.venv` (created with `python3.12 -m venv`; needs the `python3.12-venv` apt package,
  which the VM image provides). Package installed editable with `.[web,dev,mcp]` extras.
- Frontend deps installed in `frontend/`. The SPA must be **built** (`frontend/dist`) before the
  backend can serve the UI and before e2e runs — the update script does this.

### Run the dev server (single service)
```bash
DATA_DIR=./config PORT=8788 PROJECTIONIST_SKIP_DOTENV=1  # CURATORX_SKIP_DOTENV still accepted .venv/bin/python -m projectionist.web
```
Serves on http://127.0.0.1:8788 (`GET /api/health` → `{"status":"ok"}`). `PROJECTIONIST_SKIP_DOTENV=1  # CURATORX_SKIP_DOTENV still accepted`
avoids picking up a stray `.env`. Generated files land in `DATA_DIR` (`config/`, gitignored).
Backend has **no hot reload** (`reload=False`); restart the process after Python changes. After
editing frontend source, re-run `cd frontend && npm run build` (or use `npm run dev` / Vite on its
own port, which proxies `/api` to `:8788`).

### Lint / test / build (commands live in README.md, TESTING.md, docs/TESTING.md)
- **Lint (frontend):** `cd frontend && npm run lint` — **0 errors** required at release (pre-existing
  warnings OK). There is no dedicated Python linter in CI. The SPA compile gate is
  `cd frontend && npm run build`.
- **Backend tests:** `.venv/bin/python -m pytest tests/` (coverage is auto-enabled via `pyproject.toml`,
  `--cov-fail-under=74`; same floor in `.github/workflows/ci.yml`). Full suite ~2.5 min.
- **Frontend unit:** `cd frontend && npm run test:unit`.
- **Mocked e2e:** `npm run test:e2e` (needs `npx playwright install chromium` once). Playwright starts
  its **own** temp server via `node scripts/start-e2e-server.mjs` on **port 8799** (NOT 8788 — see
  `.cursor/rules/e2e-port-8788.mdc`) using the `.venv` python; no live Plex/LLM needed.
- **Full-stack QA layers** (CI, maintainer `:8790` sidecar, Interactive UI QA, pentest harness):
  [docs/superpowers/specs/2026-07-29-feature-testing-environment-blueprint.md](docs/superpowers/specs/2026-07-29-feature-testing-environment-blueprint.md).

### Rate limits in API tests
`tests/test_api_authz.py` (and several other API suites) call `clear_rate_limits()` in `setUp` /
`tearDown` so cumulative `POST /api/auth/plex` calls do not trip the in-process 10/60s limiter.
If you add suites that hit rate-limited auth routes heavily, clear the limiter between tests the
same way — otherwise later cases can see 429 and missing `user` keys.

### Automat maintainer LAN (version / health / UI truth)
When checking the live Automat Unraid stack, use LAN hosts — **not** the public hostname:

| Role | URL |
|------|-----|
| Prod | `http://10.10.1.202:8788` |
| QA sidecar | `http://10.10.1.202:8790` |

Do **not** treat `https://projectionist.automat.vip` (or ad-hoc SSH tunnels / `localhost:8788` tunnels)
as authoritative for version or admin UI. Rollout kit: `/mnt/user/appdata/projectionist` (often
`/Volumes/appdata/projectionist`). Full runbook: [docs/ops/AUTOMAT.md](docs/ops/AUTOMAT.md).
Agent rule: `.cursor/rules/automat-environments.mdc`. Interactive UI QA → `:8790` only
(`.cursor/skills/interactive-ui-qa/SKILL.md`).
